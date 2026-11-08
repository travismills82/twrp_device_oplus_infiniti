#!/usr/bin/env python3
"""Developer-only renderer for our small geometric recipes (requires Pillow).

This never reads the reference screenshot or imports theme packs. The build
extractor uses only stdlib and checked-in base64 PNGs. Existing fonts are reused.
"""
from __future__ import annotations
import argparse
import base64
import hashlib
import json
import math
from pathlib import Path
from PIL import Image, ImageDraw, ImageFilter

DEVICE=Path(__file__).resolve().parents[1]
AA=3


def rounded(w,h,red=False,pressed=False,radius=30,panel=False,footer=False):
    mask=Image.new("L",(w*AA,h*AA)); d=ImageDraw.Draw(mask)
    d.rounded_rectangle((1,1,w*AA-2,h*AA-2),radius=radius*AA,fill=255)
    mask=mask.resize((w,h),Image.Resampling.LANCZOS)
    im=Image.new("RGBA",(w,h));d=ImageDraw.Draw(im)
    a,b=((239,38,62),(115,13,31)) if red else (((39,28,32),(17,17,21)) if footer else (((29,30,34),(17,18,22)) if panel else ((46,47,53),(31,32,37))))
    for y in range(h):
        t=y/max(1,h-1)
        color=tuple(min(255,round(v+(b[i]-v)*t)+(14 if pressed else 0)) for i,v in enumerate(a))+(255,)
        d.line((0,y,w,y),fill=color)
    im.putalpha(mask)
    edge=Image.new("RGBA",(w*AA,h*AA));d=ImageDraw.Draw(edge)
    c=(245,76,94,150) if red else ((119,67,77,150) if footer else (109,110,119,95))
    d.rounded_rectangle((2,2,w*AA-3,h*AA-3),radius=radius*AA,outline=c,width=AA)
    return Image.alpha_composite(im,edge.resize((w,h),Image.Resampling.LANCZOS))


def icon(name,size,color="#F8F8FA"):
    im=Image.new("RGBA",(size*AA,size*AA));d=ImageDraw.Draw(im)
    s=size*AA/24;white=color;width=round(1.5*s)
    def line(ps,closed=False):
        ps=[(round(x*s),round(y*s)) for x,y in ps]
        if closed:ps.append(ps[0])
        d.line(ps,fill=white,width=width,joint="curve")
        for x,y in (ps[0],ps[-1]):
            r=width/2;d.ellipse((x-r,y-r,x+r,y+r),fill=white)
    def rect(box):d.rounded_rectangle(tuple(round(v*s) for v in box),radius=round(1.3*s),outline=white,width=width)
    def arc(box,a,b):d.arc(tuple(round(v*s) for v in box),a,b,fill=white,width=width)
    def dot(x,y,r=.8):d.ellipse(((x-r)*s,(y-r)*s,(x+r)*s,(y+r)*s),fill=white)
    if name=="install":
        line([(12,2),(12,15)]);line([(7,10),(12,15),(17,10)]);line([(2,15),(2,21),(22,21),(22,15)])
    elif name=="wipe":
        rect((6,6,19,23));line([(3,6),(22,6)]);line([(9,6),(9,2),(16,2),(16,6)]);line([(10,10),(10,19)]);line([(15,10),(15,19)])
    elif name=="backup":
        line([(2,7),(12,2),(22,7),(12,12)],True);line([(2,12),(12,17),(22,12)]);line([(2,17),(12,22),(22,17)])
    elif name in ("restore","recovery"):
        arc((2,2,23,23),-148,145);line([(2,3),(2,9),(8,9)])
        line([(12,7),(12,13),(17,16)] if name=="restore" else [(22,21),(22,15),(16,15)])
    elif name=="mount":
        line([(2,14),(6,4),(18,4),(22,14)]);rect((2,14,22,21));dot(15,18);dot(19,18)
    elif name=="settings":
        pts=[]
        for i in range(24):
            a=math.pi*i/12;r=10 if i%4 in (0,1) else 8;pts.append((12+math.cos(a)*r,12+math.sin(a)*r))
        line(pts,True);arc((8,8,16,16),0,360)
    elif name=="advanced":
        line([(2,7),(7,7)]);line([(12,7),(22,7)]);line([(2,17),(13,17)]);line([(18,17),(22,17)]);arc((6,4,12,10),0,360);arc((12,14,18,20),0,360)
    elif name=="reboot":arc((2,2,22,23),-55,235);line([(12,1),(12,11)])
    elif name=="wifi":arc((0,2,24,26),215,325);arc((4,8,20,24),215,325);arc((8,14,16,22),215,325);dot(12,22,1)
    elif name=="files":line([(2,5),(9,5),(12,8),(22,8),(22,21),(2,21)],True)
    elif name=="document":
        line([(4,2),(14,2),(21,9),(21,23),(4,23)],True)
        line([(14,2),(14,9),(21,9)])
    elif name=="charging":line([(14,1),(4,14),(11,14),(10,23),(21,9),(14,9)],True)
    elif name=="terminal":line([(3,4),(11,12),(3,20)]);line([(13,20),(23,20)])
    elif name in ("ftp","storage"):
        rect((2,3,22,10));rect((2,14,22,21))
        for y in (6.5,17.5):dot(16,y,.6);dot(19,y,.6)
    elif name=="sideload":rect((4,2,20,18));line([(1,21),(23,21)])
    elif name=="android":
        arc((2,7,22,27),180,360);line([(2,17),(22,17)]);line([(6,3),(9,8)]);line([(18,3),(15,8)]);dot(8,12);dot(16,12)
    elif name in ("lock","crypto"):
        rect((4,10,20,23));arc((7,1,17,15),180,360);line([(7,7),(7,10)]);line([(17,7),(17,10)])
    elif name=="fastbootd":line([(2,5),(11,12),(2,19)],True);line([(13,5),(22,12),(13,19)],True)
    elif name=="slot":rect((5,1,19,23));line([(8,20),(16,20)])
    elif name=="battery":rect((5,3,20,23));line([(10,3),(10,1),(15,1),(15,3)])
    elif name=="thermometer":
        arc((8,0,16,8),180,360);line([(8,4),(8,16)]);line([(16,4),(16,16)]);arc((6,13,18,25),-48,228);line([(12,7),(12,19)]);dot(12,19,1.8)
    else:raise ValueError(name)
    return im.resize((size,size),Image.Resampling.LANCZOS)


