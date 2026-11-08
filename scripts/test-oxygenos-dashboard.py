#!/usr/bin/env python3
"""Host/source contracts for the actual native XML, not a concept mockup."""
from __future__ import annotations
import base64
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import struct
import subprocess
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET

DEVICE=Path(__file__).resolve().parents[1]
ROOT=Path(sys.argv[1]).resolve() if len(sys.argv)>1 else DEVICE.parents[2]
RECOVERY=ROOT/"bootable/recovery"
ASSETS=DEVICE/"assets/twrp-theme/oxygenos"
spec=importlib.util.spec_from_file_location("oxygenos_patcher",DEVICE/"tools/patch_oxygenos_dashboard.py")
patcher=importlib.util.module_from_spec(spec);spec.loader.exec_module(patcher)


def flatten(nodes):return [(n.get("function"),(n.text or "").strip()) for parent in nodes for n in parent.iter("action")]


class DashboardTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.layout=json.loads((ASSETS/"dashboard.json").read_text())
        cls.manifest=json.loads((ASSETS/"manifest.json").read_text())
        cls.ui=ET.parse(RECOVERY/"gui/theme/portrait_hdpi/ui.xml").getroot()
        cls.portrait=ET.parse(RECOVERY/"gui/theme/common/portrait.xml").getroot()
        cls.home=cls.portrait.find("pages/page[@name='main2']")
        cls.classic=patcher.native_main(RECOVERY)

    def test_all_18_routes_are_copied_from_existing_actions(self):
        self.assertEqual(len(self.layout["buttons"]),18)
        for b in self.layout["buttons"]:
            actual=self.home.find(f"button[@name='oxy_{b['id']}']")
            self.assertIsNotNone(actual,b["id"])
            expected=patcher.source_actions(self.portrait,self.classic,b["source"])
            self.assertEqual(flatten(patcher.actions(actual)),flatten(expected),b["id"])
            self.assertIsNotNone(actual.find("condition[@var1='tw_busy'][@var2='0']"))

    def test_reboots_keep_confirmation_and_capabilities(self):
        for b in self.layout["buttons"]:
            if b["kind"]!="quick":continue
            n=self.home.find(f"button[@name='oxy_{b['id']}']")
            chain=flatten(patcher.actions(n))
            self.assertNotIn("reboot",[fn for fn,_ in chain])
            self.assertIn(chain[-1],[("page","rebootcheck"),("page","reboot_system_routine")])
            self.assertIsNotNone(n.find(f"condition[@var1='{b['capability']}'][@var2='1']"))

    def test_ftp_and_wifi_are_real_native_flows(self):
        chain=flatten(patcher.actions(self.home.find("button[@name='oxy_ftp']")))
        self.assertEqual(chain,[("editfile","/system/bin/twrp-ftp-menu"),("page","terminalcommand")])
        wifi=flatten(patcher.actions(self.home.find("button[@name='oxy_wifi']")))
        self.assertEqual(wifi,[("page","wlan")])
        charging=flatten(patcher.actions(self.home.find("button[@name='oxy_charging']")))
        self.assertEqual(charging,[("page","op15_charging")])
        self.assertTrue((DEVICE/"recovery/root/system/bin/twrp-ftp-menu").exists())

    def test_touch_targets_are_large_and_do_not_overlap(self):
        boxes=[]
        for b in self.layout["buttons"]:
            x,y,w,h=b["box"];self.assertGreaterEqual(w,200);self.assertGreaterEqual(h,88)
            self.assertTrue(0<=x<x+w<=1080 and 72<=y<y+h<=1820)
            n=self.home.find(f"button[@name='oxy_{b['id']}']")
            placement=n.find("placement");self.assertEqual((int(placement.get("x")),int(placement.get("y"))),(x,y))
            image=n.find("image");self.assertEqual(self.manifest[image.get("resource")]["size"],[w,h])
            boxes.append((b["id"],x,y,w,h))
        for i,(name,x,y,w,h) in enumerate(boxes):
            for other,a,b,c,d in boxes[i+1:]:
                self.assertFalse(x<a+c and a<x+w and y<b+d and b<y+h,(name,other))
            # Native hit rectangle is the image dimensions, not the label/icon.
            for px,py in ((x+w//2,y+h//2),(x+4,y+4),(x+w-4,y+h-4)):
                hits=[n for n,a,b,c,d in boxes if a<=px<=a+c and b<=py<=b+d]
                self.assertEqual(hits,[name])

    def test_all_assets_are_small_authenticated_rgba_pngs(self):
        total=0;decoded=0
        for name,m in self.manifest.items():
            data=base64.b64decode((ASSETS/(name+".png.b64")).read_bytes())
            self.assertEqual(hashlib.sha256(data).hexdigest(),m["sha256"])
            self.assertEqual(data[:8],b"\x89PNG\r\n\x1a\n")
            self.assertEqual(list(struct.unpack(">II",data[16:24])),m["size"])
            self.assertEqual(data[25],6,"RGBA transparency required")
            self.assertLess(len(data),65536);self.assertNotEqual(m["size"],[941,1672])
            staged=RECOVERY/"gui/theme/portrait_hdpi/images"/(name+".png")
            self.assertEqual(staged.read_bytes(),data)
            total+=len(data);decoded+=m["size"][0]*m["size"][1]*4
        # The requested outlined/glowing twelve-frame progress style adds a
        # small explicit artwork allowance. Per-asset and decoded limits stay.
        self.assertLess(total,288*1024);self.assertLess(decoded,16*1024*1024)

    def test_section_spacing_reaches_navigation_without_overlap(self):
        cards=[c['box'] for c in self.layout['cards']]
        for previous,current in zip(cards,cards[1:]):
            self.assertGreaterEqual(current[1]-(previous[1]+previous[3]),32)
        last_bottom=cards[-1][1]+cards[-1][3]
        nav_top=int(self.home.find("button[@name='oxy_home']/placement").get('y'))
        self.assertGreaterEqual(nav_top-last_bottom,0)
        self.assertLessEqual(nav_top-last_bottom,8)
        footer=next(n for n in self.home.findall('fill') if n.find('placement').get('y')=='1710')
        self.assertGreaterEqual(int(footer.find('placement').get('y')),last_bottom)

    def test_logs_overlay_keeps_visible_functional_navigation(self):
        logs=self.portrait.find("pages/page[@name='slideout']")
        self.assertEqual(logs.find('console/placement').get('h'),'1608')
        self.assertIsNotNone(logs.find("template[@name='oxygenos_status']"))
        for name in ('back','home','logs'):
            button=logs.find(f"button[@name='oxy_log_{name}']")
            self.assertEqual(button.find('image').get('resource'),'oxy_nav_hitbox')
            chain=flatten(patcher.actions(button))
            self.assertEqual(chain,[('overlay',''),('page','main')] if name=='home' else [('overlay','')])
        self.assertEqual(len(logs.findall('image')),3)

    def test_resources_and_pages_resolve_without_duplicates(self):
        names=[]
        for n in self.ui.find("resources"):names.append(n.get("name"))
        self.assertEqual(len(names),len(set(names)))
        resources=set(names)
        for parent in (self.home,self.ui.find("templates/template[@name='oxygenos_status']")):
            for n in parent.iter():
                for key in ("resource","highlightresource","full","empty"):
                    if n.get(key):self.assertIn(n.get(key),resources,n.attrib)
        pages=[p.get("name") for p in self.portrait.findall("pages/page")]
        self.assertEqual(len(pages),len(set(pages)))
        for action in self.home.iter("action"):
            if action.get("function")=="page":self.assertIn(action.text,pages)
        variables=[v.get("name") for v in self.ui.findall("variables/variable")]
        self.assertEqual(len(variables),len(set(variables)))
        for r in self.ui.findall("resources/font[@filename='RobotoCondensed-Regular.ttf']"):
            self.assertTrue((RECOVERY/"gui/theme/common/fonts"/r.get("filename")).exists())

    def test_no_threaded_status_actions_or_invented_success(self):
        status=self.ui.find("templates/template[@name='oxygenos_status']")
        self.assertEqual(list(status.iter("action")),[])
        for a in self.home.findall("action"):
            self.assertIsNotNone(a.find("touch"))
        source=(RECOVERY/"oxygenos_dashboard.hpp").read_text()
        for forbidden in ("system(","Exec_Cmd",'stat("/data',"Mount_By_Path","Decrypt_Device","std::thread"):
            self.assertNotIn(forbidden,source)
        self.assertIn("std::chrono::seconds(1)",source)
        self.assertIn("262144",source)
        texts=[n.text for n in self.home.findall("text/text")]
        self.assertNotIn("Not available",texts)
        self.assertNotIn("Last Backup",texts)
        for fake in ("54%","39 °C","Jan 26, 7:42 PM","Internal storage mounted"):
            self.assertNotIn(fake,texts)

    def test_aspect_ratios_and_home_navigation(self):
        for n in self.ui.findall("resources/image"):
            name=n.get("name","")
            if name.startswith(("oxy_icon_","oxy_dot_")) or name=="oxy_logo":self.assertEqual(n.get("retainaspect"),"1")
        home=self.home.find("button[@name='oxy_home']")
        self.assertEqual(flatten(patcher.actions(home)),[("key","home")])
        self.assertEqual(home.find('placement').attrib,{'x':'444','y':'1712','w':'192','h':'128'})
        for name in ('back','home','logs'):
            button=self.home.find(f"button[@name='oxy_{name}']")
            self.assertEqual(button.find('image').get('resource'),'oxy_nav_hitbox')
        self.assertEqual(self.manifest['oxy_nav_hitbox']['size'],[192,128])
        self.assertEqual(flatten(patcher.actions(self.home.find("button[@name='oxy_back']"))),[("key","back")])
        self.assertFalse(any(n.find('image').get('resource')=='oxy_footer' for n in self.home.findall('image')))

    def test_snapshot_public_headers_export_their_dependency(self):
        source=(ROOT/"system/core/fs_mgr/libsnapshot/Android.bp").read_text()
        defaults=source.split('name: "libsnapshot_defaults",',1)[1].split('\ncc_defaults {',1)[0]
        exports=defaults.split('export_header_lib_headers: [',1)[1].split(']',1)[0]
        self.assertIn('"libupdate_engine_headers"',exports)
        header=(ROOT/"system/core/fs_mgr/libsnapshot/include/libsnapshot/cow_reader.h").read_text()
        self.assertIn('#include <payload_consumer/file_descriptor.h>',header)

    def test_incremental_build_tracks_theme_resources(self):
        source=(RECOVERY/'gui/libguitwrp_defaults.go').read_text()
        copy=source.split('func copyThemeResources(',1)[1].split('outDir :=',1)[0]
        self.assertIn('ctx.GlobWithDeps(path.Join(recoveryRoot, dir, "**/*"), nil)',copy)
        self.assertIn('ctx.AddNinjaFileDeps(matches...)',copy)
        self.assertIn('ctx.AddNinjaFileDeps(path.Join(recoveryRoot, file))',copy)
        self.assertIn('"variables.h"',copy)
        packaging=(DEVICE/'Android.mk').read_text()
        self.assertIn('$(call intermediates-dir-for,PACKAGING,recovery)/ramdisk_files-timestamp:',packaging)
        for name in ('ui.xml','portrait.xml','splash.xml'):
            self.assertIn('$(TARGET_RECOVERY_ROOT_OUT)/twres/'+name,packaging)

    def test_current_vold_owns_database_sync_without_crypto_source_edits(self):
        header=(ROOT/"system/vold/Decrypt.h").read_text()
        backend=(ROOT/"system/vold/Decrypt.cpp").read_text()
        self.assertIn('bool syncKeystoreDb();',header)
        decrypt=backend.split('bool Decrypt_User_Synth_Pass(',1)[1]
        self.assertLess(decrypt.index('if (!android::keystore::syncKeystoreDb())'),
                        decrypt.index('Get_Password_Data('))
        startup=(RECOVERY/"twrp.cpp").read_text()
        self.assertNotIn('android::keystore::copySqliteDb();',startup)
        self.assertIn('Decrypt_Page(skip_decryption, datamedia);',startup)
        self.assertEqual(subprocess.check_output(['git','-C',str(ROOT/"system/vold"),'diff','--','Decrypt.h','Decrypt.cpp']),b'')

    def test_patch_syntax_and_readonly_provider_integration(self):
        for patch in sorted((DEVICE/"patches").glob("*/*.patch")):
            subprocess.run(["git","apply","--numstat",str(patch)],check=True,stdout=subprocess.PIPE)
        source=(RECOVERY/"data.cpp").read_text()
        section=source.split('// Read-only status values, not GUI actions',1)[1].split('// Handle special dynamic cases',1)[0]
        self.assertIn('property_get("twrp.user.0.decrypt"',section)
        self.assertIn('GetValue("tw_is_fbe", status.fbe)',section)
        self.assertIn('GetIntValue("tw_busy") == 0',section)
        for forbidden in ('SetValue(', 'Exec_Cmd', 'Decrypt_Device', 'Mount_By_Path', 'pthread_create'):
            self.assertNotIn(forbidden,section)
        gui=(RECOVERY/"gui/gui.cpp").read_text()
        tick=gui.split('// OP15 dashboard condition refresh:',1)[1].split('FD_ZERO(&fdset)',1)[0]
        self.assertIn('dashboard_now.tv_sec != dashboard_status_second',tick)
        self.assertIn('PageManager::NotifyVarChange("tw_op15_dashboard_storage_ready", storage)',tick)
        self.assertIn('PageManager::NotifyVarChange("tw_op15_dashboard_battery_valid", battery)',tick)
        self.assertIn('gForceRender.set_value(1)',tick)
        for forbidden in ('SetValue(', 'Exec_Cmd', 'DoActions', 'GUIAction', 'Decrypt_Device', 'Mount_By_Path', 'pthread_create'):
            self.assertNotIn(forbidden,tick)

    def test_new_upstream_vold_guard_fails_closed(self):
        script=(DEVICE/"scripts/apply-recovery-patches.sh").read_text()
        function=re.search(r'vold_temp_directory_fix_superseded\(\) \{.*?\n\}',script,re.S).group(0)
        safe='Never persist an upgraded blob:\nstd::lock_guard<std::mutex> lock(key_upgrade_lock);\nfor this operation only; the on-disk blob is left unchanged\n'
        with tempfile.TemporaryDirectory(prefix="op15-vold-guard-") as directory:
            for content,expected in ((safe,True),(safe+'mkdir(temp_dir.c_str(), 0700)',False),(safe+'std::string temp_dir =',False),("unrecognized new code",False)):
                (Path(directory)/"KeyStorage.cpp").write_text(content)
                result=subprocess.run(["bash","-c",'SYSTEM_VOLD_DIR="$1"\n'+function+'\nvold_temp_directory_fix_superseded',"test",directory])
                self.assertEqual(result.returncode==0,expected)

    def test_preserves_subpages_advanced_and_status_semantics(self):
        for name in ("install","wipe","backup","restore","mount","settings","advanced","reboot","wlan","filemanagerlist","terminalcommand","sideload","confirm_action","rebootcheck"):
            self.assertIsNotNone(self.portrait.find(f"pages/page[@name='{name}']"),name)
        advanced=ET.tostring(self.portrait.find("pages/page[@name='advanced']"),encoding="unicode")
        for value in ("op15_charging","twrp-flash-magisk init_boot","twrp-ftp-menu","twrp-avb-tool"):self.assertIn(value,advanced)
        for value in ("Disable AVB2.0","Install TWRP App","ufs_manager"):self.assertNotIn(value,advanced)
        status=self.ui.find("templates/template[@name='oxygenos_status']")
        wifi=next(n for n in status.findall("image") if n.find("image").get("resource")=="wifi_status")
        self.assertEqual(wifi.find("placement").attrib,{"x":"800","y":"2"})
        self.assertIsNotNone(wifi.find("condition[@var1='tw_wifi_connected'][@var2='1']"))
        self.assertIsNotNone(self.home.find("button[@name='oxy_logs']/action[@function='overlay']"))

    def test_classic_is_removed_and_status_is_inset_and_shared(self):
        self.assertIsNone(self.portrait.find("pages/page[@name='op15_classic_home']"))
        self.assertIsNone(self.home.find("button[@name='oxy_classic']"))
        status=self.ui.find("templates/template[@name='oxygenos_status']")
        cpu=status.find("text[text='CPU %tw_op15_dashboard_cpu%']")
        clock=status.find("text[text='%tw_time%']")
        self.assertEqual(cpu.find('placement').attrib,{'x':'282','y':'12'})
        self.assertEqual(cpu.find('font').get('resource'),clock.find('font').get('resource'))
        self.assertEqual(cpu.get('color'),clock.get('color'))
        thermometer=next(n for n in status.findall('image') if n.find('image').get('resource')=='oxy_icon_thermometer_32')
        self.assertEqual(thermometer.find('placement').attrib,{'x':'238','y':'21'})
        self.assertEqual(self.manifest['oxy_icon_thermometer_32']['size'],[32,32])
        self.assertEqual(status.find('progressbar/placement').get('x'),'952')
        self.assertLessEqual(952+self.manifest['oxy_battery_empty']['size'][0],1000)
        self.assertFalse(any(c.get('var1','').startswith('tw_cellular_') for c in self.ui.iter('condition')))
        self.assertIsNotNone(self.ui.find("templates/template[@name='page']/template[@name='oxygenos_status']"))

    def test_wifi_tile_illuminates_only_for_real_connection(self):
        green=next(n for n in self.home.findall('image') if n.find('image').get('resource')=='oxy_icon_wifi_connected_56')
        white=next(n for n in self.home.findall('image') if n.find('image').get('resource')=='oxy_icon_wifi_56')
        self.assertEqual(green.find('condition').attrib,{'var1':'tw_wifi_connected','var2':'1'})
        self.assertEqual(white.find('condition').attrib,{'var1':'tw_wifi_connected','var2':'1','op':'!='})

    def test_charging_icon_uses_fail_closed_kernel_status(self):
        images={n.find('image').get('resource'):n for n in self.home.findall('image')}
        self.assertEqual(images['oxy_icon_charging_active_56'].find('condition').attrib,{'var1':'tw_op15_dashboard_charging','var2':'1'})
        self.assertEqual(images['oxy_icon_charging_56'].find('condition').attrib,{'var1':'tw_op15_dashboard_charging','var2':'1','op':'!='})
        header=(RECOVERY/'oxygenos_dashboard.hpp').read_text()
        self.assertIn('/sys/class/power_supply/battery/status',header)
        self.assertIn('char buffer[32]',header)
        self.assertIn('O_RDONLY | O_CLOEXEC | O_NONBLOCK',header)
        self.assertIn('CachedCharging()',header)
        data=(RECOVERY/'data.cpp').read_text()
        self.assertIn('value = op15_dashboard::CachedCharging() ? "1" : "0";',data)
        gui=(RECOVERY/'gui/gui.cpp').read_text()
        self.assertIn('PageManager::NotifyVarChange("tw_op15_dashboard_charging", charging)',gui)

    def test_advanced_list_alphabetical_without_losing_actions(self):
        box=self.portrait.find("pages/page[@name='advanced']/listbox[@style='advanced_listbox']")
        items=box.findall('listitem');labels=[patcher.list_caption(n).casefold() for n in items]
        self.assertEqual(labels,sorted(labels))
        for item in items:self.assertTrue(list(item.iter('action')),item.get('name'))
        for label in ('Charging','Flash Magisk','Reload Theme'):
            self.assertIn(label.casefold(),labels)

    def test_sorted_advanced_cleanup_verifier_rejects_action_or_item_loss(self):
        patcher.verify_advanced_cleanup(RECOVERY)
        broken=copy.deepcopy(self.portrait)
        box=broken.find("pages/page[@name='advanced']/listbox")
        item=next(n for n in box.findall('listitem') if n.get('name','').startswith('{@reload_theme_btn='))
        box.remove(item)
        with self.assertRaises(ValueError):patcher.verify_advanced_cleanup(RECOVERY,broken)
        broken=copy.deepcopy(self.portrait)
        action=broken.find("pages/page[@name='advanced']/listbox/listitem[@name='{@reload_theme_btn=Reload Theme}']/action")
        action.set('function','reboot')
        with self.assertRaises(ValueError):patcher.verify_advanced_cleanup(RECOVERY,broken)

    def test_shared_red_controls_use_declared_sizes_and_red_splash(self):
        aliases=json.loads((ASSETS/'shared-controls.json').read_text())
        for name,meta in aliases.items():
            self.assertEqual(self.ui.find(f"resources/image[@name='{name}']").get('filename'),meta['asset'])
            self.assertEqual(self.manifest[meta['asset']]['size'],meta['size'])
        self.assertEqual(self.ui.find("variables/variable[@name='accent_color']").get('value'),'#E31B36')
        self.assertEqual(self.ui.find("resources/image[@name='slider_touch']").get('filename'),'oxy_shared_slider_touch')
        splash=ET.parse(RECOVERY/'gui/theme/portrait_hdpi/splash.xml').getroot()
        self.assertEqual(splash.find("resources/image[@name='splashlogo']").get('filename'),'oxy_splash_logo')
        self.assertNotIn('#0090CA',ET.tostring(splash,encoding='unicode'))
        self.assertEqual(self.ui.find("variables/variable[@name='fileselector_linecolor']").get('value'),'#8A2030')
        self.assertEqual(self.ui.find("resources/image[@name='fab_selectfolder']").get('filename'),'oxy_shared_folder_fab')
        self.assertEqual(self.ui.find("resources/image[@name='file']").get('filename'),'oxy_shared_file')
        self.assertEqual(self.manifest['oxy_shared_button_half']['size'],[468,112])
        self.assertEqual(self.manifest['oxy_shared_button_full']['size'],[1008,112])
        self.assertEqual(self.manifest['oxy_shared_button']['size'],[468,160])
        self.assertEqual(self.manifest['oxy_shared_slider']['size'],[936,192])
        self.assertEqual(self.ui.find("resources/image[@name='enter']").get('filename'),'oxy_shared_enter')
        self.assertEqual(self.manifest['oxy_shared_enter']['size'],[162,161])
        self.assertEqual(self.ui.find("resources/animation[@name='progress']").get('filename'),'oxy_indeterminate')
        frames=[n for n in self.manifest if n.startswith('oxy_indeterminate')]
        self.assertEqual(len(frames),12)
        for frame in frames:self.assertEqual(self.manifest[frame]['size'],[1008,64])

    def test_advanced_button_columns_have_symmetric_margins_and_gap(self):
        page=self.portrait.find("pages/page[@name='advanced']")
        left=page.find("button[@style='main_button_half_height']/placement")
        right=next(p for p in page.findall("button[@style='main_button_half_height']/placement") if p.get('x')=='%col1_x_right%')
        self.assertEqual(left.get('x'),'%indent%')
        values={n.get('name'):n.get('value') for n in self.ui.findall('variables/variable')}
        x1=int(values['indent']);x2=int(values['col1_x_right'])
        width=self.manifest['oxy_shared_button_half']['size'][0]
        self.assertEqual(x2-(x1+width),72)
        self.assertEqual(1080-(x2+width),x1)

    def test_navigation_headers_use_the_same_logo_size_and_position(self):
        self.assertEqual(self.manifest['oxy_logo']['size'],[96,96])
        self.assertEqual(self.ui.find("resources/image[@name='logo']").get('filename'),'oxy_logo')
        shared=self.ui.find("templates/template[@name='page']")
        controls=[n for n in shared if n.tag in ('image','button') and n.find("image[@resource='logo']") is not None]
        self.assertEqual(len(controls),2)
        for control in controls:
            self.assertEqual(control.find('placement').attrib,{'x':'56','y':'106'})
        home=next(n for n in self.home.findall('image') if n.find('image').get('resource')=='oxy_logo')
        self.assertEqual(home.find('placement').attrib,{'x':'56','y':'106'})

    def test_wlan_subtitle_removed_without_changing_actions(self):
        wlan=self.portrait.find("pages/page[@name='wlan']")
        self.assertNotIn('wlan_log_hdr',ET.tostring(wlan,encoding='unicode'))
        self.assertNotIn('Jason',ET.tostring(wlan,encoding='unicode'))
        texts=[n.text for n in wlan.findall('button/text')]
        for label in ('Get Status','Test Network','Scan','Connect','Stop Service','Start Service'):
            self.assertTrue(any(label in (value or '') for value in texts),label)

    def test_reference_progress_and_lowered_unlock_label(self):
        progress=self.ui.find("templates/template[@name='progress_bar']")
        self.assertEqual(progress.find('progressbar/resource').get('rounded'),'1')
        self.assertEqual(progress.find('progressbar/data').get('name'),'ui_progress')
        self.assertEqual(progress.find('animation/condition').attrib,{'var1':'ui_progress','var2':'0'})
        self.assertEqual(progress.find('text/text').text,'%tw_op15_dashboard_progress%')
        placement=self.portrait.find("pages/page[@name='lock']/slider/placement")
        self.assertEqual(placement.get('labelcenter'),'1')
        self.assertEqual(placement.get('labeloffsety'),'56')
        self.assertEqual(self.portrait.find("pages/page[@name='lock']/slider/action").get('function'),'overlay')

    def test_progress_geometry_and_swipe_activation_unchanged(self):
        with tempfile.TemporaryDirectory(prefix='op15-progress-geometry-') as directory:
            binary=Path(directory)/'test-progress'
            subprocess.run(['g++','-std=c++17','-Wall','-Wextra','-Werror','-I',str(RECOVERY),str(DEVICE/'scripts/test-theme-progress.cpp'),'-o',str(binary)],check=True)
            subprocess.run([str(binary)],check=True)
        baseline=subprocess.check_output(['git','-C',str(RECOVERY),'show','HEAD:gui/slider.cpp'],text=True)
        current=(RECOVERY/'gui/slider.cpp').read_text()
        marker='int GUISlider::NotifyTouch('
        self.assertEqual(current[current.index(marker):],baseline[baseline.index(marker):])

    def test_idempotent_theme_script(self):
        # Touch the exact tree only through the project transformer; no reset.
        files=[RECOVERY/"gui/theme/common/portrait.xml",RECOVERY/"gui/theme/portrait_hdpi/ui.xml",RECOVERY/'gui/theme/portrait_hdpi/splash.xml']
        before=[p.read_bytes() for p in files]
        subprocess.run([sys.executable,"-B",str(DEVICE/"tools/patch_oxygenos_dashboard.py"),str(RECOVERY)],check=True,stdout=subprocess.PIPE)
        self.assertEqual(before,[p.read_bytes() for p in files])

    def test_native_status_fixtures(self):
        with tempfile.TemporaryDirectory(prefix="op15-oxygenos-status-") as directory:
            binary=Path(directory)/"test-status"
            subprocess.run(["g++","-std=c++17","-Wall","-Wextra","-Werror","-I",str(RECOVERY),str(DEVICE/"scripts/test-oxygenos-status.cpp"),"-o",str(binary)],check=True)
            subprocess.run([str(binary),directory],check=True)


if __name__=="__main__":unittest.main(argv=[sys.argv[0]],verbosity=2)
