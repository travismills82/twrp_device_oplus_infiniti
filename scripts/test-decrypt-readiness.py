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
        self.assertIn('service vendor.nfc_hal_service /system/bin/twrp-active-hal nfc', init_rc)
        self.assertIn('disabled', init_rc)
        self.assertIn('seclabel u:r:recovery:s0', init_rc)

        for payload in (
            'vendor/odm/etc/init/nfc-service-nxp.rc',
            'vendor/odm/etc/vintf/manifest/nfc-service.xml',
        ):
            self.assertTrue((root / payload).is_file(), payload)

        self.assertIn('/tmp/vendor_dlkm/lib/modules/nxp-nci.ko', source)
        self.assertNotIn('/system/lib/modules/nxp-nci.ko', source)
        self.assertIn('mount_active_partition odm "$LEGACY_NFC_ODM_MOUNT"', source)
        self.assertIn('bind_nfc_odm_directory "$LEGACY_NFC_ODM_MOUNT/bin/hw" "$LEGACY_NFC_ODM_BIN"', source)
        self.assertIn('bind_nfc_odm_directory "$LEGACY_NFC_ODM_MOUNT/lib64" "$LEGACY_NFC_ODM_LIB"', source)

        # The active-slot NCI module must be loaded before legacy-layout
        # detection.  LineageOS 24 keeps its HAL in vendor, not legacy ODM.
        load = source.index('set_status loading-nfc-transport\nload_nxp_nci_module')
        runtime = source.index('prepare_active_nfc_runtime || fail_prereq nfc-runtime-unavailable')
        self.assertLess(load, runtime)

    def test_lineage_active_hal_runtime_is_isolated_and_has_legacy_fallbacks(self):
        root = TREE / 'recovery/root'
        source = (root / 'system/bin/twrp-decrypt-prereqs').read_text()
        wrapper = (root / 'system/bin/twrp-active-hal').read_text()
        linker_config = (root / 'system/etc/twrp-active-hal.ld.config.txt').read_text()

        for required in (
            'ACTIVE_VENDOR_MOUNT="/tmp/twrp-crypto-vendor"',
            'ACTIVE_SYSTEM_MOUNT="/tmp/twrp-crypto-system"',
            'ACTIVE_ODM_MOUNT="/tmp/twrp-crypto-odm"',
            'mount_active_partition vendor "$ACTIVE_VENDOR_MOUNT"',
            'mount_active_partition system "$ACTIVE_SYSTEM_MOUNT"',
            'mount_active_partition odm "$ACTIVE_ODM_MOUNT"',
            'nfc_nci_nxp_snxxx.so',
            'setprop "$ACTIVE_RUNTIME_PROPERTY" lineage',
            'setprop "$ACTIVE_RUNTIME_PROPERTY" legacy',
        ):
            self.assertIn(required, source)

        self.assertIn('export LD_CONFIG_FILE="$ACTIVE_LINKER_CONFIG"', wrapper)
        self.assertIn('unset LD_LIBRARY_PATH LD_PRELOAD', wrapper)
        for active_path in (
            '$ACTIVE_VENDOR_MOUNT/bin/hw/android.hardware.nfc-service.nxp',
            '$ACTIVE_ODM_MOUNT/bin/hw/android.hardware.secure_element-service.qti',
            '$ACTIVE_VENDOR_MOUNT/bin/hw/android.hardware.weaver-service.nxp',
        ):
            self.assertIn(active_path, wrapper)
        for legacy_path in (
            '/odm/bin/hw/android.hardware.nfc-service.nxp',
            '/vendor/bin/hw/android.hardware.secure_element-service.qti',
            '/odm/bin/hw/android.hardware.weaver-service.nxp',
        ):
            self.assertIn(legacy_path, wrapper)

        self.assertLess(linker_config.index('dir.twrp_active_vendor'), linker_config.index('[recovery]'))
        self.assertLess(linker_config.index('dir.twrp_active_odm'), linker_config.index('[recovery]'))
        for required in (
            '[twrp_active_vendor]',
            '[twrp_active_odm]',
            'namespace.default.search.paths = /tmp/twrp-crypto-vendor/lib64',
            'namespace.default.search.paths += /tmp/twrp-crypto-vendor/lib64/hw',
            'namespace.system.search.paths = /tmp/twrp-crypto-system/system/lib64',
            'namespace.default.link.system.allow_all_shared_libs = true',
        ):
            self.assertIn(required, linker_config)

        secure_element_rc = (root / 'vendor/etc/init/android.hardware.secure_element-service.qti.rc').read_text()
        weaver_rc = (root / 'vendor/odm/etc/init/android.hardware.weaver-service.nxp.rc').read_text()
        self.assertIn('service vendor.secure_element /system/bin/twrp-active-hal secure-element', secure_element_rc)
        self.assertIn('service vendor.weaver_nxp /system/bin/twrp-active-hal weaver', weaver_rc)

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