def wave():
    w,h=620,260;mask=Image.new("L",(w*AA,h*AA));d=ImageDraw.Draw(mask)
    def curve(p0,p1,p2,p3):
        return [tuple((1-t)**3*p0[k]+3*(1-t)**2*t*p1[k]+3*(1-t)*t*t*p2[k]+t**3*p3[k] for k in (0,1)) for t in (i/120 for i in range(121))]
    top=curve((140,182),(285,120),(350,20),(620,4));lower=curve((620,12),(360,86),(310,96),(140,182))
    d.polygon([(x*AA,y*AA) for x,y in top+lower],fill=140)
    mask=mask.resize((w,h),Image.Resampling.LANCZOS)
    glow=mask.filter(ImageFilter.GaussianBlur(28)).point(lambda p:min(90,p*2))
    im=Image.new("RGBA",(w,h),(210,12,35,0));im.putalpha(glow)
    tint=Image.new("RGBA",(w,h),(219,18,43,0));tint.putalpha(mask);im=Image.alpha_composite(im,tint)
    edge=Image.new("RGBA",(w*AA,h*AA));ImageDraw.Draw(edge).line([(x*AA,y*AA) for x,y in top],fill=(239,33,62,170),width=2*AA)
    return Image.alpha_composite(im,edge.resize((w,h),Image.Resampling.LANCZOS))


