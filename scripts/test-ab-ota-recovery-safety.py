#!/usr/bin/env python3
"""Regression checks for safe A/B OTA recovery handling on OnePlus 15."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path


if len(sys.argv) > 1 and not sys.argv[1].startswith("-"):
    RECOVERY_DIR = Path(sys.argv.pop(1)).resolve()
else:
    RECOVERY_DIR = Path(__file__).resolve().parents[4] / "bootable" / "recovery"

SOURCE = RECOVERY_DIR / "twrpinstall" / "twinstall.cpp"
REPACKER_SOURCE = RECOVERY_DIR / "twrpRepacker.cpp"


class AbOtaRecoverySafetyTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.source = SOURCE.read_text(encoding="utf-8")
        cls.repacker_source = REPACKER_SOURCE.read_text(encoding="utf-8")
        start = cls.source.index("\t\tstd::string ab_binary_name(AB_OTA);")
        end = cls.source.index(
            "\t\t} else {\n\t\t\tstd::string binary_name(\"ui.xml\");", start
        )
        cls.ab_ota_branch = cls.source[start:end]

    def test_success_marker_explains_preserved_payload_recovery(self) -> None:
        self.assertIn(
            "Skipping automatic TWRP reflash after an A/B OTA to preserve "
            "the payload-provided recovery image.",
            self.ab_ota_branch,
        )

    def test_ab_ota_branch_never_overwrites_payload_recovery(self) -> None:
        self.assertNotIn("repacker.Flash_Current_Twrp();", self.ab_ota_branch)
        self.assertNotIn("twrpRepacker repacker;", self.ab_ota_branch)

    def test_virtual_ab_prepare_only_runs_after_success(self) -> None:
        self.assertIn(
            "if (ret_val == INSTALL_SUCCESS &&\n"
            "\t\t\t\tandroid::base::GetBoolProperty(\"ro.virtual_ab.enabled\", false))",
            self.ab_ota_branch,
        )

    def test_failure_explicitly_preserves_recovery_slots(self) -> None:
        self.assertIn(
            "A/B OTA failed; recovery slots were not auto-flashed.",
            self.ab_ota_branch,
        )

    def test_dedicated_recovery_clone_is_disabled_for_every_call_path(self) -> None:
        marker = (
            "Skipping dedicated A/B recovery clone to preserve the "
            "OTA-provided inactive-slot recovery."
        )
        self.assertIn(marker, self.repacker_source)
        start = self.repacker_source.index(
            'if (!slot.empty() && PartitionManager.Find_Partition_By_Path("/recovery")) {'
        )
        end = self.repacker_source.index(
            '\n\tif (!TWFunc::Path_Exists("/ramdisk-files.txt")) {', start
        )
        dedicated_recovery_branch = self.repacker_source[start:end]
        self.assertNotIn('std::string command = "dd bs=1048576', dedicated_recovery_branch)
        self.assertNotIn('dest= root + "_b"', dedicated_recovery_branch)


if __name__ == "__main__":
    unittest.main()
