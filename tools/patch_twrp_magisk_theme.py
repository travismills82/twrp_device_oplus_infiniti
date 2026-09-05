#!/usr/bin/env python3
#
# Patch the generated TWRP portrait theme so Advanced contains the custom
# OnePlus 15 helper entries and does not expose superseded upstream actions.
# This runs from the device tree after the upstream theme has been copied to
# bootable/recovery/gui/theme/common/portrait.xml.
#

from __future__ import annotations

import re
import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class AdvancedListItem:
    name: str
    marker: str
    xml: str


@dataclass(frozen=True)
class AdvancedListItemRemoval:
    name: str
    markers: tuple[str, ...]


REMOVED_ADVANCED_ITEMS = (
    AdvancedListItemRemoval(
        name="Disable AVB2.0",
        markers=("tw_action=disableAVB2", "disable_avb2=Disable AVB2.0"),
    ),
    AdvancedListItemRemoval(
        name="Install TWRP App",
        markers=("tw_appinstall_title", "reboot_install_app_hdr=Install TWRP App"),
    ),
)


ADVANCED_ITEMS = (
    AdvancedListItem(
        name="Charging",
        marker='<action function="page">op15_charging</action>',
        xml='''
				<listitem name="Charging">
					<action function="page">op15_charging</action>
				</listitem>
''',
    ),
    AdvancedListItem(
        name="Flash Magisk",
        marker="/system/bin/twrp-flash-magisk init_boot",
        xml='''
				<listitem name="Flash Magisk">
					<actions>
						<action function="set">tw_back=advanced</action>
						<action function="set">tw_action=cmd</action>
						<action function="set">tw_action_param=/system/bin/twrp-flash-magisk init_boot</action>
						<action function="set">tw_text1=Flash bundled Magisk to init_boot?</action>
						<action function="set">tw_text2=This will patch and flash the active slot.</action>
						<action function="set">tw_action_text1=Flashing Magisk...</action>
						<action function="set">tw_complete_text1=Magisk flash complete</action>
						<action function="set">tw_slider_text=Swipe to Flash Magisk</action>
						<action function="page">confirm_action</action>
					</actions>
				</listitem>
''',
    ),
    AdvancedListItem(
        name="FTP Menu",
        marker="/system/bin/twrp-ftp-menu",
        xml='''
				<listitem name="FTP Menu">
					<actions>
						<action function="editfile">/system/bin/twrp-ftp-menu</action>
						<action function="page">terminalcommand</action>
					</actions>
				</listitem>
''',
    ),
    AdvancedListItem(
        name="AVB Tools",
        marker="/system/bin/twrp-avb-tool",
        xml='''
				<listitem name="AVB Tools">
					<actions>
						<action function="editfile">/system/bin/twrp-avb-tool</action>
						<action function="page">terminalcommand</action>
					</actions>
				</listitem>
''',
    ),
)


LISTITEM_BLOCK_RE = re.compile(
    r"^[ \t]*<listitem\b.*?</listitem>[ \t]*\n?",
    flags=re.MULTILINE | re.DOTALL,
)


def charging_page() -> str:
    items = []
    for label, command in (
        ("Charging status", "status"),
        ("Enable bypass charging", "bypass-on"),
        ("Disable bypass charging", "bypass-off"),
        ("Normal charging / Auto SUPERVOOC", "auto"),
    ):
        items.append(f'''
                <listitem name="{label}">
                    <actions>
                        <action function="set">tw_back=op15_charging</action>
                        <action function="set">tw_action=op15charging</action>
                        <action function="set">tw_action_param={command}</action>
                        <action function="set">tw_action_text1={label}</action>
                        <action function="set">tw_action_text2=</action>
                        <action function="set">tw_complete_text1=Charging result</action>
                        <action function="set">tw_has_cancel=0</action>
                        <action function="set">tw_has_action2=0</action>
                        <action function="set">tw_show_reboot=0</action>
                        <action function="page">action_page</action>
                    </actions>
                </listitem>
''')
    return '''
        <!-- OP15 charging page START -->
        <page name="op15_charging">
            <template name="page"/>
            <text style="text_l">
                <placement x="%col1_x_header%" y="%row3_header_y%"/>
                <text>Charging</text>
            </text>
            <text style="text_m">
                <placement x="%col1_x_header%" y="%row4_header_y%"/>
                <text>Bypass / SUPERVOOC</text>
            </text>
            <listbox style="advanced_listbox">
                <placement x="%indent%" y="%row2a_y%" w="%content_width%" h="%listbox_advanced_height%"/>
''' + "".join(items) + '''
            </listbox>
            <action>
                <touch key="home"/>
                <action function="page">main</action>
            </action>
            <action>
                <touch key="back"/>
                <action function="page">advanced</action>
            </action>
        </page>
        <!-- OP15 charging page END -->
'''


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


