#!/usr/bin/env python3
"""Verify the actual AVB-footed image, native dashboard and retained helpers.

No device or flashing. Reuses the project's bounded ramdisk reader; does not
extract arbitrary archive paths into the host filesystem.
"""
from __future__ import annotations
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import struct
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET

DEVICE=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location("gpu_verifier",DEVICE/"scripts/verify-gpu-image.py")
reader=importlib.util.module_from_spec(spec);spec.loader.exec_module(reader)


def canonical(n):
    if n is None:raise RuntimeError("Missing native dashboard XML element")
    return ET.canonicalize(ET.tostring(n,encoding="unicode"),strip_text=True)


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument("image",type=Path)
    p.add_argument("--root",type=Path,default=DEVICE.parents[2]);p.add_argument("--json",type=Path);a=p.parse_args()
    root=a.root.resolve();image=a.image.resolve();board=(DEVICE/"BoardConfig.mk").read_text()
    limit=int(re.search(r'BOARD_RECOVERYIMAGE_PARTITION_SIZE\s*:?=\s*(0x[0-9a-fA-F]+|\d+)',board)[1],0)
    size=image.stat().st_size
    if size>limit:raise RuntimeError(f"Image {size} exceeds the unchanged {limit}-byte partition")
    with image.open("rb") as f:f.seek(-64,2);footer=f.read(64)
    magic,major,minor,original,offset,vbmeta,_=struct.unpack(">4sIIQQQ28s",footer)
    if magic!=b"AVBf" or major!=1 or not 0<original<=offset<offset+vbmeta<=size-64:raise RuntimeError("Invalid/incomplete AVB footer geometry")
    avb=root/"external/avb/avbtool.py"
    # avbtool resolves the recovery hash descriptor by partition basename. A
    # custom artifact filename must not make it verify some neighboring image.
    with tempfile.TemporaryDirectory(prefix="twrp-oxygenos-avb-") as directory:
        canonical_image=Path(directory)/"recovery.img"
        canonical_image.symlink_to(image)
        result=subprocess.run([sys.executable,str(avb),"verify_image","--image",str(canonical_image),"--key",str(root/"external/avb/test/data/testkey_rsa2048.pem")],capture_output=True,text=True)
        if result.returncode:raise RuntimeError("AVB signature/payload verification failed:\n"+result.stdout+result.stderr)
    info=subprocess.check_output([sys.executable,str(avb),"info_image","--image",str(image)],text=True)
    if "SHA256_RSA2048" not in info:raise RuntimeError("Unexpected AVB algorithm")
    max_payload=int(subprocess.check_output([sys.executable,str(avb),"add_hash_footer","--partition_size",str(limit),"--calc_max_image_size"],text=True).strip())
    manifest=json.loads((DEVICE/"assets/twrp-theme/oxygenos/manifest.json").read_text())
    with tempfile.TemporaryDirectory(prefix="twrp-oxygenos-image-") as directory:
        subprocess.run([sys.executable,str(root/"system/tools/mkbootimg/unpack_bootimg.py"),"--boot_img",str(image),"--out",directory],check=True,stdout=subprocess.PIPE,timeout=30)
        ramdisk=Path(directory)/"ramdisk";names=set(reader.archive(ramdisk,"-it").decode().splitlines())
        def get(name):
            if name not in names:raise RuntimeError("Missing packaged file: "+name)
            return reader.archive(ramdisk,"-i","--to-stdout",name)
        packed_ui=ET.fromstring(get("twres/ui.xml"));packed_common=ET.fromstring(get("twres/portrait.xml"))
        source=root/"bootable/recovery/gui/theme"
        expected_ui=ET.parse(source/"portrait_hdpi/ui.xml").getroot();expected_common=ET.parse(source/"common/portrait.xml").getroot()
        for path in ("templates/template[@name='oxygenos_status']","templates/template[@name='progress_bar']"):
            if canonical(packed_ui.find(path))!=canonical(expected_ui.find(path)):raise RuntimeError("Stale packaged UI: "+path)
        for page in ("main2","slideout","wlan","advanced","filemanagerlist"):
            path=f"pages/page[@name='{page}']"
            if canonical(packed_common.find(path))!=canonical(expected_common.find(path)):raise RuntimeError("Stale packaged native page: "+page)
        if canonical(packed_common)!=canonical(expected_common):raise RuntimeError('Stale packaged common theme styles or pages')
        if packed_common.find("pages/page[@name='op15_classic_home']") is not None:raise RuntimeError('Removed Classic page remains packaged')
        if packed_common.find("pages/page[@name='main2']/button[@name='oxy_classic']") is not None:raise RuntimeError('Removed Classic shortcut remains packaged')
        if canonical(packed_ui.find("templates/template[@name='page']"))!=canonical(expected_ui.find("templates/template[@name='page']")):raise RuntimeError('Stale shared red page template')
        packed_splash=ET.fromstring(get('twres/splash.xml'))
        expected_splash=ET.parse(source/'portrait_hdpi/splash.xml').getroot()
        if canonical(packed_splash.find("pages/page[@name='splash']"))!=canonical(expected_splash.find("pages/page[@name='splash']")):raise RuntimeError('Stale red splash page')
        if packed_splash.find("resources/image[@name='splashlogo']").get('filename')!='oxy_splash_logo':raise RuntimeError('Splash logo is not the red resource')
        aliases=json.loads((DEVICE/'assets/twrp-theme/oxygenos/shared-controls.json').read_text())
        if packed_ui.find("resources/animation[@name='progress']").get('filename')!='oxy_indeterminate':raise RuntimeError('Streaming progress animation is still the old blue resource')
        for name,meta in aliases.items():
            if packed_ui.find(f"resources/image[@name='{name}']").get('filename')!=meta['asset']:raise RuntimeError('Shared widget resource is stale: '+name)
        for name,m in manifest.items():
            res=packed_ui.find(f"resources/image[@name='{name}']")
            expected=expected_ui.find(f"resources/image[@name='{name}']")
            if canonical(res)!=canonical(expected):raise RuntimeError("Stale packed image resource: "+name)
            data=get("twres/images/"+name+".png")
            if len(data)!=m["bytes"] or hashlib.sha256(data).hexdigest()!=m["sha256"]:raise RuntimeError("Missing/stale PNG: "+name)
        if get("twres/fonts/RobotoCondensed-Regular.ttf")!=(source/"common/fonts/RobotoCondensed-Regular.ttf").read_bytes():raise RuntimeError("Dashboard font is absent or stale")
        if get("twres/images/wifi_status.png")!=(source/"portrait_hdpi/images/wifi_status.png").read_bytes():raise RuntimeError("Existing Wi-Fi icon changed in packaging")
        magisk=get("system/etc/magisk/Magisk.apk")
        if magisk!=(DEVICE/"prebuilts/magisk/Magisk.apk").read_bytes():raise RuntimeError("Bundled Magisk APK is stale or differs from the source prebuilt")
        # This XML branch declares libguitwrp as cc_library_static. Its GUI
        # notifier and DataManager provider both link into the recovery ELF,
        # not a fictional libguitwrp.so. Compare the final stripped executable.
        native=get("system/bin/recovery")
        if b'tw_op15_dashboard_charging' not in native:raise RuntimeError('Native charging-state refresh is missing from the recovery executable')
        if b'tw_op15_dashboard_progress' not in native:raise RuntimeError('Native real-progress formatter is missing from the recovery executable')
        built=root/"out/target/product/infiniti/obj/EXECUTABLES/recovery_intermediates/recovery"
        if native!=built.read_bytes():raise RuntimeError("Stale packaged recovery executable/GUI")
        for marker in (b"tw_op15_dashboard_storage",b"tw_op15_dashboard_crypto",b"tw_op15_dashboard_storage_ready",b"tw_op15_dashboard_battery_valid"):
            if marker not in native:raise RuntimeError("Native dashboard provider/notifier missing: "+marker.decode())
        retained=("twrp-ftp-menu","twrp-avb-tool","twrp-flash-magisk","twrp-wifi-manager","twrp-gpu-start","twrp-decrypt-prereqs","lpdump","lpmake","lpflash","zstd","pigz")
        for tool in retained:
            if not any(n.endswith("/"+tool) for n in names):raise RuntimeError("Existing recovery helper lost: "+tool)
        if any("oxygenos-dashboard-reference" in n or "generate_oxygenos" in n for n in names):raise RuntimeError("Reference/developer artifacts must not ship in recovery")
    report={"result":"PASS","image":str(image),"sha256":hashlib.sha256(image.read_bytes()).hexdigest(),"recovery_elf_sha256":hashlib.sha256(native).hexdigest(),"bundled_magisk_sha256":hashlib.sha256(magisk).hexdigest(),"image_bytes":size,"physical_partition_limit":limit,"final_file_headroom_bytes":limit-size,"avb_original_payload_bytes":original,"avb_max_payload_bytes":max_payload,"payload_growth_headroom_bytes":max_payload-original,"vbmeta_offset":offset,"vbmeta_bytes":vbmeta,"asset_count":len(manifest),"compressed_asset_bytes":sum(m["bytes"] for m in manifest.values()),"note":"AVB reserves/pads the full partition. Final-file slack and pre-footer payload growth capacity are different. GUI is statically linked into the verified recovery ELF. No device validation or flashing performed."}
    if a.json:a.json.write_text(json.dumps(report,indent=2)+"\n")
    print(result.stdout.strip());print(json.dumps(report,indent=2))


if __name__=="__main__":
    try:main()
    except (OSError,RuntimeError,ValueError,ET.ParseError,subprocess.SubprocessError) as e:print("OxygenOS packed image FAILED: "+str(e),file=sys.stderr);sys.exit(1)
