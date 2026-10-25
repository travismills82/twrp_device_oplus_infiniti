#!/usr/bin/env python3
"""Regression checks for OnePlus 15 recovery ADB sideload USB ownership."""

from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path


if len(sys.argv) > 1 and not sys.argv[1].startswith("-"):
    USB_RC = Path(sys.argv.pop(1)).resolve()
else:
    USB_RC = (
        Path(__file__).resolve().parents[1]
        / "recovery/root/init.recovery.usb.rc"
    )


class SideloadUsbTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.source = USB_RC.read_text(encoding="utf-8")
        cls.blocks = re.split(r"(?=^on )", cls.source, flags=re.MULTILINE)

    def test_sideload_never_starts_regular_adbd(self) -> None:
        sideload_blocks = [
            block
            for block in self.blocks
            if "property:sys.usb.config=sideload" in block
        ]
        self.assertTrue(sideload_blocks)
        self.assertTrue(all("start adbd" not in block for block in sideload_blocks))

    def test_sideload_waits_for_minadbd_functionfs_ready(self) -> None:
        self.assertIn(
            "on property:sys.usb.ffs.ready=1 && "
            "property:sys.usb.config=sideload && property:sys.usb.configfs=1",
            self.source,
        )
        self.assertIn(
            "symlink /config/usb_gadget/g1/functions/ffs.adb "
            "/config/usb_gadget/g1/configs/b.1/f1",
            self.source,
        )

    def test_normal_adb_still_starts_regular_adbd(self) -> None:
        self.assertIn(
            "on property:sys.usb.config=adb && property:sys.usb.configfs=1\n"
            "    start adbd",
            self.source,
        )

    def test_none_resets_functionfs_before_a_new_sideload(self) -> None:
        self.assertIn(
            "on property:sys.usb.config=none && property:sys.usb.configfs=1\n"
            "    setprop sys.usb.ffs.ready 0",
            self.source,
        )


if __name__ == "__main__":
    unittest.main()
