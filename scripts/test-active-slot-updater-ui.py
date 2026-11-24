#!/usr/bin/env python3
"""Contracts for generated native TWRP updater pages and their live handlers."""
from pathlib import Path
import json
import sys
import xml.etree.ElementTree as ET

device = Path(__file__).resolve().parents[1]
source = Path(sys.argv[1]).resolve() / "bootable/recovery"
theme = ET.parse(source / "gui/theme/common/portrait.xml")
ui = ET.parse(source / "gui/theme/portrait_hdpi/ui.xml")
home = theme.find("pages/page[@name='main2']")
tile = home.find("button[@name='oxy_updates']")
assert tile is not None and home.find("button[@name='oxy_reboot']") is None
assert tile.find("placement").attrib == {"x":"802","y":"904"}
assert tile.find("image").attrib == home.find("button[@name='oxy_advanced']/image").attrib
assert tile.find("condition[@var1='tw_op15_update_state']") is None
assert [(a.get("function"),a.text) for a in tile.iter("action")] == [
    ("page","op15_updates"),("op15updater","open")]
states = []
for image in home.findall("image"):
    state = image.find("condition[@var1='tw_op15_update_state']")
    if state is not None:
        assert image.find("placement").attrib == {"x":"885","y":"914"}
        states.append((state.get("var2"),state.get("op","="),image.find("image").get("resource")))
assert states == [("available","!=","oxy_icon_install_64"),
                  ("available","=","oxy_icon_update_available_64")]
for _,_,resource in states:
    assert ui.find("resources/image[@name='"+resource+"']") is not None
assert not any(ui.find(f"resources/image[@name='oxy_update_{color}']") is not None
               for color in ("blue","green","red"))
labels = [n for n in home.findall("text") if n.findtext("text") in ("Check for","TWRP Updates")]
assert " ".join(n.findtext("text") for n in labels) == "Check for TWRP Updates"
assert [n.find("placement").attrib for n in labels] == [
    {"x":"917","y":"980","placement":"5"},{"x":"917","y":"1011","placement":"5"}]
assert ui.find("variables/variable[@name='tw_op15_update_preview']") is None
assert ui.find("variables/variable[@name='tw_op15_update_state']").get("value") == "offline"
for name in ("oxy_system","oxy_recovery","oxy_bootloader","oxy_fastbootd"):
    assert home.find(f"button[@name='{name}']") is not None
for name in ("op15_updates","op15_update_notes","reboot"):
    assert theme.find(f"pages/page[@name='{name}']") is not None
for name,back in (("op15_updates","main"),("op15_update_notes","op15_updates")):
    update_page = theme.find(f"pages/page[@name='{name}']")
    assert update_page.find("template[@name='page']") is not None
    assert not any(b.findtext("text", "").startswith(("Back","Preview channel"))
                   for b in update_page.findall("button"))
    navigation = {}
    for widget in update_page.findall("action"):
        key = widget.find("touch[@key]")
        if key is not None:
            # NotifyVarChange dispatches conditioned GUIActions even on page entry.
            assert widget.find("condition") is None and widget.find("conditions") is None
            action = widget.find("action[@function='op15updater']")
            assert action is not None
            navigation[key.get("key")] = action.text
    assert navigation == {"home":"nav:main","back":"nav:"+back}
page = theme.find("pages/page[@name='op15_updates']")
title = page.find("text[text='TWRP Recovery Updates']")
assert title.find("placement").attrib == {"x":"190","y":"98"}
font = ui.find("resources/font[@name='" + title.find("font").get("resource") + "']")
assert font.get("bold") == "1" and int(font.get("size")) > 38
assert page.find("progressbar/data[@name='tw_op15_update_progress']") is not None
install = next(b for b in page.findall("button") if b.findtext("action") == "install")
assert install.findtext("text") == "Download & Install"
assert install.get("style") == "main_button_half_height_full_width"
assert install.find("condition[@var1='tw_op15_update_state']").get("var2") == "available"
assert install.find("condition[@var1='tw_busy']").get("var2") == "0"
assert [a.text for a in theme.findall(".//action[@function='op15updater']")].count("install") == 1
review = page.find("button[text='View Release Notes']")
assert review.find("action[@function='page']").text == "op15_update_notes"
notes = theme.find("pages/page[@name='op15_update_notes']")
assert notes.find("text[text=\"What's new\"]") is not None
assert notes.find("textbox[@multiline='1']/text").text == "%tw_op15_update_notes%"
assert "value.find('\\n', start)" in (source / "gui/textbox.cpp").read_text()
for action in ("check","install"):
    assert page.find(f".//action[@function='op15updater'][.='{action}']") is not None
assert "ADD_ACTION(op15updater)" in (source / "gui/action.cpp").read_text()
assert "op15_updater_gui::Instance().Apply();" in (source / "gui/gui.cpp").read_text()
assert 'backup_exclusions.add_absolute_dir("/data/twrp/updater");' in (source / "partition.cpp").read_text()
runtime = (device / "updater/gui.hpp").read_text()
assert 'mode.c_str(),"stable"' in runtime and '"preview"' not in runtime
assert 'if (action == "nav:main" || action == "nav:op15_updates") {\n' in runtime
assert 'if (DataManager::GetIntValue("tw_busy")) return 0;\n            return gui_changePage(' in runtime
assert "waitpid(pid_,&status,WNOHANG)" in runtime and "O_NONBLOCK" in runtime
assert 'if (ok && verified_ && error_.empty())' in runtime
assert runtime.count('SetValue("tw_reboot_arg","recovery")') == 1
assert 'Start("install",offer_)' in runtime and runtime.count('Start("install",offer_)') == 1
assert 'if (action == "install") {\n            if (offer_.empty()' in runtime
assert 'if (action == "open" && !offer_.empty()) return 0;' in runtime
assert 'key == "notes_items"' in runtime and "op15_update_notes::Bullets(value)" in runtime
identity = json.loads((device / "updater/identity.json").read_text())
assert identity["partition_bytes"] == 104857600 and identity["device"] == "infiniti"
backend = (device / "updater/main.cpp").read_text()
assert "Partition(target,true)" in backend and backend.count("Partition(target,true)") == 1
assert 'Receipt(dir,journal,"writing")' in backend and 'Receipt(dir,journal,"verified")' in backend
assert 'renameat(dir,"receipt.json",dir,"last-success.json")' in backend
assert '"--proto","=https","--proto-redir","=https"' in backend and "--insecure" not in backend
print("PASS: review-only tile, explicit install button, multiline notes and isolated write/reboot contracts")
