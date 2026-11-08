#!/usr/bin/env python3
"""Host visual QA of the generated native XML (NOT an on-device screenshot).

Uses the packaged PNGs, fonts, placements and conditions. Fixture values are
explicitly synthetic and are never injected into recovery XML or the image.
Developer-only: Pillow is not a recovery or normal build dependency.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import re
import xml.etree.ElementTree as ET
from PIL import Image, ImageColor, ImageDraw, ImageFont


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument("recovery",type=Path);p.add_argument("output",type=Path)
    p.add_argument("--state",choices=("locked","decrypted","unknown"),default="locked");a=p.parse_args()
    theme=a.recovery/"gui/theme";ui=ET.parse(theme/"portrait_hdpi/ui.xml").getroot();portrait=ET.parse(theme/"common/portrait.xml").getroot()
    variables={n.get("name"):n.get("value") for n in ui.findall("variables/variable")}
    variables.update(tw_busy="0",tw_time="10:08 AM",tw_version="3.7.1_16-OnePlus_15",tw_wifi_connected="1",tw_battery="72% ",tw_no_cpu_temp="0",tw_op15_dashboard_cpu="41 °C",tw_op15_dashboard_battery="72%",tw_op15_dashboard_battery_valid="1",tw_reboot_system="1",tw_reboot_recovery="1",tw_reboot_bootloader="1",tw_fastboot_mode="1",tw_op15_dashboard_slot="Slot A",tw_op15_dashboard_crypto="Encrypted",tw_op15_dashboard_storage="Internal storage locked",tw_op15_dashboard_storage_ready="0")
    if a.state=="decrypted":variables.update(tw_op15_dashboard_crypto="Decrypted",tw_op15_dashboard_storage="Internal storage mounted",tw_op15_dashboard_storage_ready="1")
    if a.state=="unknown":variables.update(tw_op15_dashboard_slot="Unknown",tw_op15_dashboard_crypto="Unknown",tw_op15_dashboard_storage="Storage unavailable",tw_op15_dashboard_storage_ready="0",tw_op15_dashboard_cpu="Unavailable",tw_op15_dashboard_battery="Unavailable",tw_op15_dashboard_battery_valid="0",tw_wifi_connected="0")
    def expand(s):
        s=re.sub(r'%([^%]+)%',lambda m:variables.get(m[1],""),s or "")
        return re.sub(r'\{@[^=]+=(.*?)\}',r'\1',s)
    def valid(n):
        for c in list(n.findall("condition"))+list(n.findall("conditions/condition")):
            lhs=variables.get(c.get("var1"),"");rhs=c.get("var2","");op=c.get("op","=")
            if op in ("=","==") and lhs!=rhs:return False
            if op=="!=" and lhs==rhs:return False
            if op in (">=","<=",">","<"):
                x,y=float(lhs or -1),float(rhs)
                if not {">=":x>=y,"<=":x<=y,">":x>y,"<":x<y}[op]:return False
        return True
    def color(s):return ImageColor.getcolor(expand(s),"RGBA")
    resources={n.get("name"):n for n in ui.find("resources")}
    fonts={};images={}
    for name,n in resources.items():
        if n.tag=="font":fonts[name]=ImageFont.truetype(str(theme/"common/fonts"/n.get("filename")),int(n.get("size")))
        if n.tag=="image":
            path=theme/"portrait_hdpi/images"/(n.get("filename")+".png")
            if path.exists():images[name]=Image.open(path).convert("RGBA")
    canvas=Image.new("RGBA",(1080,1920),(9,9,13,255));bounds=[]
    def draw_text(value,x,y,font_name,paint,align=None):
        f=fonts[font_name];value=expand(value);w=round(f.getlength(value))
        if align in ("1","3"):x-=w
        elif align in ("4","5"):x-=w//2
        ImageDraw.Draw(canvas).text((x,y),value,font=f,fill=paint)
        box=f.getbbox(value);bounds.append({"text":value,"box":[x+box[0],y+box[1],x+box[2],y+box[3]],"font":font_name})
    def draw(n):
        if not valid(n):return
        t=n.tag;q=n.find("placement");x=int(expand(q.get("x","0"))) if q is not None else 0;y=int(expand(q.get("y","0"))) if q is not None else 0
        if t=="template":
            target=ui.find(f"templates/template[@name='{n.get('name')}']")
            for child in target:draw(child)
        elif t=="background":canvas.paste(color(n.get("color")),(0,0,1080,1920))
        elif t=="fill":
            w,h=int(expand(q.get("w"))),int(expand(q.get("h")));layer=Image.new("RGBA",canvas.size)
            ImageDraw.Draw(layer).rectangle((x,y,x+w-1,y+h-1),fill=color(n.get("color")));canvas.alpha_composite(layer)
        elif t=="image":
            im=images[n.find("image").get("resource")]
            align=q.get('placement','0')
            if align in ('1','3'):x-=im.width
            if align in ('2','3'):y-=im.height
            if align in ('4','5'):x-=im.width//2
            if align=='4':y-=im.height//2
            canvas.alpha_composite(im,(x,y))
        elif t=="text":
            f=n.find("font");draw_text(n.findtext("text"),x,y,f.get("resource"),color(n.get("color",f.get("color","#FFFFFF"))),q.get("placement"))
        elif t=="button":
            im=n.find("image")
            if im is not None:canvas.alpha_composite(images[im.get("resource")],(x,y));w,h=images[im.get("resource")].size
            else:
                w,h=int(q.get("w")),int(q.get("h"));ImageDraw.Draw(canvas).rectangle((x,y,x+w,y+h),fill=color(n.find("fill").get("color")))
            if n.findtext("text"):
                f=n.find("font");font=fonts[f.get("resource")];height=font.getbbox(n.findtext("text"))[3]
                draw_text(n.findtext("text"),x+w//2,y+(h-height)//2,f.get("resource"),color(f.get("color","#FFFFFF")),"5")
        elif t=="progressbar":
            r=n.find("resource");empty=images[r.get("empty")];full=images[r.get("full")];canvas.alpha_composite(empty,(x,y))
            w=round(full.width*.72);canvas.alpha_composite(full.crop((0,0,w,full.height)),(x,y))
    for n in portrait.find("pages/page[@name='main2']"):draw(n)
    a.output.parent.mkdir(parents=True,exist_ok=True);canvas.convert("RGB").save(a.output)
    a.output.with_suffix(".bounds.json").write_text(json.dumps({"synthetic_fixture":True,"state":a.state,"text_bounds":bounds},indent=2))
    print(f"Host-only {a.state} fixture preview: {a.output}")


if __name__=="__main__":main()