def remove_superseded_items(listbox_text: str) -> tuple[str, list[str]]:
    removed: list[str] = []

    def replace(match: re.Match[str]) -> str:
        block = match.group(0)
        for item in REMOVED_ADVANCED_ITEMS:
            if any(marker in block for marker in item.markers):
                removed.append(item.name)
                return ""
        return block

    return LISTITEM_BLOCK_RE.sub(replace, listbox_text), removed


def patch_theme(theme_path: Path) -> int:
    if not theme_path.exists():
        print(f"[advanced-theme] Theme file not found, skipping: {theme_path}")
        return 0

    original_text = theme_path.read_text(encoding="utf-8")
    text = original_text

    page_start = text.find('<page name="advanced">')
    if page_start == -1:
        print("[advanced-theme] Advanced page not found", file=sys.stderr)
        return 1

    page_end = find_matching_close(
        text,
        page_start + len('<page name="advanced">'),
        "<page",
        "</page>",
    )
    if page_end == -1:
        print("[advanced-theme] Could not find end of Advanced page", file=sys.stderr)
        return 1

    listbox_start = text.find(
        '<listbox style="advanced_listbox">',
        page_start,
        page_end,
    )
    if listbox_start == -1:
        print("[advanced-theme] Advanced listbox not found", file=sys.stderr)
        return 1

    listbox_end = find_matching_close(
        text,
        listbox_start + len('<listbox style="advanced_listbox">'),
        "<listbox",
        "</listbox>",
    )
    if listbox_end == -1 or listbox_end > page_end:
        print("[advanced-theme] Could not find end of Advanced listbox", file=sys.stderr)
        return 1

    original_listbox = text[listbox_start:listbox_end]
    cleaned_listbox, removed = remove_superseded_items(original_listbox)
    text = text[:listbox_start] + cleaned_listbox + text[listbox_end:]
    listbox_end = listbox_start + len(cleaned_listbox)

    for item in REMOVED_ADVANCED_ITEMS:
        if item.name in removed:
            print(f"[advanced-theme] Removed superseded {item.name} item")
        else:
            print(f"[advanced-theme] Superseded {item.name} item already absent")

    inserts = []
    for item in ADVANCED_ITEMS:
        if item.marker in text:
            print(f"[advanced-theme] {item.name} item already present")
        else:
            inserts.append(item.xml)

    if inserts:
        text = text[:listbox_end] + "".join(inserts) + text[listbox_end:]
        print(
            f"[advanced-theme] Added {len(inserts)} Advanced menu item(s): "
            f"{theme_path}"
        )

    # Replace the owned page on repeat runs so incremental builds also pick up
    # changed actions. Other pages and upstream menu items retain their content.
    page_pattern = re.compile(
        r"\n[ \t]*<!-- OP15 charging page START -->.*?<!-- OP15 charging page END -->\n",
        re.DOTALL,
    )
    text = page_pattern.sub("\n", text)
    if "</pages>" not in text:
        print("[advanced-theme] Pages container not found", file=sys.stderr)
        return 1
    text = re.sub(r"\s*</pages>", charging_page() + "\t</pages>", text, count=1)

    if text != original_text:
        theme_path.write_text(text, encoding="utf-8")
    else:
        print(f"[advanced-theme] No theme changes needed: {theme_path}")

    return 0


def main() -> int:
    if len(sys.argv) != 2:
        print(
            "Usage: patch_twrp_magisk_theme.py <path-to-portrait.xml>",
            file=sys.stderr,
        )
        return 2
    return patch_theme(Path(sys.argv[1]))


if __name__ == "__main__":
    raise SystemExit(main())
