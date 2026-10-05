from pathlib import Path
import colorsys
from PIL import Image, ImageDraw, ImageFont
from racers import RACERS, RACER_ORDER

OUT=Path(__file__).resolve().parent/'static'/'roles'
OUT.mkdir(parents=True,exist_ok=True)
FONT='/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc'
for i,key in enumerate(RACER_ORDER):
    h=i/len(RACER_ORDER)
    r,g,b=[int(x*255) for x in colorsys.hsv_to_rgb(h,0.62,0.95)]
    im=Image.new('RGB',(512,512),(r,g,b)); d=ImageDraw.Draw(im)
    # comic burst
    for rad in range(230,40,-28):
        alpha = int(25 + (230-rad)*0.15)
        c=(min(255,r+alpha),min(255,g+alpha),min(255,b+alpha))
        d.ellipse((256-rad,256-rad,256+rad,256+rad),outline=c,width=10)
    d.ellipse((42,42,470,470),fill=(255,255,255),outline=(20,20,20),width=14)
    name=RACERS[key].name_zh
    fbig=ImageFont.truetype(FONT,78 if len(name)<=4 else 62)
    fsmall=ImageFont.truetype(FONT,32)
    short=name[:2]
    bb=d.textbbox((0,0),short,font=fbig)
    d.text(((512-(bb[2]-bb[0]))/2,170),short,font=fbig,fill=(r,g,b),stroke_width=4,stroke_fill=(20,20,20))
    bb=d.textbbox((0,0),name,font=fsmall)
    d.rounded_rectangle((32,390,480,470),radius=24,fill=(250,247,235),outline=(20,20,20),width=6)
    d.text(((512-(bb[2]-bb[0]))/2,408),name,font=fsmall,fill=(20,20,20))
    im.save(OUT/f'{key}.png')
print(f'created {len(RACER_ORDER)} placeholders in {OUT}')
