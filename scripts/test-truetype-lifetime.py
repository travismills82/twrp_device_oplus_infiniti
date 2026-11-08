#!/usr/bin/env python3
"""ASan/UBSan tests of the actual native font implementation, never ADB."""
from pathlib import Path
import argparse
import os
import subprocess
import tempfile

DEVICE=Path(__file__).resolve().parents[1]
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('root',nargs='?',type=Path,default=DEVICE.parents[2])
parser.add_argument('--negative-control',action='store_true')
args=parser.parse_args()
root=args.root.resolve()
clang=root/'prebuilts/clang/host/linux-x86/clang-r547379/bin/clang++'
source=root/'bootable/recovery/minuitwrp/truetype.cpp'
font=root/'bootable/recovery/gui/theme/common/fonts/RobotoCondensed-Regular.ttf'
with tempfile.TemporaryDirectory(prefix='twrp-font-sanitizer-') as temporary:
    directory=Path(temporary)
    def build_and_run(implementation,label):
        binary=directory/label
        command=[str(clang),'-std=gnu++17','-g','-O1','-fsanitize=address,undefined',
                 '-fno-omit-frame-pointer','-ffunction-sections','-fdata-sections',
                 '-Wno-reorder-init-list','-Wno-non-c-typedef-for-linkage',
                 '-include',str(DEVICE/'scripts/truetype-host-compat.hpp')]
        command += ['-I'+str(root/path) for path in (
            'bootable/recovery/minuitwrp/include','bootable/recovery/gui/include',
            'bootable/recovery/libpixelflinger/include','external/freetype/include',
            'bootable/recovery/minuitwrp','bootable/recovery')]
        command += [str(DEVICE/'scripts/test-truetype-lifetime.cpp'),str(implementation),
                    '-l:libfreetype.so.6','-pthread','-Wl,--gc-sections','-o',str(binary)]
        subprocess.run(command,check=True,timeout=90)
        environment=dict(os.environ,ASAN_OPTIONS='detect_leaks=1',UBSAN_OPTIONS='halt_on_error=1')
        return subprocess.run([str(binary),str(font),'glyphs'],env=environment,
                              capture_output=True,text=True,timeout=90)
    result=build_and_run(source,'font-fixed')
    if result.returncode:
        raise SystemExit(result.stdout+result.stderr)
    print(result.stdout.strip())
    if args.negative_control:
        # A disposable generated control, never a checkout edit. HEAD is the
        # pinned pre-patch XML-recovery source that contains the original bug.
        baseline=directory/'truetype-original.cpp'
        baseline.write_bytes(subprocess.check_output(
            ['git','-C',str(root/'bootable/recovery'),'show','HEAD:minuitwrp/truetype.cpp']))
        control=build_and_run(baseline,'font-original')
        if control.returncode==0 or 'heap-use-after-free' not in control.stderr:
            raise SystemExit('Original font cleanup did not reproduce the expected ASan fault')
        print('Negative control PASS: original font cleanup reproduces heap-use-after-free')
