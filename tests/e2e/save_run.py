#!/usr/bin/env python3
"""R10 · раунд 15 · сохранить прогон приёмки в research/round-15-results/R10/<папка> — только то, что нужно для отчёта.

    python3 tests/e2e/save_run.py <папка прогона acceptance_r15.sh> research/round-15-results/R10/<сборка>

Берёт: отчёты *.md / *.json (кроме тяжелее 1 МБ), chain.log, хвосты *.log (последние 60 строк) и кадры, на которые
ссылаются строки FAIL (поле shot в RESULT.json) — кадры нужны для BUGS («кадр»). Ролики, png карты, webm не копирует.
Ничего не удаляет в назначении, кроме перезаписи тех же файлов.
"""
from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

MAX_BYTES = 1_000_000
MAX_FRAMES = 24


def main() -> int:
    if len(sys.argv) != 3:
        print(__doc__)
        return 2
    src, dst = Path(sys.argv[1]), Path(sys.argv[2])
    if not src.is_dir():
        print(f"нет папки прогона: {src}")
        return 2
    dst.mkdir(parents=True, exist_ok=True)
    copied = []
    for f in sorted(src.rglob("*")):
        if not f.is_file():
            continue
        rel = f.relative_to(src)
        if f.suffix in (".md", ".json") and f.stat().st_size <= MAX_BYTES or f.name == "chain.log":
            (dst / rel).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(f, dst / rel)
            copied.append(str(rel))
        elif f.suffix == ".log" and f.parent == src:
            lines = f.read_text(encoding="utf-8", errors="replace").splitlines()[-60:]
            (dst / (f.name + ".tail")).write_text("\n".join(lines) + "\n", encoding="utf-8")
            copied.append(f.name + ".tail")
    frames = []
    for res in src.rglob("RESULT.json"):
        try:
            data = json.loads(res.read_text(encoding="utf-8"))
        except ValueError:
            continue
        for row in data.get("results", []):
            name = row.get("shot") or row.get("file")
            if row.get("status") == "FAIL" and name:
                p = res.parent / name
                if p.is_file() and p.suffix in (".jpg", ".png") and len(frames) < MAX_FRAMES:
                    rel = p.relative_to(src)
                    (dst / rel).parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(p, dst / rel)
                    frames.append(str(rel))
    print(f"скопировано {len(copied)} отчётов, {len(frames)} кадров FAIL → {dst}")
    for x in frames:
        print("  кадр", x)
    return 0


if __name__ == "__main__":
    sys.exit(main())
