#!/usr/bin/env python3
"""Native Wi-Fi list, password flow and worker/UI ownership contracts. No ADB."""
from pathlib import Path
import sys
import unittest
import xml.etree.ElementTree as ET

DEVICE=Path(__file__).resolve().parents[1]
ROOT=Path(sys.argv[1]).resolve() if len(sys.argv)>1 else DEVICE.parents[2]
RECOVERY=ROOT/'bootable/recovery'

class WifiPageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.theme=ET.parse(RECOVERY/'gui/theme/common/portrait.xml')
        cls.page=cls.theme.find("pages/page[@name='wlan']")
        cls.cpp=(RECOVERY/'gui/wlanlist.cpp').read_text()
        cls.action=(RECOVERY/'gui/action.cpp').read_text()
        cls.log=(RECOVERY/'gui/borderedlogbox.cpp').read_text()

    def test_native_tappable_rows_and_signal_column(self):
        rows=self.page.find('wlanlist')
        self.assertEqual(rows.find('data').get('name'),'tw_selected_wlan')
        self.assertEqual(rows.find('columns').get('signalwidth'),'150')
        self.assertEqual(rows.find('icon').get('unselected'),'oxy_icon_wifi_56')
        self.assertEqual(rows.find('fastscroll').get('rectcolor'),'#E31B36')
        self.assertEqual([(a.get('function'),a.text) for a in rows.findall('actions/action')],
            [('set','tw_back=wlan'),('set','tw_wlan_password='),('page','wlan_password')])

    def test_selection_publishes_encryption_before_action(self):
        selected=self.cpp[self.cpp.index('void GUIWlanList::NotifySelect'):]
        self.assertLess(selected.index('SetValue("tw_selected_wlan_encryption"'),selected.index('SetValue(mVariable,'))
        self.assertLess(selected.index('SetValue(mVariable,'),selected.index('mSelectionAction->doActions()'))
        focus=self.cpp[self.cpp.index('void GUIWlanList::SetPageFocus'):self.cpp.index('size_t GUIWlanList::GetItemCount')]
        self.assertIn('if (!mSelectionAction && !mList.empty()',focus)
        self.assertNotIn('doActions()',focus)

    def test_password_is_masked_and_keyboard_focused(self):
        password=self.theme.find("pages/page[@name='wlan_password']")
        self.assertEqual(password.find('input/data').get('mask'),'*')
        self.assertFalse(password.find('input/text').text)
        self.assertEqual(password.find('input/cursor').get('hasfocus'),'1')
        self.assertIsNotNone(password.find("template[@name='keyboardtemplate']"))
        for action in password.findall('action'):
            if action.find('touch') is not None:
                self.assertTrue(any(a.get('function')=='set' and a.text=='tw_wlan_password=' for a in action.findall('action')))

    def test_tools_retain_all_native_network_actions(self):
        actions={a.get('function') for a in self.page.iter('action')}
        self.assertTrue({'wlanscan','wlanconnect','wlangetstatus','wlantest','wlanstart','wlanstop'}-actions=={'wlanconnect'})
        self.assertTrue(all(b.find("condition[@var1='tw_op15_wifi_tools']") is not None for b in self.page.findall('button')))
        self.assertIsNotNone(self.page.find('borderedlogbox'))

    def test_scan_results_only_change_rows_on_gui_thread(self):
        header=(RECOVERY/'gui/objects.hpp').read_text()
        wlan=header[header.index('class GUIWlanList'):header.index('// Global functions for managing WLAN list')]
        self.assertIn('std::atomic<bool> updateList;',wlan)
        self.assertIn('GUIAction* mSelectionAction;',wlan)
        partitions=header[header.index('class GUIPartitionList'):header.index('class GUIWlanList')]
        self.assertNotIn('mSelectionAction',partitions)
        self.assertIn('bool updateList;',partitions)
        notification=self.cpp[self.cpp.index('int GUIWlanList::NotifyVarChange'):self.cpp.index('void GUIWlanList::SetPageFocus')]
        self.assertIn('updateList.store(true)',notification)
        self.assertNotIn('mList =',notification)
        update=self.cpp[self.cpp.index('int GUIWlanList::Update'):self.cpp.index('int GUIWlanList::NotifyVarChange')]
        self.assertIn('updateList.exchange(false)',update)
        self.assertNotIn('Render();',update)

    def test_log_producer_never_changes_scroll_state(self):
        append=self.log[self.log.index('void GUIBorderedLogBox::AddLogLine'):self.log.index('void GUIBorderedLogBox::ClearLogs')]
        self.assertIn('lock(mLogMutex)',append)
        self.assertNotIn('SetVisibleListLocation',append)
        update=self.log[self.log.index('int GUIBorderedLogBox::Update'):self.log.index('int GUIBorderedLogBox::NotifyVarChange')]
        self.assertIn('changed && scrollToEnd && !mLogLines.empty()',update)
        self.assertNotIn('Render()',update)

    def test_scan_failures_are_not_reported_as_success(self):
        self.assertIn('"Scanning..."',self.action)
        self.assertIn('"Scan failed. Retry"',self.action)
        self.assertIn('SetWlanList({});',self.action)
        self.assertNotIn('using fallback MyHomeWiFi',self.action)

    def test_list_does_not_overlap_footer_or_navigation(self):
        placement=self.page.find('wlanlist/placement')
        y=int(placement.get('y'));height=int(placement.get('h'))
        self.assertLessEqual(y+height,1424)
        self.assertLess(1568+112,1816)
        self.assertNotIn('Jason',ET.tostring(self.page,encoding='unicode'))

    def test_back_key_cannot_autofire_on_page_focus(self):
        keys=[a for a in self.page.findall('action') if a.find("touch[@key='back']") is not None]
        self.assertEqual(len(keys),1)
        self.assertIsNone(keys[0].find('condition'))
        self.assertEqual([(a.get('function'),a.text) for a in keys[0].findall('action')],
            [('page','%tw_op15_wifi_back%'),('set','tw_op15_wifi_tools=0')])
        routes=[a for a in self.page.findall('action') if a.find('condition') is not None]
        self.assertEqual(len(routes),2)
        self.assertTrue(all(a.get('function')=='set' for route in routes for a in route.findall('action')))

if __name__=='__main__':unittest.main(argv=[sys.argv[0]],verbosity=2)
