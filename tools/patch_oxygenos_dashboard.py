#!/usr/bin/env python3
"""Install native dashboard XML idempotently; copy real actions from TWRP.

No device, shell, mount, decrypt, network or reboot calls. Runtime uses the
normal TWRP GUI engine. This build-time script only transforms theme resources.
"""
from __future__ import annotations
import argparse
import base64
import copy
import hashlib
import json
from pathlib import Path
import re
import struct
import subprocess
import sys
import xml.etree.ElementTree as ET

DEVICE=Path(__file__).resolve().parents[1]
ASSETS=DEVICE/"assets/twrp-theme/oxygenos"
START="<!-- OP15 OxygenOS dashboard START"
END="<!-- OP15 OxygenOS dashboard END"


def node(tag,**attrs):return ET.Element(tag,{k:str(v) for k,v in attrs.items()})
def add(parent,tag,**attrs):n=node(tag,**attrs);parent.append(n);return n
def place(n,x,y,w=None,h=None,align=None):
    p=add(n,"placement",x=x,y=y)
    for k,v in (("w",w),("h",h),("placement",align)):
        if v is not None:p.set(k,str(v))
def cond(n,var,value="1",op=None):
    c=add(n,"condition",var1=var,var2=value)
    if op:c.set("op",op)
def label(parent,value,x,y,font="oxy_body",color="#F4F4F7",align=None):
    n=add(parent,"text",color=color);add(n,"font",resource=font);place(n,x,y,align=align);add(n,"text").text=value;return n
def image(parent,res,x,y):
    n=add(parent,"image");add(n,"image",resource=res);place(n,x,y);return n
def fill(parent,color,x,y,w,h):n=add(parent,"fill",color=color);place(n,x,y,w,h);return n
def serialize(nodes):
    out=[]
    for n in nodes:
        n.tail=None
        ET.indent(n,space="    ",level=2)
        out.append(re.sub(r"[ \t]+\n","\n",ET.tostring(n,encoding="unicode")))
    return "\n".join(out)+"\n"
def block(part,body):return f"{START} {part} -->\n{body}{END} {part} -->"
def insert(text,part,body,before):
    pattern=re.escape(f"{START} {part} -->")+".*?"+re.escape(f"{END} {part} -->")
    if re.search(pattern,text,re.S):return re.sub(pattern,lambda _:block(part,body),text,flags=re.S)
    if text.count(before)!=1:raise ValueError("Ambiguous XML insertion: "+before)
    return text.replace(before,block(part,body)+"\n"+before,1)
def actions(n):
    group=n.find("actions")
    return [copy.deepcopy(group)] if group is not None else [copy.deepcopy(a) for a in n.findall("action")]


def source_actions(theme,classic,source):
    if source=="ftp":
        for item in theme.findall("pages/page[@name='advanced']//listitem"):
            if any(a.text=="/system/bin/twrp-ftp-menu" for a in item.iter("action")):return actions(item)
        raise ValueError("Existing Advanced FTP menu missing; refusing a placeholder")
    page,target=source.split(":",1)
    container=classic if page=="main" else theme.find(f"pages/page[@name='{page}']")
    if container is None:raise ValueError("Missing existing page: "+page)
    controls=list(container.iter("listitem" if page=="reboot" else "button"))
    if page=='advanced':controls+=list(container.iter('listitem'))
    for control in controls:
        leaves=list(control.iter("action"))
        if page=="reboot":
            matches=any(a.get("function")=="set" and a.text=="tw_action_param="+target for a in leaves)
            if target=="system":matches=any(a.get("function")=="page" and a.text=="reboot_system_routine" for a in leaves)
        else:matches=any(a.get("function")=="page" and a.text==target for a in leaves)
        if matches:return actions(control)
    raise ValueError("Missing existing action: "+source)


def native_main(recovery):
    source=subprocess.check_output(['git','-C',str(recovery),'show','HEAD:gui/theme/common/portrait.xml'],text=True)
    page=ET.fromstring(source).find("pages/page[@name='main2']")
    if page is None:raise ValueError('Pinned native main2 action source is missing')
    return page


