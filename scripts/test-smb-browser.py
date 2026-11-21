#!/usr/bin/env python3
"""Source and GUI contracts; does not contact a device or network."""
import json
from pathlib import Path
import sys
import unittest
import xml.etree.ElementTree as ET

device = Path(__file__).resolve().parents[1]
root = Path(sys.argv.pop(1)).resolve()
recovery = root / "bootable/recovery"


class Browser(unittest.TestCase):
    def test_smb_uses_bounded_longer_io_timeout_without_extending_login(self):
        client = (device / "smb/client.cpp").read_text()
        main = client[client.index("int main("):]
        self.assertIn("smb2_set_timeout(ctx.get(), 60);", main)
        self.assertLess(main.index("alarm(12);"), main.index("smb2_connect_share("))
        self.assertLess(main.index("smb2_stat(ctx.get(), "), main.index("alarm(0);"))
        self.assertLess(main.index("alarm(0);"), main.index("return Serve(ctx.get());"))

    def test_gui_wires_real_actions_and_masks_password(self):
        xml = ET.parse(recovery / "gui/theme/common/portrait.xml")
        advanced = xml.find(".//page[@name='advanced']")
        self.assertIsNone(advanced.find(".//action[@function='page'][.='extension']"))
        self.assertIsNotNone(advanced.find(".//action[@function='page'][.='smb_browser']"))
        browser = xml.find(".//page[@name='smb_browser']")
        self.assertEqual(len(browser.findall("listbox/listitem")), 24)
        for action in ("backup", "restore", "disconnect", "scan", "parent"):
            self.assertIsNotNone(browser.find(f".//action[@function='op15smb'][.='{action}']"))
        restore = xml.find(".//page[@name='restore']")
        self.assertIsNotNone(restore.find(".//action[@function='op15smb'][.='restore-list']"))
        self.assertIsNotNone(restore.find("fileselector/condition[@var1='tw_smb_storage_selected']"))
        self.assertIsNotNone(restore.find(".//action[@function='readBackup']"))
        password = xml.find(".//page[@name='smb_input_password']")
        self.assertEqual(password.find("input/data").get("mask"), "*")
        self.assertFalse(any("tw_smb_password%" in (n.text or "") for n in xml.findall(".//action")))

    def test_populated_network_rows_are_visible_in_both_pickers(self):
        xml = ET.parse(recovery / "gui/theme/common/portrait.xml")
        for page in ("smb_browser", "restore"):
            rows = xml.findall(f".//page[@name='{page}']/listbox[@smbrows='1']/listitem")
            self.assertEqual(len(rows), 24)
            for index, item in enumerate(rows):
                with self.subTest(page=page, index=index):
                    key = f"tw_smb_row_{index}"
                    self.assertEqual(item.get("name"), key)
                    # An empty operand in GUIObject::isConditionTrue tests presence.
                    # A leading '!' inverts the test and shows the empty rows instead.
                    visible = item.find(f"conditions/condition[@var1='{key}']")
                    self.assertIsNotNone(visible)
                    self.assertEqual(visible.get("var2"), "")
                    self.assertFalse(visible.get("op", "").startswith("!"))

    def test_smb_headers_and_login_controls_do_not_overlap(self):
        xml = ET.parse(recovery / "gui/theme/common/portrait.xml")
        for name in ("smb_browser", "smb_server"):
            header = xml.find(f".//page[@name='{name}']/text/placement")
            self.assertGreaterEqual(int(header.get("x")), 190)
            self.assertLess(int(header.get("y")), 120)
        page = xml.find(".//page[@name='smb_server']")
        buttons = page.findall("button")
        editor_buttons = [n for n in buttons if any(
            (a.text or "").startswith("smb_input_") for a in n.findall("actions/action"))]
        self.assertEqual(len(editor_buttons), 6)
        self.assertTrue(all(b.get("style") == "main_button_half_height_full_width" for b in editor_buttons))
        manifest = json.loads((device / "assets/twrp-theme/oxygenos/manifest.json").read_text())
        height = manifest["oxy_shared_button_full"]["size"][1]
        rows = sorted({int(b.find("placement").get("y")) for b in buttons})
        self.assertTrue(all(end - start >= height + 16 for start, end in zip(rows, rows[1:])))

    def test_smb_browser_action_grid_has_even_spacing_with_or_without_pagination(self):
        xml = ET.parse(recovery / "gui/theme/common/portrait.xml")
        browser = xml.find(".//page[@name='smb_browser']")
        ui = ET.parse(recovery / "gui/theme/portrait_hdpi/ui.xml")
        x = {n.get("name"): n.get("value") for n in ui.findall("variables/variable")}
        manifest = json.loads((device / "assets/twrp-theme/oxygenos/manifest.json").read_text())
        width, height = manifest["oxy_shared_button_half"]["size"]
        listbox = browser.find("listbox")
        font = listbox.find("font")
        self.assertEqual(font.get("resource"), "font_m")
        self.assertGreaterEqual(int(font.get("spacing")), 36)
        listing = listbox.find("placement")
        left, top, list_width, list_height = (int(listing.get(k)) for k in ("x", "y", "w", "h"))
        card = browser.find("image[image]/placement")
        card_resource = browser.find("image/image").get("resource")
        card_width, card_height = manifest[card_resource]["size"]
        self.assertEqual(2 * left + list_width, 1080)
        self.assertGreaterEqual(list_height, 580)
        self.assertEqual(2 * int(card.get("x")) + card_width, 1080)
        self.assertGreaterEqual(top - (int(card.get("y")) + card_height), 16)

        buttons = browser.findall("button")
        self.assertTrue(all(b.get("style") == "main_button_half_height" for b in buttons))
        for view, normal_rows in (("folders", 3), ("connected", 1),
                                  ("servers", 2), ("shares", 2), ("saved", 2)):
            for prev, more in (("0", "0"), ("1", "0"), ("0", "1"), ("1", "1")):
                with self.subTest(view=view, previous=prev, more=more):
                    values = dict(tw_busy="0", tw_smb_busy="0", tw_smb_view=view,
                                  tw_smb_prev=prev, tw_smb_more=more)

                    def visible(button):
                        return all((values[c.get("var1")] == c.get("var2")) != (c.get("op") == "!=")
                                   for c in button.findall("conditions/condition"))

                    rows = {}
                    for b in filter(visible, buttons):
                        p = b.find("placement")
                        xy = int(x[p.get("x").strip("%")]), int(p.get("y"))
                        rows.setdefault(xy[1], []).append((xy[0], b.findtext("text")))

                    ys = sorted(rows)
                    expects_pager = view != "connected" and "1" in (prev, more)
                    self.assertEqual(len(ys), normal_rows + int(expects_pager))
                    self.assertGreaterEqual(ys[0] - (top + list_height), 16)
                    self.assertLessEqual(ys[-1] + height + 16, 1712)  # shared nav
                    gaps = {b - a for a, b in zip(ys, ys[1:])}
                    self.assertLessEqual(len(gaps), 1)
                    self.assertTrue(all(height + 16 <= g <= height + 30 for g in gaps))
                    for row in ys[:normal_rows]:
                        xs = sorted(col for col, _ in rows[row])
                        self.assertEqual(xs, [left, left + list_width - width])
                        self.assertGreaterEqual(xs[1] - (xs[0] + width), 32)
                    if expects_pager:
                        expected = ({"Previous Results"} if prev == "1" else set())
                        expected |= ({"More Results"} if more == "1" else set())
                        self.assertCountEqual((label for _, label in rows[ys[-1]]), expected)

    def test_smb_browser_uses_only_the_shared_navigation_bar(self):
        xml = ET.parse(recovery / "gui/theme/common/portrait.xml")
        for name, back in (("smb_browser", ("op15smb", "back")), ("smb_server", ("page", "smb_browser"))):
            page = xml.find(f".//page[@name='{name}']")
            self.assertIsNotNone(page.find("template[@name='page']"))
            labels = {button.text for button in page.findall("button/text")}
            self.assertTrue({"Back", "Home"}.isdisjoint(labels))
            for key, (function, dest) in (("back", back), ("home", ("page", "main"))):
                handler = next((a for a in page.findall("action")
                                if a.find(f"touch[@key='{key}']") is not None), None)
                self.assertIsNotNone(handler)
                self.assertIsNotNone(handler.find(f"actions/action[@function='{function}'][.='{dest}']"))

    def test_back_from_share_neither_unmounts_nor_changes_backup_storage(self):
        gui = (device / "smb/gui.hpp").read_text()
        back = gui[gui.index('if (op == "back")'):gui.index('if (op == "resume")')]
        self.assertIn('Content("connected")', back)
        self.assertIn('ShowServerOverview()', back)
        self.assertNotIn('Disconnect_Op15_Smb', back)
        self.assertNotIn('tw_storage_path', back)
        xml = ET.parse(recovery / "gui/theme/common/portrait.xml")
        browser = xml.find(".//page[@name='smb_browser']")
        resume = next(b for b in browser.findall("button") if b.findtext("text") == "Resume Share")
        self.assertIsNotNone(resume.find("conditions/condition[@var1='tw_smb_view'][@var2='connected']"))
        self.assertIsNotNone(resume.find("actions/action[@function='op15smb'][.='resume']"))

    def test_guest_denial_opens_login_on_the_ui_thread_and_signin_retries_the_operation(self):
        gui = (device / "smb/gui.hpp").read_text()
        self.assertIn('Connect("shares", {item, "", "", "", "", ""}, true, true)', gui)
        self.assertIn('Connect("mount", {Get("server"), Get("port"), item, "", "", ""}, true, true)', gui)
        self.assertIn('if (rc == LoginRefused)', gui)
        updates = gui[gui.index("inline void ApplyUpdates()"):gui.index("inline int Process(")]
        self.assertIn('PageManager::GetCurrentPage() == "smb_browser"', updates)
        self.assertIn('gui_changePage("smb_server")', updates)
        xml = ET.parse(recovery / "gui/theme/common/portrait.xml")
        login = xml.find(".//page[@name='smb_server']")
        submit = next(b for b in login.findall("button") if b.findtext("text") == "Sign In")
        self.assertIsNotNone(submit.find("actions/action[@function='op15smb'][.='signin']"))

    def test_saved_credentials_are_not_put_in_gui_or_command_arguments(self):
        gui = (device / "smb/gui.hpp").read_text()
        self.assertIn('ProfileLocation(row) != key', gui)
        self.assertNotIn('Set("password", values[4])', gui)
        self.assertNotIn('Set("password", row[4])', gui)
        self.assertIn('const bool remembered = Remember(values)', gui)
        mounted = gui[gui.index('if (out != "mounted\\n"'):]
        self.assertLess(mounted.index('!ListFolders()'), mounted.index('Status(Remember(values)'))
        self.assertIn('backup_exclusions.add_absolute_dir("/data/twrp/smb")',
                      (recovery / "partition.cpp").read_text())

    def test_session_is_native_and_gate_is_preserved(self):
        source = (recovery / "partitionmanager.cpp").read_text()
        self.assertIn('Partition_List->push_back({Op15SmbStorage.Storage_Name', source)
        self.assertIn('if (network) skip_digest = 0;', source)
        self.assertIn('if (network) disable_free_space_check = 0;', source)
        self.assertIn('if (network) check_digest = 1;', source)
        backup = source[source.index('bool TWPartitionManager::Backup_Partition('):]
        self.assertIn('network ? twrpDigestDriver::Verify_Streamed_SMB_Digest(Full_Filename)', backup)
        self.assertNotIn('if (network && !twrpDigestDriver::Check_Digest(Full_Filename, true))', backup)
        self.assertIn('lstat((Restore_Name + twrp_backup_safety::kIncomplete)', source)
        self.assertIn('lstat(marker_path.c_str(), &incomplete) == 0 || errno != ENOENT', source)
        self.assertIn('archive_size > UINT64_MAX - part_settings.total_restore_size', source)
        self.assertIn('umount2(op15_smb::Root, 0)', source)
        self.assertNotIn('MNT_DETACH', source[source.index('bool TWPartitionManager::Disconnect_Op15_Smb'):
                                              source.index('bool TWPartitionManager::Check_Directory_Backup_Destination')])
        config = (device / "recovery/root/system/etc/twrp.flags").read_text()
        self.assertNotIn("/mnt/smb", config)

    def test_no_shell_invocation_or_credentials_in_argv(self):
        gui = (device / "smb/gui.hpp").read_text()
        self.assertIn('{exe, command, nullptr}', gui)
        self.assertIn('Wipe(input)', gui)
        self.assertIn('Queue("tw_smb_" + key, value)', gui)
        self.assertIn('op15_smb::ApplyUpdates()', (recovery / "gui/gui.cpp").read_text())
        self.assertIn('SMB login fields are private.', (recovery / "openrecoveryscript.cpp").read_text())
        self.assertNotIn('popen(', gui)
        self.assertNotIn('system(', gui)
        client = (device / "smb/client.cpp").read_text()
        self.assertIn('smb2_set_password(ctx.get(), user.empty() ? nullptr : password.c_str())', client)
        self.assertIn('nodev,nosuid,noexec', client)
        self.assertIn('smb2_get_dialect(ctx.get()) < 0x0210', client)


if __name__ == "__main__":
    unittest.main(verbosity=2)
