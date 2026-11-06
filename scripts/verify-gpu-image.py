#!/usr/bin/env python3
"""Verify the actual recovery image, especially incremental GUI-library staging."""
from pathlib import Path
import argparse
import hashlib
import subprocess
import sys
import tempfile

DEVICE=Path(__file__).resolve().parents[1]

def archive(ramdisk, *args):
    decoder=subprocess.Popen(['lz4','-dc',str(ramdisk)],stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    try:
        result=subprocess.run(['cpio',*args,'--quiet'],stdin=decoder.stdout,
                              stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=30)
        decoder.stdout.close()
        decoder.wait(timeout=5)
        if result.returncode or decoder.returncode:
            raise RuntimeError('Ramdisk decode/cpio failed: '+result.stderr.decode(errors='replace'))
        return result.stdout
    finally:
        if decoder.poll() is None: decoder.kill(); decoder.wait()

def digest(data): return hashlib.sha256(data).hexdigest()

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('image',type=Path)
    parser.add_argument('--root',type=Path,default=DEVICE.parents[2])
    parser.add_argument('--built-library',type=Path)
    args=parser.parse_args()
    root=args.root.resolve(); image=args.image.resolve()
    library=args.built_library or root/'out/target/product/infiniti/system/lib64/libminuitwrp.so'
    with tempfile.TemporaryDirectory(prefix='twrp-gpu-image-') as directory:
        subprocess.run([sys.executable,str(root/'system/tools/mkbootimg/unpack_bootimg.py'),
                        '--boot_img',str(image),'--out',directory],check=True,stdout=subprocess.PIPE,timeout=30)
        ramdisk=Path(directory)/'ramdisk'
        names=archive(ramdisk,'-it').decode().splitlines()
        if any(name.endswith('/twrp-gpu-render-test') or 'ufs-manager' in name or 'ufsmap' in name for name in names):
            raise RuntimeError('Retired UFS Manager or developer-only GPU test is packaged')
        if any(name.endswith(('libEGL_adreno.so','libGLESv2_adreno.so')) for name in names):
            raise RuntimeError('Vendor GPU blobs must be reused from the active slot, not bundled')
        packed=archive(ramdisk,'-i','--to-stdout','system/lib64/libminuitwrp.so')
        if packed != library.read_bytes():
            raise RuntimeError('Stale/mismatched minuitwrp in ramdisk: packed '+digest(packed)+' != built '+digest(library.read_bytes()))
        if b'GLES compositor initialized:' not in packed or b'libdl_android.so' not in packed:
            raise RuntimeError('Packed minuitwrp has no GLES renderer/namespace dependency')
        for path in ('system/bin/twrp-gpu-start','init.recovery.qcom.rc'):
            content=archive(ramdisk,'-i','--to-stdout',path)
            if content != (DEVICE/'recovery/root'/path).read_bytes():
                raise RuntimeError('Stale GPU startup resource: '+path)
        for path in ('system/bin/twrp-gpu-probe','system/lib64/libdl_android.so'):
            if not archive(ramdisk,'-i','--to-stdout',path).startswith(b'\x7fELF'):
                raise RuntimeError('Missing GPU executable/library: '+path)
        theme=archive(ramdisk,'-i','--to-stdout','twres/portrait.xml')
        if any(marker in theme for marker in (b'ufs_manager',b'tw_ufs_',b'ufsmap')):
            raise RuntimeError('Retired UFS GUI remains in image')
        print('Packed GPU image PASS: renderer byte-identical to build, helper/init current, namespace/probe present, no GPU blob bundle or developer/UFS utility')
        print('minuitwrp SHA-256:',digest(packed))
    return 0

if __name__=='__main__':
    try: sys.exit(main())
    except (OSError,RuntimeError,subprocess.SubprocessError) as error:
        print('GPU image verification FAILED:',error,file=sys.stderr)
        sys.exit(1)
