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
        for page in ("main2","slideout","wlan","advanced","filemanagerlist","settings","op15_updates","op15_update_notes"):
            path=f"pages/page[@name='{page}']"
            if canonical(packed_common.find(path))!=canonical(expected_common.find(path)):raise RuntimeError("Stale packaged native page: "+page)
        if canonical(packed_common)!=canonical(expected_common):raise RuntimeError('Stale packaged common theme styles or pages')
        if packed_common.find("pages/page[@name='op15_classic_home']") is not None:raise RuntimeError('Removed Classic page remains packaged')
        if packed_common.find("pages/page[@name='main2']/button[@name='oxy_classic']") is not None:raise RuntimeError('Removed Classic shortcut remains packaged')
        if canonical(packed_ui.find("templates/template[@name='page']"))!=canonical(expected_ui.find("templates/template[@name='page']")):raise RuntimeError('Stale shared red page template')
        progress_path="templates/template[@name='progress_bar']"
        if canonical(packed_ui.find(progress_path))!=canonical(expected_ui.find(progress_path)):
            raise RuntimeError('Stale packaged progress bar or percentage placement')
        language=ET.fromstring(get("twres/languages/en.xml"))
        for key in ("op15_file_count","op15_size_count"):
            if language.find(f".//string[@name='{key}']") is None:
                raise RuntimeError("Packaged backup counter string missing: "+key)
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
        traffic_font="resources/font[@name='oxy_traffic_bold'][@bold='1']"
        if canonical(packed_ui.find(traffic_font))!=canonical(expected_ui.find(traffic_font)):
            raise RuntimeError("Stale bold status-bar traffic font")
        if get("twres/images/wifi_status.png")!=(source/"portrait_hdpi/images/wifi_status.png").read_bytes():raise RuntimeError("Existing Wi-Fi icon changed in packaging")
        magisk=get("system/etc/magisk/Magisk.apk")
        if magisk!=(DEVICE/"prebuilts/magisk/Magisk.apk").read_bytes():raise RuntimeError("Bundled Magisk APK is stale or differs from the source prebuilt")
        # This XML branch declares libguitwrp as cc_library_static. Its GUI
        # notifier and DataManager provider both link into the recovery ELF,
        # not a fictional libguitwrp.so. Compare the final stripped executable.
        native=get("system/bin/recovery")
        helper=get("system/bin/op15-twrp-updater")
        if helper[:6]!=b"\x7fELF\x02\x01" or struct.unpack_from("<H",helper,18)[0]!=183 or b"libcrypto.so\0" not in helper:
            raise RuntimeError("Native updater is not an aarch64 recovery ELF linked to libcrypto")
        if b"op15updater\0" not in native or b"/system/bin/op15-twrp-updater\0" not in native:
            raise RuntimeError("Native updater GUI action is missing from recovery")
        if get("system/etc/op15-updater-identity.json")!=(DEVICE/"updater/identity.json").read_bytes():
            raise RuntimeError("Packaged updater build identity does not match the build input")
        print("Updater executable size:",len(helper),"bytes; standalone LZ4:",
              len(subprocess.check_output(["lz4","-l","-12","-c"],input=helper)),"bytes")
        for counter in (b"/sys/class/net/wlan0/statistics/rx_bytes", b"/sys/class/net/wlan0/statistics/tx_bytes"):
            if counter not in native:raise RuntimeError("Packaged Wi-Fi traffic counter reader is missing")
        for marker in (b"tw_op15_dt2w", b"user.twrp.written-sha256"):
            if marker not in native:raise RuntimeError("Packaged recovery feature missing: "+marker.decode())
        for marker in (b"tw_op15_dashboard_smb_connected", b"tw_op15_dashboard_ftp_connected"):
            if marker not in native:raise RuntimeError("Packaged connection indicator is missing: "+marker.decode())
        curl_wrapper="system/bin/twrp-curl"
        if get(curl_wrapper)!=(DEVICE/"recovery/root"/curl_wrapper).read_bytes():
            raise RuntimeError("Packaged FTP connection registration is stale")
        packaged_policy=Path(directory)/"packed-sepolicy"
        packaged_policy.write_bytes(get("sepolicy"))
        policy=subprocess.check_output([str(root/"out/host/linux-x86/bin/checkpolicy"),"-b","-C","-M",
                                        "-o","-",str(packaged_policy)],text=True,timeout=30)
        allowed=re.search(r"^\(allow recovery proc_net_tcp_udp \(file \(([^)]*)\)\)\)$",policy,re.M)
        if not allowed or not {"open","read"} <= set(allowed[1].split()):
            raise RuntimeError("Packaged recovery policy cannot observe TCP connection state")
        smb_page=packed_common.find("pages/page[@name='smb_browser']")
        smb_entry=packed_common.find("pages/page[@name='advanced']//action[@function='page'][.='smb_browser']")
        if smb_page is None or smb_entry is None or b"tw_smb_status" not in native:
            raise RuntimeError("Native SMB browser and Advanced entry are missing")
        smb_payload={}
        for name in ("system/bin/twrp-smb-client", "system/lib64/libtwrp_smb2.so", "system/lib64/libfuse.so"):
            payload=get(name)
            if payload[:6]!=b"\x7fELF\x02\x01" or struct.unpack_from("<H",payload,18)[0]!=183:
                raise RuntimeError("Expected a 64-bit aarch64 SMB dependency: "+name)
            if name.endswith("/twrp-smb-client") and not all(x in payload for x in (b"libtwrp_smb2.so\0", b"libfuse.so\0")):
                raise RuntimeError("SMB client is missing its FUSE or SMB dependency")
            if name.endswith("/twrp-smb-client") and not all(x in payload for x in (b"libcrypto.so\0", b"user.twrp.written-sha256")):
                raise RuntimeError("SMB client is missing its write-time SHA-256 support")
            if name.endswith("/twrp-smb-client") and b"/tmp/twrp-network-sessions" not in payload:
                raise RuntimeError("SMB client is missing its live session registration")
            smb_payload[name]={"bytes":len(payload),"standalone_lz4_bytes":len(
                subprocess.check_output(["lz4","-l","-12","-c"],input=payload))}
        if b'tw_op15_dashboard_charging' not in native:raise RuntimeError('Native charging-state refresh is missing from the recovery executable')
        if b'tw_op15_dashboard_progress' not in native:raise RuntimeError('Native real-progress formatter is missing from the recovery executable')
        for marker in (b"tw_op15_backup_file_count",b"tw_op15_backup_size_count"):
            if marker not in native:raise RuntimeError("Native backup counter missing: "+marker.decode())
        for config in ("recovery.fstab","twrp.flags"):
            name="system/etc/"+config
            if get(name)!=(DEVICE/"recovery/root"/name).read_bytes():
                raise RuntimeError("Stale packaged device configuration: "+name)
        built=root/"out/target/product/infiniti/obj/EXECUTABLES/recovery_intermediates/recovery"
        if native!=built.read_bytes():raise RuntimeError("Stale packaged recovery executable/GUI")
        for marker in (b"tw_op15_dashboard_storage",b"tw_op15_dashboard_crypto",b"tw_op15_dashboard_storage_ready",b"tw_op15_dashboard_battery_valid"):
            if marker not in native:raise RuntimeError("Native dashboard provider/notifier missing: "+marker.decode())
        retained=("twrp-ftp-menu","twrp-avb-tool","twrp-flash-magisk","twrp-wifi-manager","twrp-gpu-start","twrp-decrypt-prereqs","lpdump","lpmake","lpflash","zstd","pigz")
        for tool in retained:
            if not any(n.endswith("/"+tool) for n in names):raise RuntimeError("Existing recovery helper lost: "+tool)
        if any("oxygenos-dashboard-reference" in n or "generate_oxygenos" in n for n in names):raise RuntimeError("Reference/developer artifacts must not ship in recovery")
    report={"result":"PASS","image":str(image),"sha256":hashlib.sha256(image.read_bytes()).hexdigest(),"recovery_elf_sha256":hashlib.sha256(native).hexdigest(),"bundled_magisk_sha256":hashlib.sha256(magisk).hexdigest(),"image_bytes":size,"physical_partition_limit":limit,"final_file_headroom_bytes":limit-size,"avb_original_payload_bytes":original,"avb_max_payload_bytes":max_payload,"payload_growth_headroom_bytes":max_payload-original,"vbmeta_offset":offset,"vbmeta_bytes":vbmeta,"asset_count":len(manifest),"compressed_asset_bytes":sum(m["bytes"] for m in manifest.values()),"note":"AVB reserves/pads the full partition. Final-file slack and pre-footer payload growth capacity are different. GUI is statically linked into the verified recovery ELF. No device validation or flashing performed."}
    report["smb_payload"]=smb_payload
    if a.json:a.json.write_text(json.dumps(report,indent=2)+"\n")
    print(result.stdout.strip());print(json.dumps(report,indent=2))


if __name__=="__main__":
    try:main()
    except (OSError,RuntimeError,ValueError,ET.ParseError,subprocess.SubprocessError) as e:print("OxygenOS packed image FAILED: "+str(e),file=sys.stderr);sys.exit(1)