def shared_theme(text):
    # Keep layouts and handlers unchanged; only replace visual resources/chrome.
    text=text.replace('#0090CA','#E31B36').replace('#003B52','#39141D').replace('#006B95','#8A2030')
    text=text.replace('<animation name="progress" filename="indeterminate"/>',
                      '<animation name="progress" filename="oxy_indeterminate"/>')
    progress=node('template',name='progress_bar')
    value=label(progress,'%tw_op15_dashboard_progress%','%center_x%','%row16a_y%','oxy_body','#E31B36',5)
    cond(value,'ui_progress','0','>');cond(value,'ui_progress','100','<=')
    bar=add(progress,'progressbar');place(bar,'%indent%','%row17a_y%')
    add(bar,'resource',empty='progress_empty',full='progress_full',rounded='1');add(bar,'data',name='ui_progress')
    animation=add(progress,'animation');cond(animation,'ui_progress','0')
    place(animation,'%indent%','%row17a_y%');add(animation,'resource',name='progress')
    add(animation,'speed',fps='24',render='2');add(animation,'loop',frame='1')
    text,count=re.subn(r'<template name="progress_bar">.*?</template>',lambda _:serialize([progress]).strip(),text,count=1,flags=re.S)
    if count!=1:raise ValueError('Native progress template missing')
    controls=json.loads((ASSETS/'shared-controls.json').read_text())
    for name,meta in controls.items():
        pattern=r'(<image name="'+re.escape(name)+r'" filename=")[^"]+("[^>]*?/>)'
        text,count=re.subn(pattern,lambda m:m[1]+meta['asset']+m[2],text)
        if count!=1:raise ValueError('Missing/duplicate native control resource: '+name)
    match=re.search(r'<template name="page">.*?</template>',text,re.S)
    if not match:raise ValueError('Shared native page template missing')
    page=match[0]
    if '<!-- OP15 Wi-Fi status icon START -->' in page:
        page,count=re.subn(r'<!-- OP15 Wi-Fi status icon START -->.*?<!-- Custom position for status bar items if defined END -->',
                          '<template name="oxygenos_status"/>',page,flags=re.S)
        if count!=1:raise ValueError('Ambiguous legacy status area')
    elif '<template name="oxygenos_status"/>' not in page:
        raise ValueError('Unrecognized shared status area')
    page=page.replace('<placement x="0" y="%status_height%"/>','<placement x="56" y="106"/>')
    text=text[:match.start()]+page+text[match.end():]
    marker='<!-- OP15 shared red chrome -->'
    if marker not in text:text=text.replace('<template name="page">',marker+'\n\t\t<template name="page">',1)
    return text


def patch_splash(recovery):
    path=recovery/'gui/theme/portrait_hdpi/splash.xml';text=path.read_text()
    text=text.replace('#0090CA','#E31B36').replace('name="splashlogo" filename="splashlogo"','name="splashlogo" filename="oxy_splash_logo"')
    resources=[node('font',name='oxy_splash_title',filename='RobotoCondensed-Regular.ttf',size=64),
               node('font',name='oxy_splash_caption',filename='RobotoCondensed-Regular.ttf',size=36),
               node('image',name='oxy_wave',filename='oxy_wave')]
    text=insert(text,'splash-resources',serialize(resources),'</resources>')
    page=node('page',name='splash');add(page,'background',color='#000000')
    image(page,'oxy_wave',460,100)
    logo=add(page,'image');add(logo,'image',resource='splashlogo');place(logo,540,800,align=4)
    label(page,'Recovery',540,1140,'oxy_splash_title',align=5)
    label(page,'OnePlus 15',540,1250,'oxy_splash_caption',color='#C3C3CB',align=5)
    label(page,'TeamWin Recovery Project %tw_version%',540,1310,'oxy_splash_caption',color='#C3C3CB',align=5)
    fill(page,'#E31B36',420,1410,240,6)
    text,count=re.subn(r'<page name="splash">.*?</page>',lambda _:serialize([page]).strip(),text,count=1,flags=re.S)
    if count!=1:raise ValueError('Splash page missing')
    ET.fromstring(text)
    if path.read_text()!=text:path.write_text(text)


