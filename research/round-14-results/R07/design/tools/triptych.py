# R07 · кадр «эталон / было / стало»: три снимка одного размера в ряд с подписями (Pillow).
#   python3 triptych.py <выход.jpg> <эталон> <было> <стало> ["подпись 1|подпись 2|подпись 3"] [масштаб=0.5]
import sys
from PIL import Image, ImageDraw, ImageFont

out, paths = sys.argv[1], sys.argv[2:5]
labels = (sys.argv[5] if len(sys.argv) > 5 else "эталон A|было|стало").split("|")
scale = float(sys.argv[6]) if len(sys.argv) > 6 else 0.5
imgs = [Image.open(p).convert("RGB") for p in paths]
w, h = int(imgs[0].width * scale), int(imgs[0].height * scale)
imgs = [im.resize((w, int(im.height * w / im.width)), Image.LANCZOS) for im in imgs]
h = max(im.height for im in imgs)
gap, top = 16, 30
try:
    font = ImageFont.truetype("DejaVuSans.ttf", 17)
except OSError:
    font = ImageFont.load_default()
canvas = Image.new("RGB", (3 * w + 2 * gap, h + top), "white")
draw = ImageDraw.Draw(canvas)
for i, (im, label) in enumerate(zip(imgs, labels)):
    x = i * (w + gap)
    canvas.paste(im, (x, top))
    draw.text((x + 4, 5), label, fill=(18, 26, 23), font=font)
canvas.save(out, quality=85)
print(out, canvas.size)
