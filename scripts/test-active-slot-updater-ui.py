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
assert [(a.get("function"),a.text) for a in tile.iter("action")] == [
    ("page","op15_updates"),("op15updater","tile")]
states = {}
for image in home.findall("image"):
    state = image.find("condition[@var1='tw_op15_update_state']")
    if state is not None:
        states[state.get("var2")] = image.find("image").get("resource")
assert states == {
    "checking":"oxy_update_blue","available":"oxy_update_green",
    "installing":"oxy_update_green","failed":"oxy_update_red"}
for resource in set(states.values()):
    assert ui.find("resources/image[@name='"+resource+"']") is not None
assert ui.find("variables/variable[@name='tw_op15_update_preview']").get("value") == "0"
assert ui.find("variables/variable[@name='tw_op15_update_state']").get("value") == "offline"
for name in ("oxy_system","oxy_recovery","oxy_bootloader","oxy_fastbootd"):
    assert home.find(f"button[@name='{name}']") is not None
for name in ("op15_updates","op15_update_notes","reboot"):
    assert theme.find(f"pages/page[@name='{name}']") is not None
page = theme.find("pages/page[@name='op15_updates']")
assert page.find("progressbar/data[@name='tw_op15_update_progress']") is not None
install = next(b for b in page.findall("button") if b.findtext("action") == "install")
assert install.find("condition[@var1='tw_op15_update_state']").get("var2") == "available"
assert install.find("condition[@var1='tw_busy']").get("var2") == "0"
for action in ("check","install","preview"):
    assert page.find(f".//action[@function='op15updater'][.='{action}']") is not None
assert "ADD_ACTION(op15updater)" in (source / "gui/action.cpp").read_text()
assert "op15_updater_gui::Instance().Apply();" in (source / "gui/gui.cpp").read_text()
assert 'backup_exclusions.add_absolute_dir("/data/twrp/updater");' in (source / "partition.cpp").read_text()
runtime = (device / "updater/gui.hpp").read_text()
assert "waitpid(pid_,&status,WNOHANG)" in runtime and "O_NONBLOCK" in runtime
assert 'if (ok && verified_ && error_.empty())' in runtime
assert runtime.count('SetValue("tw_reboot_arg","recovery")') == 1
assert 'Start("install",offer_)' in runtime and runtime.count('Start("install",offer_)') == 1
identity = json.loads((device / "updater/identity.json").read_text())
assert identity["partition_bytes"] == 104857600 and identity["device"] == "infiniti"
backend = (device / "updater/main.cpp").read_text()
assert "Partition(target,true)" in backend and backend.count("Partition(target,true)") == 1
assert 'Receipt(dir,journal,"writing")' in backend and 'Receipt(dir,journal,"verified")' in backend
assert 'renameat(dir,"receipt.json",dir,"last-success.json")' in backend
assert '"--proto","=https","--proto-redir","=https"' in backend and "--insecure" not in backend
print("PASS: generated native pages, tile states, default channel, isolated write and reboot contracts")
