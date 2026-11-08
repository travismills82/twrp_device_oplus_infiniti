#!/usr/bin/env python3
"""Host-only appearance fixture from generated native resources, not a phone screenshot."""
from pathlib import Path
import argparse
from PIL import Image, ImageDraw, ImageFont

p=argparse.ArgumentParser(description=__doc__)
p.add_argument('recovery',type=Path);p.add_argument('output',type=Path);a=p.parse_args()
theme=a.recovery/'gui/theme';images=theme/'portrait_hdpi/images'
def asset(name):return Image.open(images/(name+'.png')).convert('RGBA')
canvas=Image.new('RGBA',(1080,850),'#000000');draw=ImageDraw.Draw(canvas)
fontfile=theme/'common/fonts/RobotoCondensed-Regular.ttf'
font=ImageFont.truetype(str(fontfile),42);small=ImageFont.truetype(str(fontfile),26)
draw.text((36,12),'HOST FIXTURE — native artwork; simulated progress values',font=small,fill='#AAAAAA')
empty=asset('oxy_shared_progress_empty');full=asset('oxy_shared_progress_full')
w,h=empty.size;cap=h//2
for value,y in ((3,120),(56,270),(100,420)):
    canvas.alpha_composite(empty,(36,y))
    visible=min(w,max(h,w*value//100));body=visible-cap
    canvas.alpha_composite(full.crop((0,0,body,h)),(36,y))
    canvas.alpha_composite(full.crop((w-cap,0,w,h)),(36+body,y))
    draw.text((540,y-16),str(value)+'%',font=font,fill='#E31B36',anchor='ms')
base=asset('oxy_shared_slider');used=asset('oxy_shared_slider_used');thumb=asset('oxy_shared_slider_touch')
offset=400;fill=min(base.width,offset+min(thumb.size)//2);x,y=72,580
canvas.alpha_composite(base,(x,y));canvas.alpha_composite(used.crop((0,0,fill,used.height)),(x,y))
canvas.alpha_composite(thumb,(x+offset,y))
draw.text((540,y+135),'Swipe to Unlock',font=ImageFont.truetype(str(fontfile),36),fill='#EEEEEE',anchor='mt')
canvas.convert('RGB').save(a.output)
