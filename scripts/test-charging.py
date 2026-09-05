#!/usr/bin/env python3
"""Exercise charging transitions with simulated sysfs; never access a device."""

import os
import re
from pathlib import Path
import subprocess
import tempfile
import unittest
import xml.etree.ElementTree as ET

TREE = Path(__file__).resolve().parents[1]

# Simulate the native ABI's separate write commands/read status, readiness
# acknowledgement, rejected enable requests, and asynchronous disable.
FAKE_COMMAND = r'''#!/usr/bin/env python3
import os, sys
from pathlib import Path
r = Path(os.environ['CHARGING_FIXTURE'])
name = Path(sys.argv[0]).name
args = sys.argv[1:]
plc = r/'sys/class/oplus_chg/common/plc'
ready = r/'sys/class/oplus_chg/common/boot_completed'
proc = r/'proc/ui_soc_decimal'
if name == 'id':
    print('0')
elif name == 'sleep':
    if (r/'disable_pending').exists():
        plc.write_text('status=2\n')
        (r/'disable_pending').unlink()
elif name == 'getprop':
    p = r/'props'/args[0]
    print(p.read_text().strip() if p.exists() else '')
elif name == 'setprop':
    (r/'props'/args[0]).write_text(args[1])
elif name == 'cat':
    p = Path(args[0])
    if p == ready and proc.read_text() == '1\n' and not (r/'reject_ready').exists():
        ready.write_text('1\n')
    if p == plc and plc.exists() and plc.read_text().startswith('switch='):
        command = plc.read_text()
        with (r/'writes').open('a') as f: f.write(command)
        assert command in ('switch=1|callname=twrp\n', 'switch=0|callname=twrp\n')
        if command.startswith('switch=0'):
            plc.write_text('status=4\n')
            (r/'disable_pending').touch()
        else:
            plc.write_text('status=1\n' if (r/'reject_bypass').exists() else 'status=3\n')
    try:
        print(p.read_text(), end='')
    except OSError:
        sys.exit(1)
'''


class ChargingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="twrp-charging-test-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        for name in ("bin", "proc", "sys/class/oplus_chg/common",
                     "sys/class/oplus_chg/battery", "sys/class/power_supply/usb",
                     "sys/class/power_supply/battery", "props"):
            (self.root / name).mkdir(parents=True, exist_ok=True)
        for name in ("id", "sleep", "cat", "getprop", "setprop"):
            path = self.root / "bin" / name
            path.write_text(FAKE_COMMAND)
            path.chmod(0o755)
        self.env = dict(os.environ, CHARGING_FIXTURE=str(self.root),
                        PATH=str(self.root / "bin") + ":" + os.environ["PATH"])
        source = (TREE / "recovery/root/system/bin/twrp-charging").read_text()
        source = re.sub(r"/(?:sys|proc|tmp)/", lambda m: str(self.root) + m[0], source)
        (self.root / "tmp").mkdir()
        self.script = self.root / "twrp-charging"
        self.script.write_text(source)
        self.put("props/ro.twrp.version", "3.7.1")
        self.put("props/twrp.charging.bypass_requested", "0")
        self.put("proc/ui_soc_decimal", "0, 0")
        self.put("sys/class/oplus_chg/common/boot_completed", "1")
        self.put("sys/class/oplus_chg/common/plc", "status=2")
        self.put("sys/class/oplus_chg/common/protocol_type", "2")
        self.put("sys/class/oplus_chg/battery/voocchg_ing", "1")
        self.put("sys/class/oplus_chg/battery/mmi_charging_enable", "1")
        self.put("sys/class/power_supply/usb/online", "1")
        self.protected = {
            "sys/class/oplus_chg/battery/cool_down": "8",
            "sys/class/oplus_chg/battery/normal_cool_down": "4",
            "sys/class/power_supply/usb/input_suspend": "1",
            "sys/class/power_supply/battery/constant_charge_current_max": "1234567",
        }
        for path, value in self.protected.items():
            self.put(path, value)

    def put(self, path, value):
        (self.root / path).write_text(value + "\n")

    def run_helper(self, action, success=True):
        result = subprocess.run(["/bin/sh", str(self.script), action], env=self.env,
                                capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode == 0, success, result.stdout + result.stderr)
        for path, value in self.protected.items():
            self.assertEqual((self.root / path).read_text().strip(), value)
        self.assertFalse((self.root / "tmp/twrp-charging.lock").exists())
        return result.stdout

    def requested(self):
        return (self.root / "props/twrp.charging.bypass_requested").read_text().strip()

    def test_native_bypass_and_asynchronous_disable(self):
        self.assertIn("Bypass active", self.run_helper("bypass-on"))
        self.assertEqual(self.requested(), "1")
        self.assertIn("Bypass off", self.run_helper("bypass-off"))
        self.assertEqual(self.requested(), "0")

    def test_ready_handshake_and_failed_acknowledgement(self):
        self.put("sys/class/oplus_chg/common/boot_completed", "0")
        self.assertIn("driver ready", self.run_helper("prepare"))
        self.assertEqual((self.root / "proc/ui_soc_decimal").read_text(), "1\n")
        self.put("sys/class/oplus_chg/common/boot_completed", "0")
        (self.root / "reject_ready").touch()
        self.assertIn("Read-back did not confirm", self.run_helper("prepare", False))

    def test_android_mutations_refused(self):
        self.put("props/ro.twrp.version", "")
        self.assertIn("require root in TWRP", self.run_helper("bypass-on", False))
        self.assertFalse((self.root / "writes").exists())

    def test_rejected_bypass_clears_request(self):
        (self.root / "reject_bypass").touch()
        self.assertIn("not confirmed", self.run_helper("bypass-on", False))
        self.assertEqual(self.requested(), "0")
        self.assertTrue((self.root / "writes").read_text().endswith("switch=0|callname=twrp\n"))

    def test_unknown_abi_refused(self):
        self.put("sys/class/oplus_chg/common/plc", "enable=1")
        self.assertIn("unknown ABI", self.run_helper("bypass-on", False))
        self.assertFalse((self.root / "writes").exists())

    def test_auto_resumes_normal_charge_without_changing_limits(self):
        self.run_helper("bypass-on")
        self.put("sys/class/oplus_chg/battery/mmi_charging_enable", "0")
        self.assertIn("negotiates automatically", self.run_helper("auto"))
        self.assertEqual(self.requested(), "0")
        self.assertEqual((self.root / "sys/class/oplus_chg/battery/mmi_charging_enable").read_text(), "1\n")

    def test_owned_keepalive_then_driver_stop(self):
        self.run_helper("bypass-on")
        self.run_helper("keepalive")
        self.assertEqual(self.requested(), "1")
        self.put("sys/class/oplus_chg/common/plc", "status=1")
        self.run_helper("keepalive")
        self.assertEqual(self.requested(), "0")
        writes = (self.root / "writes").read_text().splitlines()
        self.assertEqual(writes, ["switch=1|callname=twrp"] * 2 + ["switch=0|callname=twrp"])

    def test_disconnect_ends_session_and_stale_supervooc_is_not_active(self):
        self.run_helper("bypass-on")
        self.put("sys/class/power_supply/usb/online", "0")
        self.run_helper("keepalive")
        self.assertEqual(self.requested(), "0")
        self.assertNotIn("SUPERVOOC active", self.run_helper("status"))

    def test_status_is_read_only_and_requires_active_protocol(self):
        status = self.run_helper("status")
        self.assertIn("SUPERVOOC active", status)
        self.assertIn("current=mA", status)
        self.put("sys/class/oplus_chg/battery/voocchg_ing", "0")
        self.assertNotIn("SUPERVOOC active", self.run_helper("status"))
        self.assertFalse((self.root / "writes").exists())

    def test_menu_idempotence_and_existing_actions(self):
        theme = TREE.parents[2] / "bootable/recovery/gui/theme/common/portrait.xml"
        target = self.root / "portrait.xml"
        target.write_bytes(theme.read_bytes())
        command = ["python3", str(TREE / "tools/patch_twrp_magisk_theme.py"), str(target)]
        subprocess.run(command, check=True, stdout=subprocess.DEVNULL)
        original = target.read_bytes()
        subprocess.run(command, check=True, stdout=subprocess.DEVNULL)
        self.assertEqual(target.read_bytes(), original)
        root = ET.parse(target).getroot()
        page = root.findall('.//page[@name="op15_charging"]')
        self.assertEqual(len(page), 1)
        actions = [x.text for x in page[0].findall('.//action')]
        for command in ("status", "bypass-on", "bypass-off", "auto"):
            self.assertIn("tw_action_param=" + command, actions)
        self.assertEqual(actions.count("tw_action=op15charging"), 4)
        for name in ("Charging", "Flash Magisk", "FTP Menu", "AVB Tools"):
            self.assertEqual(len(root.findall(f'.//page[@name="advanced"]//listitem[@name="{name}"]')), 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