def status_template(original):
    n=node("template",name="oxygenos_status")
    fill(n,"#000000",0,0,1080,72)
    sim=fill(n,"%text_fail_color%",0,0,1080,72);cond(sim,"tw_simulate_actions")
    label(n,"%tw_time%",58,12,"oxy_status")
    # Align visible glyphs, not transparent image canvas edges. Measurements
    # account for Roboto's ascent and the retained Wi-Fi asset's top padding.
    image(n,"oxy_icon_thermometer_32",238,21)
    label(n,"CPU %tw_op15_dashboard_cpu%",282,12,"oxy_status")
    wifi=image(n,"wifi_status",800,2);cond(wifi,"tw_wifi_connected")
    # Safe inset for the OP15 rounded physical display. No cellular ornament.
    battery=label(n,"%tw_op15_dashboard_battery%",936,12,"oxy_status",align=1);cond(battery,'tw_op15_dashboard_battery_valid')
    unknown=label(n,"—",936,12,"oxy_status",align=1);cond(unknown,'tw_op15_dashboard_battery_valid','1','!=')
    p=add(n,"progressbar");place(p,952,20);cond(p,"tw_op15_dashboard_battery_valid")
    add(p,"resource",empty="oxy_battery_empty",full="oxy_battery_full");add(p,"data",name="tw_battery")
    return n


def patch_log_overlay(text):
    match=re.search(r'<page name="slideout">.*?</page>',text,re.S)
    if not match:raise ValueError('Native log overlay missing')
    original=ET.fromstring(match[0]);console=original.find('console')
    if console is None:raise ValueError('Native log console missing')
    page=node('page',name='slideout')
    add(page,'background',color='#000000')
    console=copy.deepcopy(console)
    console.find('placement').set('h','1608')  # y=90; ends before navigation.
    page.append(console)
    fill(page,'#000000',0,1710,1080,210)
    for name,center,res in (('back',240,'back'),('home',540,'home'),('logs',840,'console')):
        button=add(page,'button',name='oxy_log_'+name)
        place(button,center-96,1712,192,128)
        add(button,'image',resource='oxy_nav_hitbox')
        group=add(button,'actions');add(group,'action',function='overlay')
        if name=='home':add(group,'action',function='page').text='main'
        icon_node=add(page,'image');add(icon_node,'image',resource=res);place(icon_node,center,1776,align=4)
    for key in ('back','home'):
        action=add(page,'action');add(action,'touch',key=key)
        group=add(action,'actions');add(group,'action',function='overlay')
        if key=='home':add(group,'action',function='page').text='main'
    for action in original.findall('action'):
        if action.find("touch[@key='power']") is not None or action.find("touch[@key='power+voldown']") is not None:
            page.append(copy.deepcopy(action))
    add(page,'template',name='oxygenos_status')
    return text[:match.start()]+serialize([page]).strip()+text[match.end():]


def inset_paired_buttons(text):
    # Native two-column buttons previously met at center_x. Preserve outer
    # margins and all action chains, and use the existing right-column anchor.
    def inset(match):
        return match[0].replace('x="%center_x%"','x="%col1_x_right%"')
    return re.sub(r'<button\b[^>]*style="(?:main_button|main_button_half_height)"[^>]*>.*?</button>',
                  inset,text,flags=re.S)


def remove_wlan_subtitle(text):
    match=re.search(r'<page name="wlan">.*?</page>',text,re.S)
    if not match:raise ValueError('Native WLAN page missing')
    page=match[0]
    page=re.sub(r'\s*<text style="text_m">\s*<placement[^>]*/>\s*<text>(?:\{@wlan_log_hdr=[^<]*\}|This page is built by Jason)</text>\s*</text>',
                '',page,flags=re.S)
    return text[:match.start()]+page+text[match.end():]


