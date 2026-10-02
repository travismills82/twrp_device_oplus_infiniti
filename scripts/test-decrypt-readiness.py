#!/usr/bin/env python3
"""Check fail-closed Binder readiness and the recovery HAL startup ordering."""
from pathlib import Path
import os
import subprocess
import tempfile
import unittest

TREE = Path(__file__).resolve().parents[1]


class ReadinessTests(unittest.TestCase):
    def test_binder_check_requires_successful_checker(self):
        source = (TREE / 'recovery/root/system/bin/twrp-decrypt-prereqs').read_text()
        function = source.split('binder_service_available() {', 1)[1].split('\nwait_binder_service()', 1)[0]
        function = 'binder_service_available() {' + function
        with tempfile.TemporaryDirectory() as name:
            checker = Path(name) / 'checker'
            script = function.replace('/system/bin/twrp-service-check', str(checker))
            script += '\nbinder_service_available android.hardware.weaver.IWeaver/default\n'
            def run():
                return subprocess.run(['/bin/sh', '-c', script], capture_output=True).returncode
            self.assertNotEqual(run(), 0, 'missing checker must not imply readiness')
            checker.write_text('#!/bin/sh\necho "Service not found"\nexit 1\n')
            checker.chmod(0o755)
            self.assertNotEqual(run(), 0, 'an absent service must not pass substring matching')
            checker.write_text('#!/bin/sh\nexit 0\n')
            self.assertEqual(run(), 0)

    def test_gate_rejects_unrestored_vendor_before_mutations(self):
        source = (TREE / 'recovery/root/system/bin/twrp-decrypt-prereqs').read_text()
        # Isolate the entry checks before mounting persist or touching any HAL.
        entry = source.split('setprop twrp.decrypt.prereq preparing', 1)[1].split('\nmount_persist', 1)[0]
        with tempfile.TemporaryDirectory() as name:
            checker = Path(name) / 'checker'
            checker.write_text('#!/bin/sh\nexit 0\n')
            checker.chmod(0o755)
            for state, succeeds in [('0', False), ('', False), ('1', True)]:
                script = '''setprop() { :; }
set_status() { :; }
fail_prereq() { exit 1; }
getprop() { printf '%s' "$FIXTURE_READY"; }
setprop twrp.decrypt.prereq preparing'''+entry.replace('/system/bin/twrp-service-check', str(checker))
                result = subprocess.run(['/bin/sh', '-c', script], env=dict(os.environ, FIXTURE_READY=state), capture_output=True)
                self.assertEqual(result.returncode == 0, succeeds, result.stderr)

    def test_legacy_nfc_node_cannot_block_crypto_readiness(self):
        source = (TREE / 'recovery/root/system/bin/twrp-decrypt-prereqs').read_text()
        self.assertNotIn('NFC_DEVICE=', source)
        self.assertNotIn('nfc-device-missing', source)
        self.assertNotIn('wait_path()', source)
        self.assertIn('NFC_BINDER="android.hardware.nfc.INfc/default"', source)
        self.assertIn('NXP_NCI_MODULES=', source)
        self.assertIn('NXP_NCI_WAIT_SECONDS=20', source)
        self.assertIn('load_nxp_nci_module', source)
        self.assertIn('wait_nxp_nci_module', source)
        self.assertIn('wait_binder_service "$NFC_BINDER" 45', source)

        secure_element = source.split('set_status preparing-secure-element', 1)[1]
        secure_element = secure_element.split('\nset_status starting-crypto-services', 1)[0]
        for required in (
            'start_service vendor.qseecomd',
            'wait_service_running vendor.qseecomd 20 || fail_prereq',
            'start_service vendor.secure_element',
            'wait_binder_service "$SECURE_ELEMENT_BINDER" 30 || fail_prereq',
            'start_service se_omapi',
            'wait_binder_service "$OMAPI_BINDER" 30 || fail_prereq',
        ):
            self.assertIn(required, secure_element)

    def test_nfc_stack_and_weaver_functional_gate_are_packaged(self):
        root = TREE / 'recovery/root'
        source = (root / 'system/bin/twrp-decrypt-prereqs').read_text()
        self.assertIn('wait_weaver_config 45 || fail_prereq weaver-config-failed', source)
        self.assertIn('/system/bin/twrp-service-check --weaver-config', source)

        manifest = (root / 'vendor/odm/etc/vintf/manifest/nfc-service.xml').read_text()
        self.assertIn('<name>android.hardware.nfc</name>', manifest)
        self.assertIn('<fqname>INfc/default</fqname>', manifest)

        init_rc = (root / 'vendor/odm/etc/init/nfc-service-nxp.rc').read_text()
        self.assertIn('service vendor.nfc_hal_service /odm/bin/hw/android.hardware.nfc-service.nxp', init_rc)
        self.assertIn('disabled', init_rc)
        self.assertIn('seclabel u:r:recovery:s0', init_rc)

        for payload in (
            'vendor/odm/etc/init/nfc-service-nxp.rc',
            'vendor/odm/etc/vintf/manifest/nfc-service.xml',
        ):
            self.assertTrue((root / payload).is_file(), payload)

        self.assertIn('/tmp/vendor_dlkm/lib/modules/nxp-nci.ko', source)
        self.assertNotIn('/system/lib/modules/nxp-nci.ko', source)
        self.assertIn('mount_active_nfc_odm || fail_prereq nfc-odm-mount-failed', source)
        self.assertIn('/dev/block/mapper/odm${slot_suffix}', source)
        self.assertIn('bind_nfc_odm_directory "$NFC_ODM_MOUNT/bin/hw" "$NFC_ODM_BIN"', source)
        self.assertIn('bind_nfc_odm_directory "$NFC_ODM_MOUNT/lib64" "$NFC_ODM_LIB"', source)

    def test_early_init_cannot_start_deferred_hals(self):
        root = TREE / 'recovery/root'
        names = {
            'vendor.nfc_hal_service', 'vendor.secure_element', 'vendor.weaver_nxp',
            'vendor.touch-aidl-2', 'vendor.health-default',
        }
        definitions = {}
        for p in root.rglob('*.rc'):
            current = None
            for line in p.read_text().splitlines():
                if line.startswith('service '):
                    current = line.split()[1]
                    if current in names:
                        definitions[current] = []
                elif line and not line[0].isspace() and not line.startswith('#'):
                    current = None
                elif current in names:
                    definitions[current].append(line.strip())
        self.assertEqual(set(definitions), names)
        for name, options in definitions.items():
            self.assertIn('disabled', options, name)
        init = (root / 'init.recovery.qcom.rc').read_text()
        active = ''
        for line in init.splitlines():
            if line.startswith('on '):
                active = line
            if line.strip() in ('start twrp-touch-start', 'start twrp-decrypt-prereqs', 'start vendor.health-default'):
                self.assertIn('property:twrp.fstab.ready=1', active)


if __name__ == '__main__':
    unittest.main(verbosity=2)
