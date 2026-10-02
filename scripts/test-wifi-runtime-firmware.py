#!/usr/bin/env python3
"""Verify that recovery obtains WLAN firmware from the active phone slot."""

from pathlib import Path
import unittest


TREE = Path(__file__).resolve().parents[1]
ROOT = TREE / "recovery/root"
HELPER = ROOT / "system/bin/twrp-wifi-start"


class WifiRuntimeFirmwareTests(unittest.TestCase):
    def setUp(self):
        self.source = HELPER.read_text()

    def test_wlan_payloads_are_not_embedded_in_recovery(self):
        # These directories previously held the duplicate 39 MiB WLAN payload.
        # Their runtime equivalents are mounted from the active vendor/ODM slot.
        for relative in (
            "vendor/etc/wifi",
            "vendor/odm/etc/wifi",
            "vendor/firmware_mnt/image/qca6490",
        ):
            self.assertFalse((ROOT / relative).exists(), relative)

    def test_active_slot_sources_are_mounted_readonly(self):
        for marker in (
            'WIFI_VENDOR_MOUNT="/tmp/twrp-wifi-vendor"',
            'WIFI_ODM_MOUNT="/tmp/twrp-wifi-odm"',
            'MODEM_PEACH_FIRMWARE="/firmware/image/peach"',
            '"/dev/block/mapper/${partition}${slot_suffix}"',
            'mount -t erofs -o ro',
            'mount -o remount,bind,ro',
            'mount -t tmpfs -o mode=0755,size=256k',
            'mount -o remount,ro "$WIFI_RUNTIME_FIRMWARE"',
            'bind_readonly_directory "$WIFI_VENDOR_MOUNT/etc/wifi" /vendor/etc/wifi',
            'bind_readonly_directory "$WIFI_ODM_MOUNT/etc/wifi" /vendor/odm/etc/wifi',
            'bind_readonly_directory "$WIFI_ODM_MOUNT/etc/wifi" /odm/etc/wifi',
        ):
            self.assertIn(marker, self.source)

    def test_modem_and_odm_firmware_are_linked_without_data_writes(self):
        self.assertIn('ln -sf "$entry" "$dst/${entry##*/}"', self.source)
        self.assertLess(
            self.source.index('link_firmware_tree "$MODEM_PEACH_FIRMWARE"'),
            self.source.index('link_firmware_tree "$WIFI_ODM_MOUNT/etc/wifi/peach"'),
        )
        self.assertNotIn('WLAN_UPDATE_DIR=', self.source)
        self.assertNotIn('/data/vendor/firmware/update/wlan', self.source)
        self.assertNotIn('cp -af', self.source)
        self.assertNotIn('copy_file_if_present', self.source)

    def test_legacy_firmware_lookups_use_the_linked_view(self):
        for target in (
            '/lib/firmware/peach',
            '/vendor/firmware/peach',
            '/vendor/odm/firmware/peach',
        ):
            self.assertIn(target, self.source)
        self.assertIn('linked Peach firmware view is incomplete', self.source)
        self.assertIn('set_status firmware-link-failed', self.source)


if __name__ == "__main__":
    unittest.main(verbosity=2)