def modern_wlan(text,recovery):
    # Keep the original diagnostic actions available behind Tools. Read their
    # pinned native definition at build time, never a bundled external theme.
    original=ET.fromstring(subprocess.check_output(
        ['git','-C',str(recovery),'show','HEAD:gui/theme/common/portrait.xml'],text=True))
    legacy=original.find("pages/page[@name='wlan']")
    page=node('page',name='wlan');add(page,'template',name='page')
    label(page,'Wi-Fi','%col1_x_header%','%row3_header_y%','font_l')
    hint=label(page,'Tap a network to enter its password',72,292,'oxy_small',color='#B8B8C2')
    cond(hint,'tw_op15_wifi_tools','0')
    hint=label(page,'Network tools — Back returns to the list',72,292,'oxy_small',color='#B8B8C2')
    cond(hint,'tw_op15_wifi_tools')
    def modern(n):cond(n,'tw_op15_wifi_tools','0');return n
    modern(fill(page,'#1B1C21',36,368,1008,112))
    modern(image(page,'oxy_icon_wifi_56',64,394))
    connected=modern(label(page,'%property.twrp.wifi.ssid%',152,388,'oxy_body','#39DD87'))
    cond(connected,'tw_wifi_connected')
    disconnected=modern(label(page,'Not connected',152,388,'oxy_body','#B8B8C2'))
    cond(disconnected,'tw_wifi_connected','1','!=')
    modern(fill(page,'#1B1C21',36,528,1008,984))
    modern(fill(page,'#40232D',36,528,1008,2))
    networks=modern(add(page,'wlanlist'))
    place(networks,56,544,968,864)
    add(networks,'text').text='Available networks'
    add(networks,'font',resource='oxy_small',color='#F4F4F7',highlightcolor='#FFFFFF',spacing='34')
    add(networks,'background',color='#1B1C21')
    add(networks,'header',background='#1B1C21',textcolor='#B8B8C2',separatorcolor='#383039',separatorheight='1')
    add(networks,'separator',color='#303037',height='1')
    add(networks,'highlight',color='#491A29')
    add(networks,'icon',selected='oxy_icon_wifi_56',unselected='oxy_icon_wifi_56')
    add(networks,'columns',signalwidth='150',padding='16',color='#B8B8C2')
    add(networks,'fastscroll',linecolor='#33242B',rectcolor='#E31B36',w='26',linew='2',rectw='8',recth='112')
    add(networks,'data',name='tw_selected_wlan')
    selected=add(networks,'actions')
    add(selected,'action',function='set').text='tw_back=wlan'
    add(selected,'action',function='set').text='tw_wlan_password='
    add(selected,'action',function='page').text='wlan_password'
    empty=modern(label(page,'No networks yet. Tap Scan to refresh.',80,704,'oxy_small','#B8B8C2'))
    cond(empty,'tw_wlan_network_count','0')
    modern(fill(page,'#281820',36,1424,1008,88))
    modern(label(page,'Found %tw_wlan_network_count% networks',72,1452,'oxy_caption','#C7C7D0'))
    modern(label(page,'%tw_op15_wlan_scan_status%',1012,1452,'oxy_caption','#C7C7D0',1))
    for caption,x,function in [('Scan',36,'wlanscan'),('Tools',576,None)]:
        button=modern(add(page,'button',style='main_button_half_height'))
        place(button,x,1568);add(button,'text').text=caption
        action=add(button,'action',function=function or 'set')
        if function is None:action.text='tw_op15_wifi_tools=1'
        else:cond(button,'tw_disable_network','0')
    # Same backing log widget and six native actions; no disconnected second
    # log model. Tools mode reveals the existing diagnostics on this page.
    log=copy.deepcopy(legacy.find('borderedlogbox'))
    log.set('toprow','%row1a_y%');log.set('bottomrow','%row15_y%')
    cond(log,'tw_op15_wifi_tools');page.append(log)
    for old in legacy.findall('button'):
        button=copy.deepcopy(old);cond(button,'tw_op15_wifi_tools');page.append(button)
    # Root conditional actions run automatically in this pinned GUIAction,
    # even when they also contain a key binding. Use conditions only to select
    # a destination; keep the actual Back key action unconditional and unique.
    for value,target in [('0','advanced'),('1','wlan')]:
        route=add(page,'action');cond(route,'tw_op15_wifi_tools',value)
        add(route,'action',function='set').text='tw_op15_wifi_back='+target
    home=add(page,'action');add(home,'touch',key='home')
    add(home,'action',function='set').text='tw_op15_wifi_tools=0'
    add(home,'action',function='page').text='main'
    back=add(page,'action');add(back,'touch',key='back')
    # Resolve the previous destination before resetting Tools mode. The page
    # objects persist across a page switch, as in the native action batches.
    add(back,'action',function='page').text='%tw_op15_wifi_back%'
    add(back,'action',function='set').text='tw_op15_wifi_tools=0'
    match=re.search(r'<page name="wlan">.*?</page>',text,re.S)
    if not match:raise ValueError('Missing native WLAN page')
    text=text[:match.start()]+serialize([page]).strip()+text[match.end():]
    match=re.search(r'<page name="wlan_password">.*?</page>',text,re.S)
    password=ET.fromstring(match[0]);entry=password.find('input')
    # GUIInput paints its initial GUIText before loading the mask. The data
    # binding supplies masked displayValue later; never put the secret in the
    # constructor's literal text.
    entry.find('text').text=''
    entry.find('data').set('mask','*')
    cursor=entry.find('cursor')
    if cursor is None:cursor=add(entry,'cursor')
    cursor.set('hasfocus','1');cursor.set('color','#E31B36')
    for action in password.findall('action'):
        if action.find('touch') is not None:
            for previous in list(action.findall('action')):
                if previous.get('function')=='set' and previous.text=='tw_wlan_password=':
                    action.remove(previous)
            clear=node('action',function='set');clear.text='tw_wlan_password='
            action.insert(1,clear)
    return text[:match.start()]+serialize([password]).strip()+text[match.end():]


