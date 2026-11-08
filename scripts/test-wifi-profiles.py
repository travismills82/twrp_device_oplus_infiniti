#!/usr/bin/env python3
"""Synthetic saved-profile/controller fixtures; never access a phone or real /data."""
from pathlib import Path
import os
import socket
import subprocess
import sys
import tempfile
import threading
import unittest

DEVICE = Path(__file__).resolve().parents[1]
ROOT = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else DEVICE.parents[2]
PROFILE = 'ctrl_interface=/tmp/recovery/sockets\nupdate_config=1\nnetwork={\n ssid="Fixture"\n psk="fixture-only-not-real"\n disabled=1\n}\n'


class WifiProfileTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.build = tempfile.TemporaryDirectory(prefix="wifi-code-")
        cls.binary = Path(cls.build.name) / "fixture"
        fixture = r'''
#define WIFI_MANAGER_HOST_TEST
#include "wifi_manager.cpp"
int main(int argc, char** argv) {
    if (argc != 3) return 64;
    wifi::Paths p;
    const std::string root = argv[2], command = argv[1];
    p.data = root + "/data"; p.parent = p.data + "/twrp"; p.saved = p.parent + "/wifi";
    p.runtime = root + "/ram"; p.mounts = root + "/mounts";
    p.socket = root + "/wpa.sock";
    p.vendor_config = root + "/vendor.conf";
    p.root = p.supplicant = geteuid();
    umask(0077);
    if (command == "prepare") return wifi::Prepare(p) ? 0 : 1;
    if (command == "save") return wifi::Save(p) ? 0 : 1;
    if (command == "read") {
        std::string content;
        return wifi::ReadPrivate(p.saved + "/wpa_supplicant.conf", p.root, content) ? 0 : 1;
    }
    if (command == "parse") {
        std::string content((std::istreambuf_iterator<char>(std::cin)), {});
        printf("%d", wifi::ProfileCount(content)); return 0;
    }
    if (command == "reassociate") {
        const std::string profiles = "header\n0\tFixture\tany";
        if (!wifi::NeedsReassociate("DISCONNECTED", profiles, 0)) return 1;
        if (!wifi::NeedsReassociate("INACTIVE", profiles, 15)) return 2;
        if (wifi::NeedsReassociate("COMPLETED", profiles, 0)) return 3;
        if (wifi::NeedsReassociate("ASSOCIATING", profiles, 0)) return 4;
        if (wifi::NeedsReassociate("DISCONNECTED", "header", 0)) return 5;
        if (wifi::NeedsReassociate("DISCONNECTED", profiles, 1)) return 6;
        return 0;
    }
    return 64;
}
'''
        fixture = '#include <iostream>\n' + fixture
        subprocess.run(["g++", "-std=c++17", "-Wall", "-Wextra", "-Werror", "-Wno-unused-function",
                        "-I", str(DEVICE / "tools"), "-x", "c++", "-", "-o", str(cls.binary)],
                       input=fixture, text=True, check=True)

    @classmethod
    def tearDownClass(cls):
        cls.build.cleanup()

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="wf-")
        self.root = Path(self.temp.name)
        self.data = self.root / "data"
        (self.data / "misc").mkdir(parents=True)
        self.store = self.data / "twrp/wifi"
        self.ram = self.root / "ram"
        self.mounts = self.root / "mounts"
        self.mounts.write_text(f"/dev/block/dm-test {self.data} f2fs rw,inlinecrypt 0 0\n")

    def tearDown(self):
        self.temp.cleanup()

    def run_helper(self, command):
        return subprocess.run([str(self.binary), command, str(self.root)], capture_output=True, text=True, timeout=8)

    def write_profile(self, text=PROFILE):
        self.store.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.store.parent.chmod(0o700)
        path = self.store / "wpa_supplicant.conf"
        path.write_text(text)
        path.chmod(0o600)
        return path

    def test_prepare_loads_saved_network_without_user_storage(self):
        self.write_profile()
        self.assertEqual(self.run_helper("prepare").returncode, 0)
        text = (self.ram / "wpa_supplicant.conf").read_text()
        self.assertIn('ssid="Fixture"', text)
        self.assertIn('disabled=0', text)
        self.assertFalse((self.data / "media").exists())
        self.assertFalse((self.data / "user").exists())
        self.assertEqual((self.ram.stat().st_mode & 0o777), 0o700)
        self.assertEqual(((self.ram / "wpa_supplicant.conf").stat().st_mode & 0o777), 0o600)

    def test_unmounted_data_only_creates_ram_configuration(self):
        self.mounts.write_text("")
        self.assertEqual(self.run_helper("prepare").returncode, 0)
        self.assertFalse(self.store.exists())
        self.assertNotIn("network={", (self.ram / "wpa_supplicant.conf").read_text())

    def test_ram_defaults_preserve_firmware_options_not_vendor_profiles(self):
        (self.root / "vendor.conf").write_text('update_config=0\npmf=1\nsae_pwe=2\nctrl_interface=/wrong\nnetwork={\nssid="NotOurs"\npsk="not-a-real-key"\n}\n')
        self.assertEqual(self.run_helper("prepare").returncode, 0)
        text = (self.ram / "wpa_supplicant.conf").read_text()
        self.assertIn("pmf=1", text)
        self.assertIn("sae_pwe=2", text)
        self.assertIn("update_config=1", text)
        self.assertNotIn("NotOurs", text)
        self.assertNotIn("/wrong", text)

    def test_read_only_or_wrong_mount_is_not_a_save_destination(self):
        for fs, flags in (("f2fs", "ro"), ("tmpfs", "rw"), ("ext4", "noload,ro")):
            self.mounts.write_text(f"x {self.data} {fs} {flags} 0 0\n")
            self.assertNotEqual(self.run_helper("save").returncode, 0)
            self.assertFalse(self.store.exists())

    def test_read_only_data_can_load_an_existing_saved_profile(self):
        self.write_profile()
        (self.store.parent).chmod(0o700)
        self.mounts.write_text(f"x {self.data} f2fs ro 0 0\n")
        self.assertEqual(self.run_helper("prepare").returncode, 0)
        self.assertIn('ssid="Fixture"', (self.ram / "wpa_supplicant.conf").read_text())

    def test_corrupt_saved_profile_falls_back_without_destroying_it(self):
        bad = self.write_profile(PROFILE[:-3])
        before = bad.read_bytes()
        self.assertEqual(self.run_helper("prepare").returncode, 0)
        self.assertEqual(bad.read_bytes(), before)
        self.assertNotIn("network={", (self.ram / "wpa_supplicant.conf").read_text())

    def test_profile_decoder_rejects_truncation_and_missing_ssid(self):
        for text in (PROFILE[:-3], "network={\n}\nupdate_config=1\n", "network={\nssid=x\n", "update_config=0\n"):
            result = subprocess.run([str(self.binary), "parse", str(self.root)], input=text, text=True, capture_output=True, check=True)
            self.assertEqual(result.stdout, "-1")

    def test_profile_decoder_retains_multiple_saved_networks(self):
        self.write_profile(PROFILE + 'network={\nssid="Second"\nkey_mgmt=NONE\n}\n')
        self.assertEqual(self.run_helper("prepare").returncode, 0)
        text = (self.ram / "wpa_supplicant.conf").read_text()
        self.assertIn('ssid="Fixture"', text)
        self.assertIn('ssid="Second"', text)

    def test_supplicant_global_blocks_are_not_mistaken_for_networks(self):
        self.write_profile(PROFILE + 'blockedlist={\n}\nblob-base64-fixture={\nQUJDRA==\n}\n')
        self.assertEqual(self.run_helper("prepare").returncode, 0)
        text = (self.ram / "wpa_supplicant.conf").read_text()
        self.assertIn('ssid="Fixture"', text)
        self.assertIn('blob-base64-fixture={', text)

    def test_symlink_and_hardlink_profiles_are_not_read(self):
        target = self.write_profile()
        original = target.with_name("original")
        target.rename(original)
        target.symlink_to(original)
        self.assertNotEqual(self.run_helper("read").returncode, 0)
        target.unlink()
        os.link(original, target)
        self.assertNotEqual(self.run_helper("read").returncode, 0)

    def test_oversize_or_world_readable_profiles_are_rejected(self):
        path = self.write_profile()
        path.chmod(0o644)
        self.assertNotEqual(self.run_helper("read").returncode, 0)
        path.chmod(0o600)
        path.write_text("x" * (256 * 1024 + 1))
        self.assertNotEqual(self.run_helper("read").returncode, 0)

    def test_atomic_save_uses_real_control_exchange_and_no_secret_output(self):
        self.assertEqual(self.run_helper("prepare").returncode, 0)
        server = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
        server.bind(str(self.root / "wpa.sock"))
        server.settimeout(5)
        requests, errors = [], []

        def respond():
            try:
                for _ in range(2):
                    command, address = server.recvfrom(8192)
                    requests.append(command)
                    if command == b"STATUS":
                        server.sendto(b"wpa_state=COMPLETED\nssid=Fixture\n", address)
                    elif command == b"SAVE_CONFIG":
                        config = self.ram / "wpa_supplicant.conf"
                        config.write_text(PROFILE)
                        config.chmod(0o660)  # Android supplicant's actual save mode.
                        server.sendto(b"OK\n", address)
            except Exception as error:
                errors.append(error)

        thread = threading.Thread(target=respond)
        thread.start()
        result = self.run_helper("save")
        thread.join(timeout=6)
        server.close()
        self.assertFalse(errors)
        self.assertFalse(thread.is_alive())
        self.assertEqual(result.returncode, 0)
        self.assertEqual(requests, [b"STATUS", b"SAVE_CONFIG"])
        saved = self.store / "wpa_supplicant.conf"
        self.assertEqual(saved.stat().st_mode & 0o777, 0o600)
        self.assertIn('ssid="Fixture"', saved.read_text())
        self.assertEqual(result.stdout + result.stderr, "")
        self.assertEqual(list(self.store.glob(".wifi-new-*")), [])

    def test_failed_control_exchange_keeps_previous_backup(self):
        path = self.write_profile()
        before = path.read_bytes()
        self.assertNotEqual(self.run_helper("save").returncode, 0)
        self.assertEqual(path.read_bytes(), before)

    def test_native_gui_preserves_profiles_and_mirrors_controller_status(self):
        action = (ROOT / "bootable/recovery/gui/action.cpp").read_text()
        connect = action.split("int GUIAction::wlanconnect(", 1)[1].split("int GUIAction::wlangetstatus", 1)[0]
        self.assertNotIn('remove_network all', connect)
        self.assertIn('twrp-wifi-manager save', connect)
        self.assertIn('manual.network = network_id', connect)
        self.assertIn('line == "id=" + network_id', connect)
        self.assertIn('!keep && !network.empty()', connect)
        # Save once after authentication, not on every DHCP polling iteration.
        self.assertEqual(connect.count('manual.keep = true;'), 1)
        self.assertEqual(connect.count('twrp-wifi-manager save'), 1)
        self.assertLess(connect.index('if (!connected)'), connect.index('manual.keep = true;'))
        self.assertLess(connect.index('manual.keep = true;'), connect.index('std::string ip_address;'))
        self.assertNotIn('twrp-wifi-manager save', connect.split('std::string ip_address;', 1)[1])
        gui = (ROOT / "bootable/recovery/gui/gui.cpp").read_text()
        self.assertIn('property_get("twrp.wifi.connected"', gui)
        self.assertIn('SetValue("tw_wifi_connected", connected)', gui)
        code = (DEVICE / "tools/wifi_manager.cpp").read_text()
        self.assertIn('FS_IOC_GET_ENCRYPTION_POLICY_EX', code)
        self.assertIn('error == ENODATA', code)
        self.assertIn('Request(p, "SCAN")', code)
        self.assertIn('"/system/bin/dhcpcd", "wlan0"', code)
        self.assertNotIn('/data/media', code)

    def test_android_idle_profiles_trigger_bounded_reassociation(self):
        self.assertEqual(self.run_helper("reassociate").returncode, 0)


if __name__ == "__main__":
    unittest.main(argv=[sys.argv[0]], verbosity=2)
