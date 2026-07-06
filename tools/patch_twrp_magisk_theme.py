#!/usr/bin/env python3
#
# Patch the generated TWRP portrait theme so Advanced contains the custom
# OnePlus 15 helper entries. This runs from the device tree after the upstream
# theme has been copied to bootable/recovery/gui/theme/common/portrait.xml.
#

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class AdvancedListItem:
    name: str
    marker: str
    xml: str


ADVANCED_ITEMS = (
    AdvancedListItem(
        name="Flash Magisk",
        marker="/system/bin/twrp-flash-magisk init_boot",
        xml='''\n\t\t\t\t<listitem name="Flash Magisk">\n\t\t\t\t\t<actions>\n\t\t\t\t\t\t<action function="set">tw_back=advanced</action>\n\t\t\t\t\t\t<action function="set">tw_action=cmd</action>\n\t\t\t\t\t\t<action function="set">tw_action_param=/system/bin/twrp-flash-magisk init_boot</action>\n\t\t\t\t\t\t<action function="set">tw_text1=Flash bundled Magisk to init_boot?</action>\n\t\t\t\t\t\t<action function="set">tw_text2=This will patch and flash the active slot.</action>\n\t\t\t\t\t\t<action function="set">tw_action_text1=Flashing Magisk...</action>\n\t\t\t\t\t\t<action function="set">tw_complete_text1=Magisk flash complete</action>\n\t\t\t\t\t\t<action function="set">tw_slider_text=Swipe to Flash Magisk</action>\n\t\t\t\t\t\t<action function="page">confirm_action</action>\n\t\t\t\t\t</actions>\n\t\t\t\t</listitem>\n''',
    ),
    AdvancedListItem(
        name="FTP Menu",
        marker="/system/bin/twrp-ftp-menu",
        xml='''\n\t\t\t\t<listitem name="FTP Menu">\n\t\t\t\t\t<actions>\n\t\t\t\t\t\t<action function="editfile">/system/bin/twrp-ftp-menu</action>\n\t\t\t\t\t\t<action function="page">terminalcommand</action>\n\t\t\t\t\t</actions>\n\t\t\t\t</listitem>\n''',
    ),
)


def find_matching_close(text: str, start: int, open_tag: str, close_tag: str) -> int:
    depth = 1
    pos = start
    while depth:
        next_open = text.find(open_tag, pos)
        next_close = text.find(close_tag, pos)
        if next_close == -1:
            return -1
        if next_open != -1 and next_open < next_close:
            depth += 1
            pos = next_open + len(open_tag)
        else:
            depth -= 1
            if depth == 0:
                return next_close
            pos = next_close + len(close_tag)
    return -1


def patch_theme(theme_path: Path) -> int:
    if not theme_path.exists():
        print(f"[advanced-theme] Theme file not found, skipping: {theme_path}")
        return 0

    text = theme_path.read_text(encoding="utf-8")

    page_start = text.find('<page name="advanced">')
    if page_start == -1:
        print("[advanced-theme] Advanced page not found", file=sys.stderr)
        return 1

    page_end = find_matching_close(text, page_start + len('<page name="advanced">'), "<page", "</page>")
    if page_end == -1:
        print("[advanced-theme] Could not find end of Advanced page", file=sys.stderr)
        return 1

    listbox_start = text.find('<listbox style="advanced_listbox">', page_start, page_end)
    if listbox_start == -1:
        print("[advanced-theme] Advanced listbox not found", file=sys.stderr)
        return 1

    listbox_end = find_matching_close(text, listbox_start + len('<listbox style="advanced_listbox">'), "<listbox", "</listbox>")
    if listbox_end == -1 or listbox_end > page_end:
        print("[advanced-theme] Could not find end of Advanced listbox", file=sys.stderr)
        return 1

    inserts = []
    for item in ADVANCED_ITEMS:
        if item.marker in text:
            print(f"[advanced-theme] {item.name} item already present")
        else:
            inserts.append(item.xml)

    if not inserts:
        return 0

    patched = text[:listbox_end] + "".join(inserts) + text[listbox_end:]
    theme_path.write_text(patched, encoding="utf-8")
    print(f"[advanced-theme] Added {len(inserts)} Advanced menu item(s): {theme_path}")
    return 0


def main() -> int:
    if len(sys.argv) != 2:
        print("Usage: patch_twrp_magisk_theme.py <path-to-portrait.xml>", file=sys.stderr)
        return 2
    return patch_theme(Path(sys.argv[1]))


if __name__ == "__main__":
    raise SystemExit(main())
