# «эталон / было / стало»: python3 ref_triple.py <DIR со снимками refshots/..> <OUT> [масштаб]; файлы ref-*, was-*, now-*
# «эталон / было / стало»: три кадра рядом (телефон) или друг под другом (1366), с подписями
import sys
from PIL import Image, ImageDraw, ImageFont
S=sys.argv[1]; out=sys.argv[2]; scale=float(sys.argv[3]) if len(sys.argv)>3 else 0.5
try: font=ImageFont.truetype('/usr/share/fonts/opentype/inter/Inter-SemiBold.otf', 22)
except Exception: font=ImageFont.load_default()
labels=[('ref','эталон A (REFERENCE.html)'),('was','было · R01 69984f0f'),('now','стало · R01 69984f0f + ui-kit R11')]
for f in ['home','obj','proj','phone']:
    ims=[Image.open(f'{S}/refshots/{t}-{f}.png').convert('RGB') for t,_ in labels]
    w,h=ims[0].size
    ims=[im.crop((0,0,w,h)) if im.size!=(w,h) else im for im in ims]
    if f=='phone':
        W=w*3+40; H=h+40; c=Image.new('RGB',(W,H),'white'); d=ImageDraw.Draw(c)
        for i,(im,(t,l)) in enumerate(zip(ims,labels)):
            c.paste(im,(i*(w+20),40)); d.text((i*(w+20)+4,8),l.split(' (')[0].split(' · ')[0],fill='#121a17',font=font)
    else:
        W=w*3+40; H=h+44; c=Image.new('RGB',(W,H),'white'); d=ImageDraw.Draw(c)
        for i,(im,(t,l)) in enumerate(zip(ims,labels)):
            c.paste(im,(i*(w+20),44)); d.text((i*(w+20)+4,10),l,fill='#121a17',font=font)
    if scale!=1: c=c.resize((int(c.width*scale),int(c.height*scale)),Image.LANCZOS)
    c.save(f'{out}/{f}.jpg',quality=82)
    print(f, c.size)
