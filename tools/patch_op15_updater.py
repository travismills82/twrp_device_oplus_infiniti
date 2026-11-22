#!/usr/bin/env python3
"""Apply the native updater hooks after the existing recovery patches."""
import argparse
from pathlib import Path
import sys

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("recovery",type=Path)
root = parser.parse_args().recovery.resolve()
changes = {
    "gui/gui.cpp": [
        ('#include "../op15_smb_gui.hpp"', '#include "../op15_smb_gui.hpp"\n#include "../op15_updater_gui.hpp"'),
        ("\t\top15_smb::ApplyUpdates();", "\t\top15_smb::ApplyUpdates();\n"
         "#ifndef TW_NO_NETWORK\n\t\top15_updater_gui::Instance().Apply();\n#endif"),
    ],
    "gui/objects.hpp": [
        ("\tint op15smb(std::string arg);", "\tint op15smb(std::string arg);\n\tint op15updater(std::string arg);"),
    ],
    "gui/action.cpp": [
        ('#include "../op15_smb_gui.hpp"', '#include "../op15_smb_gui.hpp"\n#include "../op15_updater_gui.hpp"'),
        ("\t\t// remember actions that run in the caller thread", "#ifndef TW_NO_NETWORK\n"
         "\t\tADD_ACTION(op15updater);\n#endif\n\n\t\t// remember actions that run in the caller thread"),
        ("int GUIAction::op15smb(std::string arg) {", "int GUIAction::op15updater(std::string arg) {\n"
         "\tif (simulate) return 0;\n\treturn op15_updater_gui::Instance().User(arg);\n}\n\n"
         "int GUIAction::op15smb(std::string arg) {"),
    ],
    "partition.cpp": [
        ('backup_exclusions.add_absolute_dir("/data/twrp/smb"); // Recovery-local SMB credentials must not leave the device in a Data archive.',
         'backup_exclusions.add_absolute_dir("/data/twrp/smb"); // Recovery-local SMB credentials must not leave the device in a Data archive.\n'
         '\t\tbackup_exclusions.add_absolute_dir("/data/twrp/updater"); // Do not capture rollback images or replay transaction receipts.'),
    ],
}
results = {}
for file, edits in changes.items():
    path = root / file
    source = path.read_text()
    for old, new in edits:
        if new in source:
            continue
        if source.count(old) != 1:
            sys.exit(f"Updater integration anchor changed in {file}: {old}")
        source = source.replace(old, new, 1)
    results[path] = source
for path, source in results.items():
    if path.read_text() != source:
        path.write_text(source)
