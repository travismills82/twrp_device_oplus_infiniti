#!/usr/bin/env python3
"""Retired-cellular presentation and native safety contracts; no radio writes.

Historical glyph conditions are checked against the original patch fixtures;
the actual shared status bar must contain no cellular glyphs after retirement.
"""
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET

DEVICE = Path(__file__).resolve().parents[1]
ROOT = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else DEVICE.parents[2]
UI = ROOT / "bootable/recovery/gui/theme/portrait_hdpi/ui.xml"
START = "<!-- OP15 cellular data status icon START -->"
END = "<!-- OP15 cellular data status icon END -->"
SIGNAL_START = "<!-- OP15 cellular signal bars START -->"
SIGNAL_END = "<!-- OP15 cellular signal bars END -->"


class CellularStatusTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = UI.read_text()
        cls.theme = ET.fromstring(cls.source)
        cls.variables = {n.attrib["name"]: n for n in cls.theme.findall("variables/variable")}
        def added_lines(name):
            patch=(DEVICE/'patches/bootable-recovery'/name).read_text()
            return '\n'.join(line[1:] for line in patch.splitlines() if line.startswith('+') and not line.startswith('+++'))
        cls.retired_source=added_lines('0031-theme-cellular-data-status-icon.patch')
        cls.retired_signal=added_lines('0033-theme-visible-cellular-signal-bars.patch')
        fragment = cls.retired_source.split(START, 1)[1].split(END, 1)[0]
        cls.fills = ET.fromstring("<icon>" + fragment + "</icon>").findall("fill")
        signal = cls.retired_signal.split(SIGNAL_START, 1)[1].split(SIGNAL_END, 1)[0]
        cls.signal_fills = ET.fromstring("<icon>" + signal + "</icon>").findall("fill")

    def test_connected_state_defaults_off_and_is_not_persistent(self):
        state = self.variables["tw_cellular_connected"]
        self.assertEqual(state.attrib["value"], "0")
        self.assertNotIn(state.attrib.get("persist", "0"), ("1", "true"))

    def test_every_primitive_requires_connected_state(self):
        self.assertEqual(len(self.fills), 8)
        for fill in self.fills:
            conditions = fill.findall("condition")
            self.assertEqual(len(conditions), 1)
            self.assertEqual(conditions[0].attrib, {"var1": "tw_cellular_connected", "var2": "1"})
        for disconnected in ("", "0", "2", "running", "registered"):
            self.assertFalse(any(disconnected == f.find("condition").attrib["var2"] for f in self.fills))
        self.assertTrue(all("1" == f.find("condition").attrib["var2"] for f in self.fills))

    def test_native_fill_fixtures_stay_small_and_theme_accent_is_red(self):
        self.assertTrue(all(f.attrib["color"] == "%accent_color%" for f in self.fills))
        color = self.variables["accent_color"].attrib["value"].lstrip("#")
        self.assertEqual(len(color), 6)
        red, green, blue = (int(color[i:i+2], 16) for i in (0, 2, 4))
        self.assertGreater(red, blue)
        self.assertGreater(red, green)
        fragment = self.retired_source.split(START, 1)[1].split(END, 1)[0]
        self.assertNotIn("<image", fragment)
        self.assertNotIn("<animation", fragment)

    def test_geometry_fits_status_bar_and_leaves_wifi_unchanged(self):
        boxes = [tuple(int(f.find("placement").attrib[k]) for k in ("x", "y", "w", "h")) for f in self.fills]
        self.assertEqual((min(b[0] for b in boxes), max(b[0]+b[2] for b in boxes)), (607, 643))
        self.assertEqual((min(b[1] for b in boxes), max(b[1]+b[3] for b in boxes)), (28, 60))
        self.assertTrue(all(w > 0 and h > 0 and x+w < 720 for x, y, w, h in boxes))
        status=self.theme.find("templates/template[@name='oxygenos_status']")
        icon=next(n for n in status.findall('image') if n.find('image').get('resource')=='wifi_status')
        self.assertEqual(icon.find("condition").attrib, {"var1": "tw_wifi_connected", "var2": "1"})
        self.assertEqual(icon.find("image").attrib, {"resource": "wifi_status"})
        self.assertEqual(icon.find("placement").attrib, {"x": "800", "y": "2"})

    def test_icon_is_in_shared_page_header_once(self):
        self.assertEqual(self.source.count(START), 0)
        self.assertEqual(self.source.count(END), 0)
        page = self.theme.find("templates/template[@name='page']")
        self.assertIsNotNone(page)
        cell_fills = [f for f in page.findall("fill") if any(c.attrib == {"var1": "tw_cellular_connected", "var2": "1"} for c in f.findall("condition"))]
        self.assertEqual(len(cell_fills), 0)
        self.assertIsNotNone(page.find("template[@name='oxygenos_status']"))
        self.assertFalse(any(c.get('var1','').startswith('tw_cellular_') for c in self.theme.iter('condition')))

    def test_no_fake_signal_strength_or_fixed_radio_technology(self):
        fragment = self.retired_source.split(START, 1)[1].split(END, 1)[0]
        for label in ("4G", "5G", "LTE", "tw_sim_state", "tw_modem_running", "tw_cellular_preview"):
            self.assertNotIn(label, fragment)

    def test_no_new_raster_asset_is_bundled(self):
        for name in ("0031-theme-cellular-data-status-icon.patch", "0033-theme-visible-cellular-signal-bars.patch"):
            patch = (DEVICE / "patches/bootable-recovery" / name).read_text()
            self.assertNotIn(".png", patch)
            self.assertNotIn(".jpg", patch)
            self.assertNotIn("base64", patch)

    def test_signal_reading_defaults_unknown_and_is_not_persistent(self):
        for name, value in (("tw_cellular_signal_valid", "0"), ("tw_cellular_signal_level", "-1")):
            variable = self.variables[name]
            self.assertEqual(variable.attrib["value"], value)
            self.assertNotIn(variable.attrib.get("persist", "0"), ("1", "true"))

    def test_four_empty_signal_outlines_are_always_visible(self):
        outlines = [f for f in self.signal_fills if f.attrib["color"] == "#9E9E9E" and not f.findall("condition")]
        holes = [f for f in self.signal_fills if f.attrib["color"] == "%status_color%"]
        self.assertEqual(len(outlines), 4)
        self.assertEqual(len(holes), 4)
        self.assertTrue(all(not f.findall("condition") for f in holes))
        self.assertEqual([int(f.find("placement").attrib["h"]) for f in outlines], [9, 16, 23, 30])
        self.assertEqual([int(f.find("placement").attrib["x"]) for f in outlines], [656, 667, 678, 689])

    def test_signal_fill_requires_valid_bounded_measurement(self):
        blue = [f for f in self.signal_fills if f.attrib["color"] == "%accent_color%" and f.find("condition[@var1='tw_cellular_signal_valid']") is not None]
        self.assertEqual(len(blue), 4)
        for level, fill in enumerate(blue, 1):
            self.assertEqual([c.attrib for c in fill.findall("condition")], [
                {"var1": "tw_cellular_connected", "var2": "1"},
                {"var1": "tw_cellular_signal_valid", "var2": "1"},
                {"var1": "tw_cellular_signal_level", "op": ">=", "var2": str(level)},
                {"var1": "tw_cellular_signal_level", "op": "<=", "var2": "4"},
            ])

    @staticmethod
    def shown(fill, valid, level, connected=0):
        values = {"tw_cellular_signal_valid": valid, "tw_cellular_signal_level": level, "tw_cellular_connected": connected}
        for condition in fill.findall("condition"):
            c = condition.attrib
            left, right = str(values[c["var1"]]), c["var2"]
            op = c.get("op", "=")
            if op == "=" and left != right: return False
            if op == "!=" and left == right: return False
            if op == ">=" and int(left) < int(right): return False
            if op == "<=" and int(left) > int(right): return False
        return True

    def test_signal_level_states_never_invent_service(self):
        blue = [f for f in self.signal_fills if f.attrib["color"] == "%accent_color%" and f.find("condition[@var1='tw_cellular_signal_valid']") is not None]
        crosses = [f for f in self.signal_fills if f.find("condition[@op='!=']") is not None]
        for level in range(5):
            self.assertEqual(sum(self.shown(f, 1, level, 1) for f in blue), level)
            self.assertFalse(any(self.shown(f, 1, level, 0) for f in blue))
            self.assertFalse(any(self.shown(f, 1, level) for f in crosses))
            self.assertFalse(any(self.shown(f, 0, level, 1) for f in blue))
            self.assertTrue(all(self.shown(f, 0, level) for f in crosses))
        for level in (-1, 5, 99):
            self.assertFalse(any(self.shown(f, 1, level, 1) for f in blue))

    def test_connected_data_lights_outlines_without_faking_signal_level(self):
        outlines = [f for f in self.signal_fills if f.attrib["color"] == "%accent_color%" and len(f.findall("condition")) == 1]
        measured = [f for f in self.signal_fills if any(c.attrib == {"var1": "tw_cellular_signal_valid", "var2": "1"} for c in f.findall("condition"))]
        crosses = [f for f in self.signal_fills if f.find("condition[@op='!=']") is not None]
        self.assertEqual(len(outlines), 4)
        self.assertTrue(all(self.shown(f, 0, -1, 1) for f in outlines))
        self.assertFalse(any(self.shown(f, 0, -1, 0) for f in outlines))
        self.assertFalse(any(self.shown(f, 0, -1, 1) for f in measured))
        self.assertFalse(any(self.shown(f, 0, -1, 1) for f in crosses))
        for fill in outlines:
            self.assertEqual(fill.find("condition").attrib, {"var1": "tw_cellular_connected", "var2": "1"})

    def test_disconnected_signal_measurements_stay_gray(self):
        gray = [f for f in self.signal_fills if f.attrib["color"] == "#9E9E9E" and any(c.attrib == {"var1": "tw_cellular_signal_valid", "var2": "1"} for c in f.findall("condition"))]
        self.assertEqual(len(gray), 4)
        for level in range(5):
            self.assertEqual(sum(self.shown(f, 1, level, 0) for f in gray), level)

    def test_unknown_signal_displays_small_gray_x(self):
        crosses = [f for f in self.signal_fills if f.find("condition[@op='!=']") is not None]
        self.assertEqual(len(crosses), 8)
        for fill in crosses:
            self.assertEqual(fill.attrib["color"], "#9E9E9E")
            self.assertEqual([c.attrib for c in fill.findall("condition")], [
                {"var1": "tw_cellular_signal_valid", "op": "!=", "var2": "1"},
                {"var1": "tw_cellular_connected", "op": "!=", "var2": "1"},
            ])
        self.assertTrue(all(self.shown(f, 0, -1) for f in crosses))

    def test_signal_geometry_does_not_overlap_data_or_wifi(self):
        for fill in self.signal_fills:
            x, y, w, h = (int(fill.find("placement").attrib[k]) for k in ("x", "y", "w", "h"))
            self.assertGreaterEqual(x, 656)
            self.assertLessEqual(x + w, 712)  # Eight-pixel gap before unchanged Wi-Fi at x=720.
            self.assertGreaterEqual(y, 28)
            self.assertLessEqual(y + h, 60)
        self.assertEqual(self.source.count(SIGNAL_START), 0)
        page = self.theme.find("templates/template[@name='page']")
        self.assertEqual(len(page.findall("fill[@color='#9E9E9E']")), 0)

    def test_patch_workflow_verifies_icon(self):
        self.assertIn('test-cellular-status.py', (DEVICE / "scripts/apply-recovery-patches.sh").read_text())

    def test_native_fill_requests_one_redraw_on_each_visibility_transition(self):
        source = (ROOT / "bootable/recovery/gui/fill.cpp").read_text()
        method = re.search(r"int GUIFill::Update\(void\)\n\{.*?^\}", source, re.M | re.S)
        self.assertIsNotNone(method)
        fixture = '''#include <cassert>
class GUIFill {
public:
 bool visible=false, mLastVisible=false;
 bool isConditionTrue() const { return visible; }
 int Update(void);
};
''' + method.group(0) + '''
int main() {
 GUIFill f;
 assert(f.Update()==0);
 f.visible=true; assert(f.Update()==2); assert(f.Update()==0);
 f.visible=false; assert(f.Update()==2); assert(f.Update()==0);
 f.visible=true; assert(f.Update()==2);
}
'''
        with tempfile.TemporaryDirectory() as directory:
            binary = str(Path(directory) / "fill-visibility")
            subprocess.run(["g++", "-std=c++17", "-Wall", "-Wextra", "-Werror", "-x", "c++", "-", "-o", binary], input=fixture, text=True, check=True)
            subprocess.run([binary], check=True)

    def test_native_render_tracks_displayed_state(self):
        source = (ROOT / "bootable/recovery/gui/fill.cpp").read_text()
        render = source[source.index("int GUIFill::Render(void)"):source.index("int GUIFill::Update(void)")]
        self.assertIn("mLastVisible = isConditionTrue();", render)
        self.assertIn("if (!mLastVisible)", render)


if __name__ == "__main__":
    unittest.main(argv=[sys.argv[0]], verbosity=2)
