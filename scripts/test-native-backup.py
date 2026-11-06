#!/usr/bin/env python3
"""Native backup integration contracts; no connected phone is used."""
from __future__ import annotations
import importlib.util
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
import xml.etree.ElementTree as ET

TREE = Path(__file__).resolve().parents[1]
ROOT = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else TREE.parents[2]
spec = importlib.util.spec_from_file_location("native_audit", TREE / "scripts/audit-native-backups.py")
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)

class NativeBackupTests(unittest.TestCase):
    def test_native_targets_and_safe_scope(self):
        rows = audit.targets(TREE / "recovery/root/system/etc/twrp.flags")
        names = {row["target"] for row in rows}
        self.assertGreaterEqual(len(rows), 50)
        self.assertTrue({"/data", "/boot", "/init_boot", "/vendor_boot", "/system_image", "/vendor_image",
                         "/efs1", "/efs2", "/efs_oem_backup", "/splash_image"} <= names)
        self.assertFalse({"/userdata_image", "/super", "/sda", "/xbl", "/abl", "/keystore"} & names)

    def test_active_slot_and_logical_alias_resolution(self):
        inventory = {"slot": "a", "partitions": [
            {"name": "boot_a", "bytes": 100, "kind": "gpt"},
            {"name": "boot_b", "bytes": 100, "kind": "gpt"},
            {"name": "system_a", "bytes": 200, "kind": "logical"},
            {"name": "xbl_a", "bytes": 300, "kind": "gpt"}]}
        result = audit.audit(inventory, TREE / "recovery/root/system/etc/twrp.flags")
        targets = {row["target"]: row for row in result["targets"]}
        self.assertEqual(targets["/boot"]["resolved"], "boot_a")
        self.assertEqual(targets["/system_image"]["resolved"], "system_a")
        self.assertTrue(targets["/system_image"]["present"])
        excluded = {row["name"]: row["reason"] for row in result["excluded"]}
        self.assertIn("Inactive slot", excluded["boot_b"])
        self.assertIn("Boot-chain/security", excluded["xbl_a"])

    def test_invalid_inventory_is_rejected(self):
        for inventory in ({"slot": "c", "partitions": []}, {"slot": "a", "partitions": [
            {"name": "../block", "bytes": 1}]}, {"slot": "a", "partitions": [{"name": "boot_a", "bytes": -1}]}):
            with self.assertRaises(ValueError):
                audit.audit(inventory, TREE / "recovery/root/system/etc/twrp.flags")

    def test_retired_theme_cleanup_is_idempotent_and_preserves_wifi(self):
        theme = '''<recovery><pages><page name="advanced"><listbox style="advanced_listbox">
<listitem name="UFS Manager"><action function="page">ufs_manager</action></listitem>
<listitem name="Disable AVB2.0"><action function="set">tw_action=disableAVB2</action></listitem>
<listitem name="Install TWRP App"><action function="set">tw_appinstall_title=1</action></listitem>
</listbox></page><page name="wlan"><text>tw_wifi_connected wifi_status</text></page>
<!-- OP15 UFS Manager pages START --><page name="ufs_manager"/><!-- OP15 UFS Manager pages END -->
</pages></recovery>'''
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "portrait.xml"
            path.write_text(theme)
            command = [sys.executable, str(TREE / "tools/patch_twrp_magisk_theme.py"), str(path)]
            subprocess.run(command, check=True, stdout=subprocess.PIPE)
            first = path.read_text()
            subprocess.run(command, check=True, stdout=subprocess.PIPE)
            self.assertEqual(first, path.read_text())
            self.assertNotIn("ufs_manager", first)
            self.assertNotIn("Disable AVB2.0", first)
            self.assertNotIn("Install TWRP App", first)
            self.assertIn('<page name="wlan"><text>tw_wifi_connected wifi_status</text></page>', first)
            ET.fromstring(first)

    def test_restore_preflight_before_writes_and_incomplete_guard(self):
        manager = (ROOT / "bootable/recovery/partitionmanager.cpp").read_text()
        restore = manager[manager.index("int TWPartitionManager::Run_Restore("):]
        self.assertLess(restore.index("Mount_Current_Storage(true)"), restore.index("kIncomplete"))
        self.assertLess(restore.index("kIncomplete"), restore.index("Restore_Partition(&part_settings)"))
        self.assertLess(restore.index("Validate_Raw_Restore(Full_Filename)"), restore.index("Restore_Partition(&part_settings)"))
        self.assertIn("Validate_Raw_Restore(child_file)", restore)
        backup = manager[manager.index("int TWPartitionManager::Run_Backup("):manager.index("bool TWPartitionManager::Restore_Partition(")]
        self.assertLess(backup.index("kIncomplete"), backup.index("Backup_Partition(&part_settings)"))
        self.assertLess(backup.index("unlink("), backup.index("backup_completed="))
        self.assertIn("HasCapacity(free_space, total_bytes)", backup)

    def test_raw_io_does_not_truncate_or_discard_block_targets(self):
        source = (ROOT / "bootable/recovery/partition.cpp").read_text()
        raw = source[source.index("bool TWPartition::Raw_Read_Write("):source.index("bool TWPartition::Backup_Dump_Image(")]
        self.assertNotIn("BlkDiscard();", raw)
        self.assertNotIn("O_TRUNC", raw)
        self.assertIn("O_EXCL", raw)
        self.assertIn("BLKROGET", raw)
        self.assertIn("ExactIo", raw)
        self.assertIn("if ((restoring || !part_settings->adbbackup) && fsync(dest_fd) != 0)", raw)
        self.assertIn("part_settings->adbbackup ? 0 : (O_CREAT | O_EXCL)", raw)
        self.assertLess(raw.index("BlockIsSafe"), raw.index("dest_fd = open"))

    def test_terminal_helper_uses_native_workflow(self):
        helper = (TREE / "recovery/root/system/bin/twrp-partition-backup").read_text()
        self.assertIn("exec /system/bin/twrp changepage=backup", helper)
        self.assertNotIn("dd if=", helper)

if __name__ == "__main__":
    unittest.main(argv=[sys.argv[0]], verbosity=2)
