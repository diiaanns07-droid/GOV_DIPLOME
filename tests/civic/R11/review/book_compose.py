#!/usr/bin/env python3
"""R11 · «книга экранов»: склейка кадров ru | kk в research/round-14-results/R11/design/book/ (JPEG).

    python3 tests/civic/R11/review/book_compose.py <папка-кадров> [<папка-книги>]

<папка-кадров> содержит b/ (build_shots.cjs), w/ (wave2_shots.cjs), s/ (book_staff.cjs). Ноутбук 1366 — 70 %, телефон 375 —
как есть; пара — слева ru, справа kk. Нужен Pillow (python3 -m pip install pillow), только для склейки.
"""
import os
import sys

from PIL import Image

RAW = sys.argv[1]
OUT = sys.argv[2] if len(sys.argv) > 2 else "research/round-14-results/R11/design/book"
B, W, S = (os.path.join(RAW, x) for x in ("b", "w", "s"))
BOOK = [
    ("01-akimat-map", B + "/b-r-1-akimat-map-{w}-{l}.png"),
    ("02-akimat-card", B + "/b-r-2-akimat-card-{w}-{l}.png"),
    ("03-day", B + "/b-r-3-day-{w}-{l}.png"),
    ("04-hot-to-map", B + "/b-r-4-hot-to-map-{w}-{l}.png"),
    ("05-akimat-avatar-menu", W + "/w2-akimat-{w}-{l}-0-menu.png"),
    ("06-akimat-layers", W + "/w2-akimat-{w}-{l}-0-layers.png"),
    ("07-akimat-more", W + "/w2-akimat-{w}-{l}-more.png"),
    ("08-staff-login", S + "/staff-login-{w}-{l}.png"),
    ("09-inbox-staff", S + "/inbox-staff-{w}-{l}.png"),
    ("10-inbox-item-staff", S + "/inbox-item-staff-{w}-{l}.png"),
    ("11-projects-staff", S + "/projects-staff-{w}-{l}.png"),
    ("12-questions-staff", S + "/questions-staff-{w}-{l}.png"),
    ("13-works", W + "/w2-akimat-{w}-{l}-more-works.png"),
    ("14-services", W + "/w2-akimat-{w}-{l}-more-services.png"),
    ("15-resident-map", B + "/b-r-5-resident-{w}-{l}.png"),
    ("16-wizard-place", B + "/b-r-6-wizard-place-{w}-{l}.png"),
    ("17-wizard-text", B + "/b-r-7-wizard-text-{w}-{l}.png"),
    ("17b-wizard-review", B + "/b-r-7b-wizard-review-{w}-{l}.png"),
    ("18-wizard-done", B + "/b-r-8-wizard-done-{w}-{l}.png"),
    ("19-mine", B + "/b-r-9-mine-{w}-{l}.png"),
    ("20-fixed-verified", B + "/b-r-10-fixed-{w}-{l}.png"),
    ("21-nearby", W + "/w2-resident-{w}-{l}-nearby.png"),
    ("22-ideas", W + "/w2-resident-{w}-{l}-ideas.png"),
    ("23-questions", W + "/w2-resident-{w}-{l}-more-questions.png"),
    ("24-resident-avatar-menu", W + "/w2-resident-{w}-{l}-0-menu.png"),
    ("25-build3d-catalog", B + "/b-r-11-catalog-{w}-{l}.png"),
    ("26-build3d-placed", B + "/b-r-12-placed-{w}-{l}.png"),
    ("27-build3d-vote", B + "/b-r-13-vote-{w}-{l}.png"),
]

os.makedirs(OUT, exist_ok=True)
made, total = [], 0
for name, pattern in BOOK:
    for width, scale in (("1366", 0.7), ("375", 1.0)):
        ims = []
        for lang in ("ru", "kk"):
            path = pattern.format(w=width, l=lang)
            if os.path.exists(path):
                im = Image.open(path).convert("RGB")
                if scale != 1:
                    im = im.resize((round(im.width * scale), round(im.height * scale)), Image.LANCZOS)
                ims.append(im)
        if len(ims) < 2:
            continue
        pair = Image.new("RGB", (ims[0].width + ims[1].width + 12, max(i.height for i in ims)), (255, 255, 255))
        pair.paste(ims[0], (0, 0))
        pair.paste(ims[1], (ims[0].width + 12, 0))
        out = os.path.join(OUT, f"{name}-{width}.jpg")
        pair.save(out, quality=78, optimize=True, progressive=True)
        made.append(os.path.basename(out))
        total += os.path.getsize(out)
print(f"{len(made)} файлов, {total / 1e6:.2f} МБ → {OUT}")