def generate():
    layout=json.loads((DEVICE/"assets/twrp-theme/oxygenos/dashboard.json").read_text())
    logo=Image.new("RGBA",(112*AA,112*AA));d=ImageDraw.Draw(logo)
    d.ellipse((0,0,112*AA-1,112*AA-1),fill="#EE1935")
    for ps in ([(43,0),(58,0),(58,29),(77,29),(54,59),(31,29),(43,29)],[(69,112),(54,112),(54,83),(35,83),(58,53),(81,83),(69,83)]):
        d.polygon([(round(x*AA),round(y*AA)) for x,y in ps],fill="#09090D")
    result={"oxy_wave":wave(),"oxy_logo":logo.resize((96,96),Image.Resampling.LANCZOS),
            "oxy_nav_hitbox":Image.new('RGBA',(192,128),'#000000')}
    # Shared replacements: ordinary action buttons are intentionally slimmer;
    # sliders, tabs, selectors and icon dimensions retain their native geometry.
    controls=json.loads((DEVICE/"assets/twrp-theme/oxygenos/shared-controls.json").read_text())
    for name,meta in controls.items():
        w,h=meta['size'];kind=meta['kind'];selected=name.endswith('_true')
        if kind in ('button','red','arrow'):
            im=rounded(w,h,red=kind!='button',radius=min(28,h//3))
            if kind=='arrow':im.alpha_composite(icon('fastbootd',72),((w-72)//2,(h-72)//2))
        elif kind=='logo':im=logo.resize((w,h),Image.Resampling.LANCZOS)
        elif kind=='folder_fab':
            im=Image.new('RGBA',(w*AA,h*AA));draw=ImageDraw.Draw(im)
            draw.ellipse((16*AA,4*AA,200*AA,188*AA),fill='#E31B36')
            im=im.resize((w,h),Image.Resampling.LANCZOS)
            im.alpha_composite(icon('files',80),((w-80)//2,(h-80)//2))
        elif kind=='file_icon':
            im=Image.new('RGBA',(w,h));im.alpha_composite(icon('document',64),((w-64)//2,(h-64)//2))
        elif kind=='enter_key':
            im=Image.new('RGBA',(w*AA,h*AA));draw=ImageDraw.Draw(im)
            draw.polygon([(x*AA,y*AA) for x,y in ((26,26),(135,26),(135,99),(99,135),(26,135))],fill='#E31B36')
            draw.line([(60*AA,82*AA),(74*AA,96*AA),(104*AA,65*AA)],fill='#FFFFFF',width=7*AA,joint='curve')
            im=im.resize((w,h),Image.Resampling.LANCZOS)
        elif kind in ('progress_track','progress_fill'):
            im=Image.new('RGBA',(w*AA,h*AA));draw=ImageDraw.Draw(im)
            if kind=='progress_fill':
                draw.rounded_rectangle((8*AA,8*AA,(w-8)*AA,(h-8)*AA),radius=(h-16)*AA//2,fill='#E31B36')
                im=im.resize((w,h),Image.Resampling.LANCZOS)
            else:
                draw.rounded_rectangle((4*AA,4*AA,(w-4)*AA,(h-4)*AA),radius=(h-8)*AA//2,outline='#E31B36',width=2*AA)
                edge=im.resize((w,h),Image.Resampling.LANCZOS)
                glow=edge.filter(ImageFilter.GaussianBlur(3))
                im=Image.alpha_composite(glow,edge)
            im=im.quantize(colors=32,method=Image.Quantize.FASTOCTREE,dither=Image.Dither.NONE).convert('RGBA')
        else:
            im=Image.new('RGBA',(w*AA,h*AA));draw=ImageDraw.Draw(im)
            box=tuple(v*AA for v in (14,26,58,70));paint='#E31B36' if selected or kind=='handle' else '#888890'
            if kind=='checkbox':
                draw.rounded_rectangle(box,radius=5*AA,fill=paint if selected else None,outline=paint,width=3*AA)
                if selected:draw.line([(23*AA,47*AA),(33*AA,57*AA),(51*AA,37*AA)],fill='#FFFFFF',width=4*AA,joint='curve')
            elif kind=='radio':
                draw.ellipse(box,outline=paint,width=3*AA)
                if selected:draw.ellipse(tuple(v*AA for v in (24,36,48,60)),fill=paint)
            elif kind=='handle':draw.rounded_rectangle(tuple(v*AA for v in (8,24,64,84)),radius=28*AA,fill=paint)
            im=im.resize((w,h),Image.Resampling.LANCZOS)
        if kind in ('folder_fab','file_icon'):
            # These flat native icons need few colors; retain RGBA transparency
            # while bounding the total theme payload, including antialiasing.
            im=im.quantize(colors=16,method=Image.Quantize.FASTOCTREE,dither=Image.Dither.NONE).convert('RGBA')
        result[meta['asset']]=im
    result['oxy_splash_logo']=logo.resize((500,500),Image.Resampling.LANCZOS)
    for full in (False,True):
        im=Image.new("RGBA",(48*AA,28*AA));d=ImageDraw.Draw(im)
        d.rounded_rectangle((AA,AA,43*AA,27*AA),radius=4*AA,outline="#F8F8FA",width=2*AA)
        d.rounded_rectangle((44*AA,8*AA,47*AA,20*AA),radius=AA,fill="#F8F8FA")
        if full:d.rounded_rectangle((5*AA,5*AA,39*AA,23*AA),radius=AA,fill="#F8F8FA")
        result["oxy_battery_"+("full" if full else "empty")]=im.resize((48,28),Image.Resampling.LANCZOS)
    for ready in (False,True):
        im=Image.new("RGBA",(14*AA,14*AA));ImageDraw.Draw(im).ellipse((0,0,14*AA-1,14*AA-1),fill="#39DD87" if ready else "#909099")
        result["oxy_dot_"+("ready" if ready else "unknown")]=im.resize((14,14),Image.Resampling.LANCZOS)
    for c in layout["cards"]:result["oxy_card_"+c["id"]]=rounded(*c["box"][2:],panel=True,radius=36)
    for p in layout["pills"]:result["oxy_pill_"+p["id"]]=rounded(*p["box"][2:],radius=30)
    for b in layout["buttons"]:
        w,h=b["box"][2:];name=f"oxy_button_{w}_{h}"+("_red" if b.get("red") else "")
        for pressed in (False,True):
            key=name+("_pressed" if pressed else "")
            if key not in result:result[key]=rounded(w,h,red=b.get("red",False),pressed=pressed)
    groups={32:("slot","crypto","storage","thermometer"),44:("android","recovery","lock","fastbootd"),56:("wifi","files","terminal","ftp","sideload","charging"),64:("install","wipe","backup","restore","mount","settings","advanced","reboot")}
    for size,names in groups.items():
        for name in names:result[f"oxy_icon_{name}_{size}"]=icon(name,size)
    result['oxy_icon_wifi_connected_56']=icon('wifi',56,'#39DD87')
    result['oxy_icon_charging_active_56']=icon('charging',56,'#39DD87')
    # Keep the native twelve-frame animation protocol and dimensions. These
    # tiny transparent frames replace only the old blue streaming artwork.
    for i in range(12):
        im=Image.new('RGBA',(1008*AA,64*AA));draw=ImageDraw.Draw(im)
        left=-168+i*(1008+168)//11;right=left+168
        if right>0 and left<1008:
            draw.rounded_rectangle((left*AA,8*AA,(right-1)*AA,56*AA),radius=24*AA,fill='#E31B36')
        im=im.resize((1008,64),Image.Resampling.LANCZOS)
        im=im.quantize(colors=16,method=Image.Quantize.FASTOCTREE,dither=Image.Dither.NONE).convert('RGBA')
        result[f'oxy_indeterminate{i+1:03d}']=im
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument("output",type=Path);parser.add_argument("--json",action="store_true")
    parser.add_argument('--install-sources',action='store_true',help='Regenerate checked base64 sources and manifest from the recipes')
    args=parser.parse_args();args.output.mkdir(parents=True,exist_ok=True);bundle={}
    for name,im in generate().items():
        path=args.output/(name+".png");im.save(path,optimize=True,compress_level=9);data=path.read_bytes()
        bundle[name]={"base64":base64.encodebytes(data).decode(),"bytes":len(data),"sha256":hashlib.sha256(data).hexdigest(),"size":list(im.size)}
    if args.install_sources:
        assets=DEVICE/'assets/twrp-theme/oxygenos'
        for name,meta in bundle.items():(assets/(name+'.png.b64')).write_text(meta['base64'])
        (assets/'manifest.json').write_text(json.dumps({k:{n:v for n,v in m.items() if n!='base64'} for k,m in bundle.items()},indent=2)+'\n')
    print(json.dumps(bundle) if args.json else f"Rendered {len(bundle)} assets, {sum(m['bytes'] for m in bundle.values())} PNG bytes")


if __name__=="__main__":main()