def position_unlock_label(text):
    match=re.search(r'<page name="lock">.*?</page>',text,re.S)
    if not match:raise ValueError('Native lock page missing')
    page=ET.fromstring(match[0]);slider=page.find('slider')
    if slider is None:raise ValueError('Native unlock slider missing')
    placement=slider.find('placement')
    if placement is None:placement=node('placement');slider.insert(0,placement)
    placement.attrib.update(x='%center_x%',y='%row23_y%',labelcenter='1',labeloffsety='56')
    return text[:match.start()]+serialize([page]).strip()+text[match.end():]


def list_caption(item):
    caption=item.get('name','')
    if caption.startswith('{@') and caption.endswith('}') and '=' in caption:
        caption=caption.split('=',1)[1][:-1]
    return caption.strip()


def verify_advanced_cleanup(recovery,current=None):
    source=subprocess.check_output(['git','-C',str(recovery),'show','HEAD:gui/theme/common/portrait.xml'])
    baseline=ET.fromstring(source)
    if current is None:current=ET.parse(recovery/'gui/theme/common/portrait.xml').getroot()
    path="pages/page[@name='advanced']/listbox/listitem"
    original={n.get('name'):n for n in baseline.findall(path)}
    actual={n.get('name'):n for n in current.findall(path)}
    removed={'{@disable_avb2=Disable AVB2.0}','{@reboot_install_app_hdr=Install TWRP App}'}
    extras={'AVB Tools','Charging','FTP Menu','Flash Magisk'}
    if not removed.issubset(original) or set(actual)!=(set(original)-removed)|extras:
        raise ValueError('Advanced cleanup has unexpected missing or extra items')
    def canonical(n):
        n=copy.deepcopy(n);n.tail=None
        return ET.canonicalize(ET.tostring(n,encoding='unicode'),strip_text=True)
    for name,item in original.items():
        if name not in removed and canonical(item)!=canonical(actual[name]):
            raise ValueError('Native Advanced item actions/conditions changed: '+name)


def alphabetize_advanced(text):
    page=re.search(r'<page name="advanced">.*?</page>',text,re.S)
    if not page:raise ValueError('Native Advanced page missing')
    match=re.search(r'<listbox style="advanced_listbox">.*?</listbox>',page[0],re.S)
    if not match:raise ValueError('Native Advanced list missing')
    box=ET.fromstring(match[0]);items=box.findall('listitem')
    if not items:raise ValueError('Native Advanced list is empty')
    for item in items:box.remove(item)
    for item in sorted(items,key=lambda n:list_caption(n).casefold()):box.append(item)
    replacement=serialize([box]).strip()
    updated=page[0][:match.start()]+replacement+page[0][match.end():]
    return text[:page.start()]+updated+text[page.end():]


