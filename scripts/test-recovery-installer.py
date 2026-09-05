#!/usr/bin/env python3
"""Run the packaged installer against isolated regular-file partition fixtures."""
from pathlib import Path
import hashlib
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile

PACKAGE = Path(sys.argv.pop(1)).resolve()
FAKE = r'''#!/usr/bin/python3
from pathlib import Path
import os, shutil, subprocess, sys
root = Path(os.environ['INSTALLER_FIXTURE'])
name = Path(sys.argv[0]).name
args = sys.argv[1:]
if name == 'getprop':
    print({'ro.twrp.version': os.environ.get('FIXTURE_TWRP', '3.7.1'),
           'ro.boot.prjname': os.environ.get('FIXTURE_PROJECT', '24863')}.get(args[0], ''))
elif name == 'id':
    print('0')
elif name == 'blockdev':
    if os.environ.get('FIXTURE_SIZE') == 'unavailable': sys.exit(1)
    print(os.environ.get('FIXTURE_SIZE', '104857600'))
elif name == 'dd':
    opts = dict(a.split('=', 1) for a in args if '=' in a)
    target = Path(opts['of']).resolve()
    assert target in ((root/'dev/block/by-name/recovery_a').resolve(),
                      (root/'dev/block/by-name/recovery_b').resolve())
    with (root/'writes').open('a') as f: f.write(target.name+'\n')
    if os.environ.get('FIXTURE_WRITE_FAIL'): sys.exit(1)
    shutil.copyfile(opts['if'], target)
    if os.environ.get('FIXTURE_READBACK_FAIL'):
        with target.open('r+b') as f: f.write(b'bad readback')
elif name == 'unzip':
    result = subprocess.run(['/usr/bin/unzip', *args])
    if result.returncode: sys.exit(result.returncode)
    if '-d' in args and os.environ.get('FIXTURE_CORRUPT'):
        image = Path(args[args.index('-d')+1])/'recovery.img'
        with image.open('r+b') as f: f.write(b'corrupt payload')
elif name == 'sync':
    pass
else:
    raise RuntimeError(name)
'''


class InstallerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='twrp-installer-test-')
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        (self.root/'tmp').mkdir()
        (self.root/'bin').mkdir()
        (self.root/'dev/block/by-name').mkdir(parents=True)
        self.parts = [self.root/'dev/block/by-name'/('recovery_'+s) for s in 'ab']
        for part in self.parts: part.write_bytes(b'original-'+part.name.encode())
        with zipfile.ZipFile(PACKAGE) as z:
            script = z.read('META-INF/com/google/android/update-binary').decode()
            self.sha = z.read('recovery.img.sha256').decode().strip()
        # Substitute only the namespace and fixture file type, never a real /dev path.
        script = script.replace('/tmp/twrp-', str(self.root)+'/tmp/twrp-')
        script = script.replace('/dev/block/', str(self.root)+'/dev/block/')
        script = script.replace('[ -b "$candidate" ]', '[ -f "$candidate" ]')
        self.script = self.root/'update-binary'
        self.script.write_text(script)
        for name in ['getprop', 'id', 'blockdev', 'dd', 'unzip', 'sync']:
            p = self.root/'bin'/name
            p.write_text(FAKE)
            p.chmod(0o755)
        self.env = dict(os.environ, INSTALLER_FIXTURE=str(self.root),
                        PATH=str(self.root/'bin')+':'+os.environ['PATH'])

    def run_installer(self, success=False, writes=0, option=None, **environment):
        args = ['/bin/sh', str(self.script), '3', '1', str(PACKAGE)]
        if option is not None:
            args.append(option)
        result = subprocess.run(args,
                                env=dict(self.env, **environment), capture_output=True,
                                text=True, timeout=45)
        self.assertEqual(result.returncode == 0, success, result.stdout+result.stderr)
        journal = self.root/'writes'
        touched = journal.read_text().splitlines() if journal.exists() else []
        self.assertEqual(len(touched), writes, result.stdout+result.stderr)
        self.assertFalse(list((self.root/'tmp').iterdir()), 'temporary extraction must be removed')
        if writes == 0:
            for p in self.parts:
                if p.exists() and not p.is_symlink():
                    self.assertEqual(p.read_bytes(), b'original-'+p.name.encode())
        return result.stdout

    def test_exact_payload_written_and_verified_in_both_slots(self):
        output = self.run_installer(success=True, writes=2)
        for part in self.parts:
            self.assertEqual(hashlib.sha256(part.read_bytes()).hexdigest(), self.sha)
            self.assertIn('Verified '+part.name, output)

    def test_dry_run_checks_package_without_writing(self):
        self.assertIn('Preflight passed', self.run_installer(success=True, option='--dry-run'))
        self.run_installer(option='--unknown')

    def test_wrong_device_and_android_are_rejected_before_writes(self):
        self.run_installer(FIXTURE_PROJECT='other')
        self.run_installer(FIXTURE_TWRP='')

    def test_corrupt_payload_is_rejected_before_writes(self):
        self.assertIn('checksum mismatch', self.run_installer(FIXTURE_CORRUPT='1'))

    def test_wrong_or_unreadable_partition_size_is_rejected(self):
        self.run_installer(FIXTURE_SIZE='103809024')
        self.run_installer(FIXTURE_SIZE='unavailable')

    def test_missing_slot_is_rejected_before_writes(self):
        self.parts[1].unlink()
        self.run_installer()

    def test_aliasing_slots_are_rejected_before_writes(self):
        self.parts[1].unlink()
        self.parts[1].symlink_to(self.parts[0])
        self.assertIn('same partition', self.run_installer())

    def test_write_failure_stops_before_second_slot(self):
        self.assertIn('Failed to write recovery_a', self.run_installer(writes=1, FIXTURE_WRITE_FAIL='1'))
        self.assertEqual(self.parts[1].read_bytes(), b'original-recovery_b')

    def test_readback_mismatch_stops_before_second_slot(self):
        self.assertIn('Readback mismatch for recovery_a', self.run_installer(writes=1, FIXTURE_READBACK_FAIL='1'))
        self.assertEqual(self.parts[1].read_bytes(), b'original-recovery_b')


if __name__ == '__main__':
    unittest.main(verbosity=2)
