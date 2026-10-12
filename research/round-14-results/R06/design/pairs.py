"""Пары «до | после» для research/round-14-results/R06/design/ (JPEG, подписи сверху).

python3 -I pairs.py <папка до> <папка после> <папка вывода>
"""
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

BEFORE, AFTER, OUT = (Path(a) for a in sys.argv[1:4])
OUT.mkdir(parents=True, exist_ok=True)

PICK = [
    ("r-list", ["1366-ru", "375-kk"]), ("r-list-tall", ["1366-kk", "375-ru"]), ("r-supported", ["1366-ru", "375-ru"]),
    ("r-tab-project", ["1366-ru", "375-kk"]), ("r-tab-rejected", ["1366-kk"]), ("r-loading", ["1366-ru", "375-kk"]),
    ("r-empty", ["1366-ru", "375-ru"]), ("w-step1", ["1366-ru", "375-kk"]), ("w-step1-done", ["1366-ru"]),
    ("w-step2-error", ["375-ru", "1366-kk"]), ("w-step3", ["1366-kk", "375-ru"]), ("w-sent", ["1366-ru", "375-kk"]),
    ("a-queue", ["1366-ru", "375-ru"]), ("a-review-open", ["1366-kk"]), ("a-check", ["1366-ru", "375-kk"]),
    ("a-check-allyes", ["1366-ru", "375-ru"]), ("a-decided", ["375-kk"]), ("a-projects-tall", ["1366-ru"]),
    ("k-works-tall", ["1366-ru", "375-kk"]), ("k-form-errors-tall", ["1366-ru"]), ("k-form-tall", ["375-kk"]), ("p-card-idea", ["375-ru", "1366-ru"]),
    ("a-nologin", ["1366-ru"]), ("r-mine-review", ["375-kk"]), ("w-pick-chosen", ["1366-ru"]), ("r-more", ["1366-kk"]),
]


def font(size):
    for f in ("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", "/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf"):
        if Path(f).exists():
            return ImageFont.truetype(f, size)
    return ImageFont.load_default()


def pair(name, combo):
    b, a = BEFORE / f"{name}-{combo}.png", AFTER / f"{name}-{combo}.png"
    if not b.exists() or not a.exists():
        return None
    ib, ia = Image.open(b).convert("RGB"), Image.open(a).convert("RGB")
    scale = 0.6 if ib.width > 900 else 1.0
    ib = ib.resize((int(ib.width * scale), int(ib.height * scale)))
    ia = ia.resize((int(ia.width * scale), int(ia.height * scale)))
    gap, head = 16, 40
    w, h = ib.width + ia.width + gap, max(ib.height, ia.height) + head
    out = Image.new("RGB", (w, h), (244, 245, 246))
    d = ImageDraw.Draw(out)
    f = font(20)
    d.text((8, 9), "до · " + combo, fill=(91, 106, 100), font=f)
    d.text((ib.width + gap + 8, 9), "после · " + combo, fill=(21, 44, 38), font=f)
    out.paste(ib, (0, head))
    out.paste(ia, (ib.width + gap, head))
    path = OUT / f"{name}-{combo}.jpg"
    out.save(path, "JPEG", quality=80, optimize=True)
    return path


made = [p for name, combos in PICK for c in combos if (p := pair(name, c))]
print(len(made), "пар;", sum(p.stat().st_size for p in made) // 1024, "КБ")