def dashboard(layout,theme,classic):
    p=node("page",name="main2");add(p,"background",color=layout["background"])
    image(p,"oxy_wave",460,62);image(p,"oxy_logo",56,106)
    label(p,"Recovery",190,94,"oxy_title")
    label(p,"OnePlus 15 · TWRP %tw_version%",192,168,"oxy_subtitle",color="#BFC0C7")
    for q in layout["pills"]:image(p,"oxy_pill_"+q["id"],*q["box"][:2])
    image(p,"oxy_icon_slot_32",82,258);label(p,"%tw_op15_dashboard_slot%",128,254,"oxy_small")
    image(p,"oxy_icon_crypto_32",300,258);label(p,"%tw_op15_dashboard_crypto%",348,254,"oxy_small")
    image(p,"oxy_icon_storage_32",564,258)
    n=image(p,"oxy_dot_unknown",616,268);cond(n,"tw_op15_dashboard_storage_ready","1","!=")
    n=image(p,"oxy_dot_ready",616,268);cond(n,"tw_op15_dashboard_storage_ready")
    label(p,"%tw_op15_dashboard_storage%",648,254,"oxy_small")
    for c in layout["cards"]:
        x,y,_,_=c["box"];image(p,"oxy_card_"+c["id"],x,y)
        fill(p,layout["accent"],x+40,y+30,6,34);label(p,c["label"],x+64,y+23,"oxy_section")
    for b in layout["buttons"]:
        x,y,w,h=b["box"];res=f"oxy_button_{w}_{h}"+("_red" if b.get("red") else "")
        n=add(p,"button",name="oxy_"+b["id"]);place(n,x,y)
        add(n,"font",resource="oxy_body",color="#FFFFFF");add(n,"text")
        add(n,"image",resource=res,highlightresource=res+"_pressed");cond(n,"tw_busy","0")
        for a in source_actions(theme,classic,b["source"]):n.append(a)
        cap=b.get("capability")
        if cap:cond(n,cap)
        kind=b["kind"]
        if kind=="device":
            image(p,f"oxy_icon_{b['icon']}_64",x+(w-64)//2,y+22)
            label(p,b["label"],x+w//2,y+94,"oxy_body",align=5)
        else:
            size=64 if kind=="large" else (44 if kind=="quick" else 56)
            ix=x+(64 if kind=="large" else (24 if kind=="quick" else 30))
            icon_node=image(p,f"oxy_icon_{b['icon']}_{size}",ix,y+(h-size)//2)
            if b['id']=='wifi':
                cond(icon_node,'tw_wifi_connected','1','!=')
                connected=image(p,'oxy_icon_wifi_connected_56',ix,y+(h-size)//2)
                cond(connected,'tw_wifi_connected')
            elif b['id']=='charging':
                cond(icon_node,'tw_op15_dashboard_charging','1','!=')
                connected=image(p,'oxy_icon_charging_active_56',ix,y+(h-size)//2)
                cond(connected,'tw_op15_dashboard_charging')
            tx=x+(174 if kind=="large" else (98 if kind=="quick" else 124))
            font="oxy_body" if kind=="large" else ("oxy_quick" if kind=="quick" else "oxy_small")
            parts=b["label"].split("|");lineh=30 if kind=="quick" else 40
            for i,t in enumerate(parts):label(p,t,tx,y+h//2-len(parts)*lineh//2+i*lineh-3,font)
        if cap:
            n=fill(p,"#09090DA0",x,y,w,h);cond(n,cap,"1","!=")
    # Classic navigation, not the removed Classic theme. Spacious hit targets.
    fill(p,'#000000',0,1710,1080,210)
    for name,center,res,function,target in (
        ('back',240,'back','key','back'),('home',540,'home','key','home'),
        ('logs',840,'console','overlay','slideout')):
        n=add(p,'button',name='oxy_'+name);place(n,center-96,1712,192,128)
        # A real native-size image makes the large native GUIButton hit geometry
        # explicit instead of depending on the fill-only widget fallback.
        add(n,'image',resource='oxy_nav_hitbox')
        add(n,'fill',color='#000000');add(n,'font',resource='oxy_caption',color='#EEEEEE');add(n,'text')
        cond(n,'tw_busy','0');add(n,'action',function=function).text=target
        icon_node=add(p,'image');add(icon_node,'image',resource=res);place(icon_node,center,1776,align=4)
    for key,function,arg in (("home","page","main"),("back","page","main"),("power","togglebacklight",None),("power+voldown","screenshot",None)):
        n=add(p,"action");add(n,"touch",key=key);add(n,"action",function=function).text=arg
    add(p,"template",name="oxygenos_status")
    return p


def patch(recovery):
    common=recovery/"gui/theme/common/portrait.xml";ui=recovery/"gui/theme/portrait_hdpi/ui.xml"
    ct=common.read_text();ut=ui.read_text();theme=ET.fromstring(ct)
    # Only read the pinned native actions at build time. No Classic page ships.
    classic=native_main(recovery)
    layout=json.loads((ASSETS/"dashboard.json").read_text());manifest=json.loads((ASSETS/"manifest.json").read_text())
    resources=[]
    for name,size in (("oxy_title",64),("oxy_subtitle",32),("oxy_section",38),("oxy_body",38),("oxy_small",32),("oxy_status",34),("oxy_caption",28),("oxy_quick",29),("oxy_value",38)):
        resources.append(node("font",name=name,filename="RobotoCondensed-Regular.ttf",size=size))
    for name,meta in sorted(manifest.items()):
        data=base64.b64decode((ASSETS/(name+".png.b64")).read_bytes(),validate=False)
        if hashlib.sha256(data).hexdigest()!=meta["sha256"] or len(data)!=meta["bytes"]:raise ValueError("Asset checksum mismatch: "+name)
        if data[:8]!=b"\x89PNG\r\n\x1a\n" or struct.unpack(">II",data[16:24])!=tuple(meta["size"]):raise ValueError("Asset dimensions mismatch: "+name)
        if len(data)>65536 or meta["size"][0]*meta["size"][1]>1080*420:raise ValueError("Oversized asset: "+name)
        dest=recovery/"gui/theme/portrait_hdpi/images"/(name+".png")
        if not dest.exists() or dest.read_bytes()!=data:dest.write_bytes(data)
        resource=node("image",name=name,filename=name)
        if name.startswith("oxy_icon_") or name.startswith("oxy_dot_") or name=="oxy_logo":
            resource.set("retainaspect","1")
        resources.append(resource)
    # Preserve retired generated files outside packaged theme resources.
    for retired in ('oxy_home_bar','oxy_footer','oxy_icon_battery_56','oxy_icon_thermometer_56','oxy_icon_backup_56','oxy_shared_logo'):
        old=recovery/'gui/theme/portrait_hdpi/images'/(retired+'.png')
        if old.exists() and retired not in manifest:
            archive=recovery/'.op15-retired-assets';archive.mkdir(exist_ok=True)
            old.replace(archive/old.name)
    ut=insert(ut,"resources",serialize(resources),"</resources>")
    ut=insert(ut,"templates",serialize([status_template(ut)]),"</templates>")
    pages=serialize([dashboard(layout,theme,classic)])
    s=f"{START} pages -->";e=f"{END} pages -->"
    if s in ct:ct=re.sub(re.escape(s)+".*?"+re.escape(e),lambda _:block("pages",pages),ct,flags=re.S)
    else:
        ct,count=re.subn(r'<page name="main2">.*?</page>',lambda _:block("pages",pages),ct,count=1,flags=re.S)
        if count!=1:raise ValueError("Ambiguous main2 replacement")
    ct=patch_log_overlay(ct)
    ct=inset_paired_buttons(ct)
    ct=remove_wlan_subtitle(ct)
    ct=modern_wlan(ct,recovery)
    ct=inset_paired_buttons(ct)  # Native Tools actions were freshly copied.
    defaults=[node('variable',name='tw_op15_wifi_tools',value='0'),
              node('variable',name='tw_op15_wifi_back',value='advanced'),
              node('variable',name='tw_wlan_network_count',value='0'),
              node('variable',name='tw_op15_wlan_scan_status',value='Tap Scan to refresh')]
    ut=insert(ut,'wifi-variables',serialize(defaults),'</variables>')
    ct=alphabetize_advanced(ct)
    ct=position_unlock_label(ct)
    ut=shared_theme(ut)
    patch_splash(recovery)
    ET.fromstring(ct);ET.fromstring(ut)
    for path,value in ((common,ct),(ui,ut)):
        if path.read_text()!=value:path.write_text(value)
    print(f"[oxygenos-ui] Native 1080x1920 dashboard: {len(layout['buttons'])} real actions, {len(manifest)} small assets")


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument("recovery",type=Path)
    p.add_argument('--verify-advanced-cleanup',action='store_true');a=p.parse_args()
    if a.verify_advanced_cleanup:
        verify_advanced_cleanup(a.recovery.resolve());print('Advanced cleanup verified independent of item order')
    else:patch(a.recovery.resolve())


if __name__=="__main__":
    try:main()
    except (OSError,ValueError,ET.ParseError) as e:print("OxygenOS dashboard FAILED: "+str(e),file=sys.stderr);sys.exit(1)
