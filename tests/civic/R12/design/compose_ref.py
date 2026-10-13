"""«эталон / было / стало»: полные кадры 50 % и вырезы карточки 1:1. python3 compose_ref.py <ref.png> <was.png> <now.png> <out.jpg> [card]
card = "x,y,w,h;x,y,w,h;x,y,w,h" — вырезы карточки в трёх кадрах (по умолчанию — полные кадры)."""
import sys
from PIL import Image, ImageDraw, ImageFont
ref, was, now, out = sys.argv[1:5]
crops = sys.argv[5].split(";") if len(sys.argv) > 5 else None
ims = [Image.open(p).convert("RGB") for p in (ref, was, now)]
if crops:
    ims = [im.crop((int(c.split(",")[0]), int(c.split(",")[1]), int(c.split(",")[0]) + int(c.split(",")[2]), int(c.split(",")[1]) + int(c.split(",")[3]))) for im, c in zip(ims, crops)]
else:
    ims = [im.resize((im.width // 2, im.height // 2), Image.LANCZOS) if im.width > 1000 else im for im in ims]
    ims = [im.resize((im.width // 2, im.height // 2), Image.LANCZOS) if im.width == 750 else im for im in ims]
labels = ["эталон A", "было", "стало"]
try:
    font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 18)
except Exception:
    font = ImageFont.load_default()
gap, top = 16, 36
W = sum(i.width for i in ims) + gap * 4
H = max(i.height for i in ims) + top + gap
canvas = Image.new("RGB", (W, H), (233, 235, 230))
d = ImageDraw.Draw(canvas)
x = gap
for im, lab in zip(ims, labels):
    d.text((x, 10), lab, fill=(18, 26, 23), font=font)
    canvas.paste(im, (x, top))
    x += im.width + gap
canvas.save(out, "JPEG", quality=82)
print(out, canvas.size)
