"""До/после для research/round-14-results/R12/design/<экран>/: JPEG q=78; телефон (2x) уменьшается до 1x, чтобы файлы были лёгкими.
python3 pack.py <src_dir> <dst_dir> [prefix,prefix…]"""
import sys
from pathlib import Path
from PIL import Image
src, dst = Path(sys.argv[1]), Path(sys.argv[2])
only = sys.argv[3].split(",") if len(sys.argv) > 3 else None
dst.mkdir(parents=True, exist_ok=True)
n = 0
for f in sorted(src.glob("*.png")):
    if only and not any(f.name.startswith(p + "-") for p in only):
        continue
    im = Image.open(f).convert("RGB")
    if im.width == 750:  # 375 × 2
        im = im.resize((375, im.height // 2), Image.LANCZOS)
    im.save(dst / (f.stem + ".jpg"), quality=78, optimize=True)
    n += 1
print(n, "files →", dst)
