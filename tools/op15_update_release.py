#!/usr/bin/env python3
"""Build identity and offline Ed25519 release signing. Never writes a private key."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import time

DEVICE = Path(__file__).resolve().parents[1]
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


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(required=True)
    new = sub.add_parser("identity")
    new.add_argument("--build", required=True, type=int)
    new.add_argument("--channel", choices=("stable", "prerelease", "development"), required=True)
    new.add_argument("--public-key", default="")
    new.add_argument("--output", required=True, type=Path)
    new.set_defaults(run=identity)
    seal = sub.add_parser("sign")
    for key in ("identity", "image", "profiles", "notes", "key", "output"):
        seal.add_argument("--"+key, type=Path, required=True)
    seal.add_argument("--tag", required=True)
    seal.set_defaults(run=sign)
    a = parser.parse_args()
    try:
        a.run(a)
    except (ValueError, OSError, KeyError, subprocess.CalledProcessError) as e:
        parser.exit(1, f"Updater release validation failed: {e}\n")


if __name__ == "__main__":
    main()
