"""R01 round 15: glue the «было | стало» shots of r15_pairs.cjs side by side for the build log and the diploma.

    python3 tests/civic/R01/browser/r15_pairs_merge.py <pairs_dir> <out_dir> [--quality 80]

Reads <pairs_dir>/pairs.json (labels, views) and before_<view>.jpg / after_<view>.jpg, writes <out_dir>/pair_<view>.jpg:
a white strip on top with the two labels (each over its own frame), the frames below with an 8 px gap. On narrow frames
(375) the label font shrinks until the text fits its frame, so labels never overlap. Writes nothing else.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

FONTS = ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf")
GAP, PAD, STRIP = 8, 10, 40
INK, PAPER, RULE = (21, 44, 38), (255, 255, 255), (214, 220, 217)


def font(size: int):
    for path in FONTS:
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            continue
    return ImageFont.load_default()


def fitted(draw: ImageDraw.ImageDraw, text: str, width: int):
    """Largest font 11..20 px whose text fits the frame width (minus padding); the smallest one otherwise."""
    for size in range(20, 10, -1):
        f = font(size)
        if draw.textlength(text, font=f) <= width - 2 * PAD:
            return f
    return font(11)


def merge(before: Path, after: Path, labels: tuple[str, str], out: Path, quality: int) -> None:
    a, b = Image.open(before).convert("RGB"), Image.open(after).convert("RGB")
    if a.height != b.height:  # same view of two stands — normally the same size; otherwise scale «было» to «стало»
        a = a.resize((round(a.width * b.height / a.height), b.height))
    canvas = Image.new("RGB", (a.width + GAP + b.width, STRIP + a.height), PAPER)
    canvas.paste(a, (0, STRIP))
    canvas.paste(b, (a.width + GAP, STRIP))
    draw = ImageDraw.Draw(canvas)
    draw.rectangle([a.width, 0, a.width + GAP - 1, canvas.height], fill=RULE)
    for x, w, text in ((0, a.width, labels[0]), (a.width + GAP, b.width, labels[1])):
        f = fitted(draw, text, w)
        box = draw.textbbox((0, 0), text, font=f)
        draw.text((x + PAD, (STRIP - (box[3] - box[1])) // 2 - box[1]), text, font=f, fill=INK)
    canvas.save(out, "JPEG", quality=quality, optimize=True)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("pairs_dir", type=Path)
    ap.add_argument("out_dir", type=Path)
    ap.add_argument("--quality", type=int, default=80)
    args = ap.parse_args()
    meta = json.loads((args.pairs_dir / "pairs.json").read_text(encoding="utf-8"))
    labels = tuple(meta.get("labels") or ("было", "стало"))
    args.out_dir.mkdir(parents=True, exist_ok=True)
    done = []
    for view in meta.get("views") or []:
        before, after = args.pairs_dir / f"before_{view}.jpg", args.pairs_dir / f"after_{view}.jpg"
        if before.exists() and after.exists():
            merge(before, after, labels, args.out_dir / f"pair_{view}.jpg", args.quality)
            done.append(view)
    print(json.dumps({"pairs": len(done), "out": str(args.out_dir)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
