#!/usr/bin/env python3
"""Build identity, offline Ed25519 signing, and gated release publication."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import tempfile
import time

DEVICE = Path(__file__).resolve().parents[1]
REPO = "github.com/travismills82/twrp_device_oplus_infiniti"
SIGNED_ASSETS = ("recovery.img", "twrp-update.json", "twrp-update.json.sig", "SHA256SUMS")
IMAGE_BYTES = 104857600
DER_ED25519 = bytes.fromhex("302a300506032b6570032100")
COMMON = dict(schema=1, device="infiniti", twrp="3.7.1-16",
              compatibility="op15-dedicated-ab-recovery-v1", partition_bytes=IMAGE_BYTES)


def check(ok, message):
    if not ok:
        raise ValueError(message)


def canonical(obj):
    return (json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True) + "\n").encode()


def hex32(value):
    return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value)


def verify_profiles(profiles):
    check(isinstance(profiles, list) and 1 <= len(profiles) <= 24, "Need between 1 and 24 tested profiles")
    for p in profiles:
        hashes = {"boot", "init_boot", "vendor_boot", "dtbo", "vbmeta", "from_recovery"}
        check(isinstance(p, dict) and set(p) == {"project", "slot"} | hashes,
              "Malformed compatibility profile")
        check(p["project"] in ("24831", "24863") and p["slot"] in ("_a", "_b") and
              all(hex32(p[k]) for k in hashes),
              "Invalid project, slot or full-partition SHA-256")
    check(len({canonical(p) for p in profiles}) == len(profiles), "Duplicate compatibility profiles")
    return profiles


def identity(a):
    commit = subprocess.check_output(["git", "-C", str(DEVICE), "rev-parse", "HEAD"], text=True).strip()
    check(re.fullmatch(r"[0-9a-f]{40}", commit), "Missing device-tree commit")
    check(0 < a.build <= (1 << 53) - 1, "Invalid monotonic build ID")
    check(a.channel == "development" and not a.public_key or hex32(a.public_key),
          "Release builds require the raw Ed25519 public key (64 lowercase hex digits)")
    doc = dict(COMMON, build=a.build, timestamp=int(time.time()), commit=commit,
               channel=a.channel, public_key=a.public_key)
    a.output.write_bytes(canonical(doc))


def verify_packed_identity(path, expected, commit, build):
    check(len(expected)<=4096,"Release identity is too large")
    doc=json.loads(expected)
    check(all(doc.get(k)==v for k,v in COMMON.items()) and doc.get("commit")==commit and
          doc.get("build")==build and path.stat().st_size==IMAGE_BYTES,
          "Handoff identity, commit, or image size mismatch")
    with tempfile.TemporaryDirectory(prefix="op15-identity-") as temp, path.open("rb") as image:
        header=image.read(44)
        check(header[:8]==b"ANDROID!" and header[8:12]==bytes(4) and
              int.from_bytes(header[40:44],"little")==4,"Invalid packaged recovery header")
        length=int.from_bytes(header[12:16],"little")
        check(0<length<IMAGE_BYTES-4096,"Invalid packaged ramdisk length")
        image.seek(4096)
        ramdisk=Path(temp)/"ramdisk.lz4"
        with ramdisk.open("wb") as out:
            while length:
                chunk=image.read(min(length,1024*1024))
                check(chunk,"Truncated packaged ramdisk")
                out.write(chunk)
                length-=len(chunk)
        # Never unpack archive paths to disk; extract only the named identity.
        with subprocess.Popen(["lz4","-q","-dc",str(ramdisk)],stdout=subprocess.PIPE) as unzip:
            with subprocess.Popen(["cpio","--quiet","-i","--to-stdout","system/etc/op15-updater-identity.json"],
                                  stdin=unzip.stdout,stdout=subprocess.PIPE) as cpio:
                unzip.stdout.close()
                packed=cpio.stdout.read(4097)
                if len(packed)>4096:
                    cpio.kill()
                result=cpio.wait(timeout=30)
            check(result==0 and unzip.wait(timeout=30)==0 and packed==expected,
                  "Packaged build identity differs from the release artifact")
    return doc


def verify_identity(a):
    verify_packed_identity(a.image, a.identity.read_bytes(), a.commit, a.build)
    print("Packaged updater identity verified")


def sign(a):
    identity = json.loads(a.identity.read_bytes())
    check(all(identity.get(k) == v for k, v in COMMON.items()), "Wrong board or image format")
    check(identity["channel"] in ("stable", "prerelease") and identity["build"] > 0 and identity["timestamp"] > 0 and
          re.fullmatch(r"[0-9a-f]{40}", identity["commit"]) and hex32(identity["public_key"]),
          "Release requires a provisioned build identity")
    check(re.fullmatch(r"[A-Za-z0-9._-]{1,96}", a.tag) and a.tag not in (".", ".."), "Invalid GitHub release tag")
    key = a.key.resolve(strict=True)
    check(DEVICE not in key.parents and not key.stat().st_mode & (stat.S_IRWXG | stat.S_IRWXO),
          "Keep the private key outside the checkout with mode 0600 or more restrictive")
    pub = subprocess.check_output(["openssl", "pkey", "-in", str(key), "-pubout", "-outform", "DER"])
    check(len(pub) == len(DER_ED25519) + 32 and pub.startswith(DER_ED25519) and
          pub[len(DER_ED25519):].hex() == identity.pop("public_key"),
          "Signing key does not match the verification key embedded in recovery")
    profiles = verify_profiles(json.loads(a.profiles.read_bytes()))
    notes = a.notes.read_text().strip()
    check(0 < len(notes.encode()) <= 3072, "Signed release notes must be 1–3072 UTF-8 bytes")
    check(a.image.is_file() and a.image.stat().st_size == IMAGE_BYTES, "Image must cover all 100 MiB of recovery")
    with a.image.open("rb") as f:
        header = f.read(44)
        check(header[:8] == b"ANDROID!" and header[8:12] == bytes(4) and
              int.from_bytes(header[40:44], "little") == 4, "Invalid recovery boot image header")
        f.seek(-64, os.SEEK_END)
        check(f.read(4) == b"AVBf", "Recovery AVB footer is missing")
        f.seek(0)
        digest = hashlib.file_digest(f, "sha256").hexdigest()
    out = a.output
    out.mkdir(parents=True, exist_ok=True)
    document = out / "twrp-update.json"
    document.write_bytes(canonical(dict(identity, tag=a.tag, notes=notes, asset="recovery.img",
                                       sha256=digest, profiles=profiles)))
    signature = out / "twrp-update.json.sig"
    subprocess.run(["openssl", "pkeyutl", "-sign", "-rawin", "-inkey", str(key),
                    "-in", str(document), "-out", str(signature)], check=True)
    check(signature.stat().st_size == 64, "Unexpected Ed25519 signature length")
    # Validate the signing output, not only the signing process exit status.
    subprocess.run(["openssl", "pkeyutl", "-verify", "-rawin", "-pubin", "-keyform", "DER",
                    "-inkey", "/dev/stdin", "-in", str(document), "-sigfile", str(signature)],
                   check=True, input=pub)
    (out / "SHA256SUMS").write_text(f"{digest}  recovery.img\n")


def verify_release(a):
    """Verify the publishable bundle against independently supplied release inputs."""
    check(hex32(a.public_key), "A trusted Ed25519 public key is required")
    check(re.fullmatch(r"[0-9a-f]{40}", a.commit), "Expected a full release commit SHA")
    check(re.fullmatch(r"[A-Za-z0-9._-]{1,96}", a.tag) and a.tag not in (".", ".."),
          "Invalid GitHub release tag")
    image, manifest, signature, checksum = (a.assets / file for file in SIGNED_ASSETS)
    for asset in (image, manifest, signature, checksum):
        check(asset.is_file() and not asset.is_symlink(), f"Missing required release asset: {asset.name}")
    check(0 < manifest.stat().st_size <= 32768 and signature.stat().st_size == 64,
          "Invalid release manifest or signature length")
    subprocess.run(["openssl", "pkeyutl", "-verify", "-rawin", "-pubin", "-keyform", "DER",
                    "-inkey", "/dev/stdin", "-in", str(manifest), "-sigfile", str(signature)],
                   check=True, input=DER_ED25519 + bytes.fromhex(a.public_key))
    raw = manifest.read_bytes()
    signed = json.loads(raw)
    check(raw == canonical(signed), "Release manifest must be canonical JSON")
    check(all(signed.get(k) == v for k, v in COMMON.items()) and
          signed.get("tag") == a.tag and signed.get("commit") == a.commit and
          signed.get("channel") == a.channel and signed.get("asset") == image.name,
          "Signed release tag, device, commit, channel or asset mismatch")
    build, timestamp = signed.get("build"), signed.get("timestamp")
    check(type(build) is int and 0 < build <= (1 << 53) - 1 and
          type(timestamp) is int and timestamp > 0, "Invalid signed build identity")
    notes, digest = signed.get("notes"), signed.get("sha256")
    check(isinstance(notes, str) and notes.strip() and len(notes.encode()) <= 3072 and hex32(digest),
          "Missing or invalid signed release notes or image digest")
    verify_profiles(signed.get("profiles"))
    expected_checksum = f"{digest}  recovery.img\n".encode()
    check(checksum.stat().st_size == len(expected_checksum) and checksum.read_bytes() == expected_checksum,
          "SHA256SUMS does not match the signed image digest")
    check(image.stat().st_size == IMAGE_BYTES, "Image must cover all 100 MiB of recovery")
    with image.open("rb") as payload:
        payload.seek(-64, os.SEEK_END)
        check(payload.read(4) == b"AVBf", "Recovery AVB footer is missing")
        payload.seek(0)
        check(hashlib.file_digest(payload, "sha256").hexdigest() == digest,
              "Recovery image does not match the signed image digest")
    identity_file = a.assets / "identity.json"
    check(identity_file.is_file() and identity_file.stat().st_size <= 4096, "Missing or oversized build identity")
    expected = identity_file.read_bytes()
    identity = {k: signed[k] for k in (*COMMON, "build", "timestamp", "commit", "channel")}
    check(json.loads(expected) == dict(identity, public_key=a.public_key),
          "Signed manifest does not match the build identity or its trusted key")
    verify_packed_identity(image, expected, a.commit, build)
    print(f"Verified signed release {a.tag}: {a.channel} build {build}, {digest}", flush=True)


def publish(a):
    verify_release(a)
    installers = sorted(a.assets.glob("TWRP-*.zip"))
    check(len(installers) == 1 and re.fullmatch(r"TWRP-[A-Za-z0-9._-]+\.zip", installers[0].name) and
          installers[0].is_file() and not installers[0].is_symlink(), "Expected exactly one TWRP installer ZIP")
    check(a.release_notes.is_file(), "Missing GitHub release description")
    flags = ["--prerelease"] if a.channel == "prerelease" else []
    subprocess.run(["gh", "release", "create", "--repo", REPO, "--target", a.commit,
                    "--title", a.title, "--notes-file", str(a.release_notes.resolve()),
                    *flags, "--", a.tag, *SIGNED_ASSETS, installers[0].name],
                   cwd=a.assets, check=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(required=True)
    new = sub.add_parser("identity")
    new.add_argument("--build", required=True, type=int)
    new.add_argument("--channel", choices=("stable", "prerelease", "development"), required=True)
    new.add_argument("--public-key", default="")
    new.add_argument("--output", required=True, type=Path)
    new.set_defaults(run=identity)
    verify = sub.add_parser("verify-identity")
    verify.add_argument("--identity", required=True, type=Path)
    verify.add_argument("--image", required=True, type=Path)
    verify.add_argument("--commit", required=True)
    verify.add_argument("--build", required=True, type=int)
    verify.set_defaults(run=verify_identity)
    seal = sub.add_parser("sign")
    for key in ("identity", "image", "profiles", "notes", "key", "output"):
        seal.add_argument("--"+key, type=Path, required=True)
    seal.add_argument("--tag", required=True)
    seal.set_defaults(run=sign)
    for command, handler in (("verify-release", verify_release), ("publish", publish)):
        gate = sub.add_parser(command)
        gate.add_argument("--assets", type=Path, required=True)
        gate.add_argument("--tag", required=True)
        gate.add_argument("--commit", required=True)
        gate.add_argument("--channel", choices=("stable", "prerelease"), required=True)
        gate.add_argument("--public-key", required=True)
        if command == "publish":
            gate.add_argument("--title", required=True)
            gate.add_argument("--release-notes", type=Path, required=True)
        gate.set_defaults(run=handler)
    a = parser.parse_args()
    try:
        a.run(a)
    except (ValueError, OSError, KeyError, subprocess.SubprocessError) as e:
        parser.exit(1, f"Updater release validation failed: {e}\n")


if __name__ == "__main__":
    main()
