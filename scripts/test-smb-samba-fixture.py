#!/usr/bin/env python3
"""Real SMB/FUSE transport test. Run in a disposable user/net/mount namespace.

unshare -Ur --map-auto -nm sh -c 'ip link set lo up &&
    python3 /absolute/test-smb-samba-fixture.py /absolute/host/twrp-smb-client'
"""
import hashlib
import os
from pathlib import Path
import signal
import socket
import subprocess
import sys
import tempfile
import threading
import time

if os.geteuid() != 0:
    raise SystemExit("Use an isolated mapped root namespace; see the module docstring")

client = Path(sys.argv[1]).resolve()
with tempfile.TemporaryDirectory(prefix="twrp-samba-fixture-") as temp:
    root = Path(temp)
    root.chmod(0o711)
    for name in ("private", "state", "cache", "lock", "pid", "rpc", "mount", "share"):
        (root / name).mkdir()
    (root / "share").chmod(0o777)
    cfg = root / "smb.conf"
    with socket.socket() as reservation:
        reservation.bind(("127.0.0.1", 0))
        port = reservation.getsockname()[1]
    max_protocol = os.environ.get("TWRP_SMB_FIXTURE_PROTOCOL", "SMB3_11")
    assert max_protocol in ("SMB3_11", "SMB2_10")
    auth_only = os.environ.get("TWRP_SMB_REQUIRE_AUTH") == "1"
    guest_ok = "no" if auth_only else "yes"
    cfg.write_text(f"""[global]
interfaces = 127.0.0.1
bind interfaces only = yes
smb ports = {port}
server min protocol = SMB2_10
server max protocol = {max_protocol}
passdb backend = tdbsam:{root}/private/passdb.tdb
private dir = {root}/private
state directory = {root}/state
cache directory = {root}/cache
lock directory = {root}/lock
pid directory = {root}/pid
ncalrpc dir = {root}/rpc
log file = {root}/log
load printers = no
disable spoolss = yes
map to guest = {"Never" if auth_only else "Bad User"}
restrict anonymous = {2 if auth_only else 0}
guest account = nobody
server signing = auto
[Fixture]
path = {root}/share
guest ok = {guest_ok}
read only = no
[ReadOnlyFixture]
path = {root}/share
guest ok = {guest_ok}
read only = yes
[AuthenticatedFixture]
path = {root}/share
guest ok = no
valid users = root
read only = yes
""")
    secret = "fixture, with spaces!'\";"
    subprocess.run(["smbpasswd", "-c", str(cfg), "-s", "-a", "root"],
                   input=f"{secret}\n{secret}\n", text=True, capture_output=True, check=True)
    startup_path = root / "startup.log"
    with startup_path.open("wb") as startup:
        server = subprocess.Popen(["smbd", "-F", "--no-process-group", "-s", str(cfg), "--debug-stdout", "-d", "1"],
                                  start_new_session=True, stdout=startup, stderr=subprocess.STDOUT)
    mount = root / "mount"
    env = dict(os.environ, TWRP_SMB_TEST_TARGET=str(mount))

    def call(mode, share="", user="", password=""):
        args = ["127.0.0.1", str(port), share, user, password, ""]
        data = ("\0".join(args) + "\0").encode()
        return subprocess.run([client, mode], input=data, capture_output=True, env=env, timeout=25)

    try:
        for _ in range(100):
            try:
                with socket.create_connection(("127.0.0.1", port), .2):
                    break
            except OSError:
                time.sleep(.05)
        else:
            raise AssertionError("Disposable loopback Samba never started:\n" + startup_path.read_text()[-4000:])
        reply = call("shares", user="root", password=secret)
        assert reply.returncode == 0, (reply.returncode, "authenticated share enumeration failed")
        assert b"Fixture" in reply.stdout.splitlines()
        assert b"ReadOnlyFixture" in reply.stdout.splitlines()
        guest_listing = call("shares")
        assert guest_listing.returncode == (3 if auth_only else 0), (
            guest_listing.returncode, "guest share enumeration classification")
        if auth_only:
            assert not guest_listing.stdout and not guest_listing.stderr
        denied_share = call("fixture-probe", "AuthenticatedFixture")
        assert denied_share.returncode == 3 and not denied_share.stdout, (
            denied_share.returncode, "protected share did not return an authentication denial")
        dialect = b"0311\n" if max_protocol == "SMB3_11" else b"0210\n"
        logins = [("root", secret)] + ([] if auth_only else [("", "")])
        for user, password in logins:
            probe = call("fixture-probe", "Fixture", user, password)
            assert probe.returncode == 0 and probe.stdout == dialect, (
                probe.returncode, "dialect or login mismatch", "signed" if user else "guest")
        rejected = call("shares", user="root", password="incorrect")
        assert rejected.returncode == 3 and not rejected.stdout and not rejected.stderr, (
            rejected.returncode, len(rejected.stdout), len(rejected.stderr))
        print(f"PASS: {max_protocol} {'protected' if auth_only else 'guest-visible'} server, private share, signed login and wrong-password rejection")
        read_only = call("mount", "ReadOnlyFixture", "root", secret)
        assert read_only.returncode == 0
        try:
            (mount / "must-not-create").touch(exist_ok=False)
        except OSError:
            pass
        else:
            raise AssertionError("Read-only share accepted write")
        assert not (root / "share/must-not-create").exists()
        subprocess.run(["umount", str(mount)], check=True)
        mounted = call("mount", "Fixture", "root", secret)
        assert mounted.returncode == 0 and mounted.stdout == b"mounted\n", (
            mounted.returncode, "FUSE mount failed")
        line = next(line for line in Path("/proc/self/mountinfo").read_text().splitlines()
                    if line.split()[4] == str(mount))
        assert " - fuse.twrp-smb twrp-smb " in line
        assert {"nosuid", "nodev", "noexec"} <= set(line.split()[5].split(","))
        data = mount / "TWRP/BACKUPS/fixture/one"
        data.mkdir(parents=True)
        assert os.statvfs(data).f_bavail > 0
        marker = data / ".twrp-incomplete"
        marker.touch(exist_ok=False)
        archive = data / "boot.emmc.win"
        payload = b"disposable backup fixture" * 8192
        with archive.open("xb") as file:
            file.write(payload)
            file.flush()
            os.fsync(file.fileno())
        digest = hashlib.sha256(payload).hexdigest()
        def verify_archive(path):
            return subprocess.run([client, "fixture-verify-archive", str(path)], capture_output=True, timeout=30)
        receipt = os.getxattr(archive, "user.twrp.written-sha256")
        assert int.from_bytes(receipt[:8], "little") == len(payload)
        assert receipt[8:].hex() == digest
        verified = verify_archive(archive)
        assert verified.returncode == 0, (verified.returncode, "single remote readback failed")
        assert Path(str(archive) + ".sha2").read_text() == f"{digest}  {archive.name}\n"
        split = data / "userdata.f2fs.win000"
        with split.open("xb") as file:
            file.write(payload)
        assert verify_archive(split).returncode == 0
        bad = data / "bad.emmc.win"
        with bad.open("xb") as file:
            file.write(payload)
        with (root / "share" / bad.relative_to(mount)).open("r+b") as file:
            file.write(b"!")
        assert verify_archive(bad).returncode == 6
        assert not Path(str(bad) + ".sha2").exists() and marker.exists()
        nonsequential = data / "nonsequential.emmc.win"
        with nonsequential.open("xb") as file:
            file.seek(64)
            file.write(payload)
        assert verify_archive(nonsequential).returncode == 6 and marker.exists()
        print("PASS: SHA-256 calculated on writes, one verified readback, split naming and corrupted/sparse archive rejection")
        assert hashlib.sha256(archive.read_bytes()).hexdigest() == digest
        assert hashlib.sha256((root / "share" / archive.relative_to(mount)).read_bytes()).hexdigest() == digest
        with (root / "share" / archive.relative_to(mount)).open("r+b") as file:
            file.write(b"!")
        assert hashlib.sha256(archive.read_bytes()).hexdigest() != digest
        marker.unlink()
        sparse = data / "offset-test"
        with sparse.open("xb+") as file:
            file.seek((1 << 32) + 31)
            file.write(b"test")
            file.flush()
            os.fsync(file.fileno())
            assert file.seek(-4, os.SEEK_END) == (1 << 32) + 31 and file.read() == b"test"
        sparse.unlink()
        print("PASS: actual FUSE writes, readback, fsync, statvfs, 64-bit offsets, read-only and corruption checks")

        # A connected HDD share may stop responding briefly during writeback.
        # Pause only this fixture's server, not the mounted FUSE client.
        stalled = data / "stalled.emmc.win"
        with stalled.open("xb", buffering=0) as file:
            os.killpg(server.pid, signal.SIGSTOP)
            resume = threading.Timer(8, os.killpg, (server.pid, signal.SIGCONT))
            try:
                started = time.monotonic()
                resume.start()
                assert file.write(payload) == len(payload)
                os.fsync(file.fileno())
                assert 7 < time.monotonic() - started < 30
            finally:
                resume.cancel()
                os.killpg(server.pid, signal.SIGCONT)
        assert verify_archive(stalled).returncode == 0
        print("PASS: mounted SMB write and SHA-256 verification survive an 8-second server stall")

        marker.touch(exist_ok=False)
        os.killpg(server.pid, signal.SIGTERM)
        server.wait(5)
        try:
            archive.read_bytes()
        except OSError:
            pass
        else:
            raise AssertionError("Lost Samba connection produced a false successful read")
        assert (root / "share" / marker.relative_to(mount)).is_file()
        print("PASS: interrupted share read fails; remote incomplete marker survives")
        with socket.socket() as silent:
            silent.bind(("127.0.0.1", 0))
            silent.listen()
            stop = threading.Event()

            def hold():
                with silent.accept()[0]:
                    stop.wait(16)

            worker = threading.Thread(target=hold, daemon=True)
            worker.start()
            try:
                started = time.monotonic()
                request = "\0".join(("127.0.0.1", str(silent.getsockname()[1]),
                                     "Fixture", "root", secret, "")) + "\0"
                timeout_result = subprocess.run([client, "fixture-probe"], input=request.encode(),
                                                capture_output=True, env=env, timeout=16)
                elapsed = time.monotonic() - started
                assert timeout_result.returncode == 2 and 10 < elapsed < 14, (timeout_result.returncode, elapsed)
                assert not timeout_result.stdout and not timeout_result.stderr
                print("PASS: a silent SMB peer is bounded by the 12-second connection deadline")
            finally:
                stop.set()
                worker.join(2)
    finally:
        if any(line.split()[4] == str(mount) for line in Path("/proc/self/mountinfo").read_text().splitlines()):
            subprocess.run(["umount", str(mount)], check=True)
        if server.poll() is None:
            os.killpg(server.pid, signal.SIGTERM)
            server.wait(5)
