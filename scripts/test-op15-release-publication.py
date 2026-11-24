#!/usr/bin/env python3
"""Exercise the publication gate with disposable keys and a fake GitHub CLI."""
import json
import os
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest


TOOL = Path(__file__).resolve().parents[1] / "tools/op15_update_release.py"
PARTITION_BYTES = 104857600


def run(*args, **kwargs):
    return subprocess.run([str(a) for a in args], **kwargs)


class ReleasePublication(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        temp = tempfile.TemporaryDirectory(prefix="op15-publication-test-")
        cls.addClassCleanup(temp.cleanup)
        cls.root = Path(temp.name)
        cls.fake_gh_call = cls.root / "gh-call"
        gh = cls.root / "gh"
        gh.write_text('#!/bin/sh\nprintf "%s\\n" "$@" > "$FAKE_GH_CALL"\n')
        gh.chmod(0o700)
        cls.key = cls.root / "key.pem"
        run("openssl", "genpkey", "-algorithm", "ED25519", "-out", cls.key, check=True)
        cls.key.chmod(0o600)
        cls.pub = subprocess.check_output(["openssl", "pkey", "-in", cls.key, "-pubout", "-outform", "DER"])[-32:].hex()
        profiles, notes = cls.root / "profiles.json", cls.root / "notes.txt"
        hashes = ("boot", "init_boot", "vendor_boot", "dtbo", "vbmeta", "from_recovery")
        profiles.write_text(json.dumps([dict.fromkeys(hashes, "d"*64) | dict(project="24863", slot="_a")]))
        notes.write_text("Signed test notes. Never publish this fixture.\n")

        for channel in ("stable", "prerelease"):
            stage = cls.root / channel
            stage.mkdir()
            identity = stage / "identity.json"
            run(sys.executable, TOOL, "identity", "--build", "1002", "--channel", channel,
                "--public-key", cls.pub, "--output", identity, check=True)
            cls.commit = json.loads(identity.read_bytes())["commit"]
            entry = Path("system/etc/op15-updater-identity.json")
            (stage / entry).parent.mkdir(parents=True)
            (stage / entry).write_bytes(identity.read_bytes())
            cpio = run("cpio", "--quiet", "-o", "-H", "newc", cwd=stage,
                       input=f"{entry}\n".encode(), stdout=subprocess.PIPE, check=True).stdout
            ramdisk = run("lz4", "-q", "-l", "-c", input=cpio, stdout=subprocess.PIPE, check=True).stdout
            header = bytearray(4096)
            header[:8] = b"ANDROID!"
            struct.pack_into("<I", header, 12, len(ramdisk))
            struct.pack_into("<I", header, 40, 4)
            image = stage / "recovery.img"
            with image.open("wb") as stream:
                stream.write(header)
                stream.write(ramdisk)
                # Synthetic envelope; native AVB validation has a separate test.
                stream.seek(PARTITION_BYTES - 64)
                stream.write(b"AVBf" + bytes(60))
            run(sys.executable, TOOL, "sign", "--identity", identity, "--image", image,
                "--key", cls.key, "--profiles", profiles, "--notes", notes, "--tag",
                f"fixture-{channel}", "--output", stage, check=True)
            (stage / "TWRP-fixture.zip").touch()
        cls.notes, cls.profiles = notes, profiles

    def publish(self, channel="stable", *, tag=None, pub=None, commit=None):
        self.fake_gh_call.unlink(missing_ok=True)
        env = dict(os.environ, FAKE_GH_CALL=str(self.fake_gh_call),
                   PATH=f"{self.root}:{os.environ['PATH']}")
        return run(sys.executable, TOOL, "publish", "--assets", self.root / channel,
                   "--tag", tag or f"fixture-{channel}", "--channel", channel,
                   "--commit", commit or self.commit, "--public-key", pub or self.pub,
                   "--title", "TWRP test", "--release-notes", self.notes,
                   capture_output=True, text=True, env=env)

    def reject(self, expected, **kwargs):
        result = self.publish(**kwargs)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(expected, result.stderr)
        self.assertFalse(self.fake_gh_call.exists(), "GitHub called before release verification passed")

    def test_passes_all_signed_assets_to_github_for_both_channels(self):
        for channel in ("stable", "prerelease"):
            with self.subTest(channel=channel):
                result = self.publish(channel)
                self.assertEqual(result.returncode, 0, result.stderr)
                argv = self.fake_gh_call.read_text().splitlines()
                self.assertEqual("--prerelease" in argv, channel == "prerelease")
                self.assertEqual(argv[-6:], [f"fixture-{channel}", "recovery.img", "twrp-update.json",
                                            "twrp-update.json.sig", "SHA256SUMS", "TWRP-fixture.zip"])

    def test_missing_required_manifest_or_signature(self):
        for name in ("twrp-update.json", "twrp-update.json.sig"):
            path = self.root / "stable" / name
            contents = path.read_bytes()
            try:
                path.unlink()
                self.reject(f"Missing required release asset: {name}")
            finally:
                path.write_bytes(contents)

    def test_wrong_key_tag_commit_and_changed_manifest(self):
        self.reject("Updater release validation failed", pub="1"*64)
        self.reject("Signed release tag", tag="another-tag")
        self.reject("Signed release tag", commit="2"*40)
        path = self.root / "stable" / "twrp-update.json"
        original = path.read_bytes()
        try:
            path.write_bytes(original.replace(b"Signed test notes", b"Wrong test notes"))
            self.reject("Updater release validation failed")
        finally:
            path.write_bytes(original)

    def test_changed_checksum_and_image(self):
        for name, data, message in (
            ("SHA256SUMS", b"x", "SHA256SUMS does not match"),
            ("recovery.img", b"X", "Recovery image does not match"),
        ):
            path = self.root / "stable" / name
            with self.subTest(filename=name), path.open("r+b") as f:
                position = 8192 if name == "recovery.img" else 0
                f.seek(position)
                original = f.read(len(data))
                try:
                    f.seek(position)
                    f.write(data)
                    f.flush()
                    self.reject(message)
                finally:
                    f.seek(position)
                    f.write(original)
                    f.flush()

    def test_valid_signature_cannot_override_embedded_identity(self):
        stage = self.root / "stable"
        assets = ["identity.json", "twrp-update.json", "twrp-update.json.sig", "SHA256SUMS"]
        originals = {stage / asset: (stage / asset).read_bytes() for asset in assets}
        identity = stage / "identity.json"
        try:
            identity.write_text(json.dumps(dict(json.loads(originals[identity]), build=1003)))
            self.reject("does not match the build identity")
            run(sys.executable, TOOL, "sign", "--identity", identity, "--image", stage / "recovery.img",
                "--key", self.key, "--profiles", self.profiles, "--notes", self.notes,
                "--tag", "fixture-stable", "--output", stage, check=True)
            self.reject("Packaged build identity differs")
        finally:
            for path, contents in originals.items():
                path.write_bytes(contents)


if __name__ == "__main__":
    unittest.main()
