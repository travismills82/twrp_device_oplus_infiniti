#!/usr/bin/env python3
"""Read-only normal-TWRP target audit. No block writes, mounts, or radio calls.

Print JSON to stdout: use --live for a connected rooted Android/recovery, or
--inventory FILE for a previously captured JSON object (for example fixtures).
The inventory deliberately contains no PIN, serial, SIM identifiers or GPT UUIDs.
"""
from __future__ import annotations

import argparse
import json
import re
import shlex
import subprocess
from pathlib import Path

TREE = Path(__file__).resolve().parents[1]
PROTECTED = re.compile(r"^(xbl|abl|uefi|aop|tz|hyp|keymaster|secretkeeper|tme|pvmfw|"
                       r"devcfg|qupfw|shrm|cpucp|dcp|oplus_sec|oplus_storagefw|multiimg|"
                       r"spuservice|qweslicstore|featenabler|pdp|qtvm|imagefv|soccp|"
                       r"apdp|cdt|ocdt|engineering_cdt|keystore|secdata|storsec|ssd|"
                       r"connsec|tzsc|frp|devinfo|dinfo|ddr|dpm|efisp|uefivarstore)")


def targets(path: Path) -> list[dict]:
    result = []
    for line in path.read_text().splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        fields = shlex.split(line)
        if len(fields) < 4 or "backup=1" not in fields[-1].split(";"):
            # 'flags=' prefixes the first attribute, not all attributes.
            if len(fields) < 4 or "backup=1" not in fields[-1].replace("flags=", "", 1).split(";"):
                continue
        options = fields[-1].removeprefix("flags=").split(";")
        display = next((value[8:] for value in options if value.startswith("display=")), fields[0])
        result.append({"target": fields[0], "type": fields[1], "source": fields[2],
                       "name": display, "slotselect": "slotselect" in options,
                       "method": "raw-image" if fields[1] == "emmc" else "files"})
    return result


def audit(inventory: dict, flags: Path) -> dict:
    slot = inventory.get("slot")
    if slot not in ("a", "b"):
        raise ValueError("inventory must identify active slot a or b")
    partitions = inventory.get("partitions")
    if not isinstance(partitions, list):
        raise ValueError("inventory must contain partitions")
    known = {}
    for entry in partitions:
        if not isinstance(entry, dict) or not isinstance(entry.get("name"), str) or not isinstance(entry.get("bytes"), int):
            raise ValueError("invalid partition inventory entry")
        if entry["bytes"] < 0 or not re.fullmatch(r"[A-Za-z0-9_.-]+", entry["name"]):
            raise ValueError("invalid partition name or size")
        known[entry["name"]] = entry
    configured, covered = [], set()
    for entry in targets(flags):
        source = entry["source"].rsplit("/", 1)[-1]
        selected = source + "_" + slot if entry["slotselect"] else source
        if selected not in known and source + "_" + slot in known:
            # Logical image aliases are prepared by TWRP's v2 fstab/liblp path.
            if known[source + "_" + slot].get("kind") == "logical":
                selected = source + "_" + slot
        device = known.get(selected)
        row = dict(entry, resolved=selected, present=device is not None and device["bytes"] > 0)
        if device:
            row["bytes"] = device["bytes"]
            if device["bytes"] > 0:
                covered.add(selected)
        if entry["source"] == "/data/media/0":
            row["resolved"] = "/data/media/0"
            row["present"] = bool(inventory.get("internal_media_available"))
            row["condition"] = "File-level internal media: external/ADB destination only"
        elif source == "userdata":
            row["condition"] = "Decrypted file-level Data; excludes internal media"
        elif entry["method"] == "raw-image":
            row["condition"] = "Full-size image; backup rejects writable mounts; restore rejects mounted/held targets"
        configured.append(row)
    excluded = []
    for name, entry in sorted(known.items()):
        if name in covered:
            continue
        if entry.get("kind") == "lun":
            reason = "Whole UFS LUN: not a normal partition backup/restore target"
        elif name.endswith("_" + ("b" if slot == "a" else "a")):
            reason = "Inactive slot: not automatically exposed or activated"
        elif entry["bytes"] == 0:
            reason = "Absent/zero-size logical placeholder"
        elif name == "userdata":
            reason = "Use decrypted Data and external media backup; raw userdata-to-self is unsafe"
        elif name == "super":
            reason = "Use individual logical image backups; no automatic super/GPT metadata rewrite"
        elif PROTECTED.match(name):
            reason = "Boot-chain/security/device state: no generic safe restore qualification"
        else:
            reason = "Scratch/log/padding or unqualified OEM target: not automatically declared restorable"
        excluded.append({"name": name, "bytes": entry["bytes"], "reason": reason})
    return {"format": "twrp-native-backup-audit-v1", "slot": slot,
            "targets": configured, "excluded": excluded,
            "note": "Presence is not a destructive restore test or a guarantee of EDL-free recovery"}


def live_inventory(serial: str | None) -> dict:
    base = ["adb"] + (["-s", serial] if serial else [])
    def shell(command):
        return subprocess.check_output(base + ["shell", command], text=True, timeout=45)
    if shell("id -u").strip() != "0":
        raise RuntimeError("read-only inventory requires an already-rooted ADB shell")
    slot = shell("getprop ro.boot.slot_suffix").strip().removeprefix("_")
    command = r'''for p in /dev/block/by-name/* /dev/block/mapper/*; do
        [ -b "$p" ] || continue
        node=$(readlink -f "$p"); node=${node##*/}
        root=/sys/class/block/$node
        [ -r "$root/size" ] || continue
        kind=lun
        [ -r "$root/partition" ] && kind=gpt
        [ -r "$root/dm/name" ] && kind=logical
        printf '%s\t%s\t%s\n' "${p##*/}" "$kind" "$(cat "$root/size")"
    done'''
    records = {}
    for line in shell(command).splitlines():
        name, kind, sectors = line.split("\t")
        if kind == "logical" and not name.endswith(("_a", "_b")):
            # Do not mislabel dm-verity/snapshot/cow/default-key plumbing as
            # independent Android logical partitions, or shadow raw userdata.
            continue
        records[name] = {"name": name, "kind": kind, "bytes": int(sectors) * 512}
    media = shell("if [ -d /data/media/0 ] && grep -q ' /data ' /proc/mounts; then echo yes; fi").strip() == "yes"
    return {"slot": slot, "internal_media_available": media, "partitions": list(records.values())}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    selection = parser.add_mutually_exclusive_group(required=True)
    selection.add_argument("--live", action="store_true")
    selection.add_argument("--inventory", type=Path)
    parser.add_argument("--serial")
    parser.add_argument("--flags", type=Path, default=TREE / "recovery/root/system/etc/twrp.flags")
    args = parser.parse_args()
    try:
        inventory = live_inventory(args.serial) if args.live else json.loads(args.inventory.read_text())
        print(json.dumps(audit(inventory, args.flags), indent=2))
    except (ValueError, OSError, RuntimeError, subprocess.SubprocessError) as error:
        parser.exit(1, f"ERROR: {error}\n")


if __name__ == "__main__":
    main()
