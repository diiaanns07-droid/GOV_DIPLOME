"""Генерирует web/labeling/categories.js из research/round-14/categories_v2.json.

Зачем отдельный файл: страница разметки открывается двойным щелчком (file://),
а браузер не даёт fetch() читать соседний JSON с диска. Поэтому список категорий
кладётся в .js, но НЕ пишется руками (CONTRACT §3): только этим скриптом.
Тест tests/civic/R02/round14/test_r02_labeling_files.py проверяет, что файл не устарел.

Запуск из корня репозитория:
    python -m ml.labeling.gen_categories_js          # перезаписать
    python -m ml.labeling.gen_categories_js --check  # только проверить (код 1, если устарел)
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "research" / "round-14" / "categories_v2.json"
TARGET = ROOT / "web" / "labeling" / "categories.js"
FIELDS = ("id", "ru", "kk", "examples_ru", "icon")


def render(source: Path = SOURCE) -> str:
    data = json.loads(source.read_text(encoding="utf-8"))
    cats = [{k: c[k] for k in FIELDS} for c in data["categories"]]
    payload = {"version": data["version"], "categories": cats}
    body = json.dumps(payload, ensure_ascii=False, indent=1)
    return (
        "/* СГЕНЕРИРОВАНО из research/round-14/categories_v2.json скриптом\n"
        " * python -m ml.labeling.gen_categories_js — не править руками. */\n"
        f"window.BIRGE_CATEGORIES = {body};\n"
    )


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--check", action="store_true", help="не писать, только сверить")
    args = ap.parse_args(argv)
    text = render()
    if args.check:
        current = TARGET.read_text(encoding="utf-8") if TARGET.exists() else ""
        if current.replace("\r\n", "\n") != text:
            print(f"УСТАРЕЛ: {TARGET.relative_to(ROOT)} — запустите python -m ml.labeling.gen_categories_js")
            return 1
        print("ok: categories.js совпадает с categories_v2.json")
        return 0
    TARGET.write_text(text, encoding="utf-8", newline="\n")
    print(f"записано: {TARGET.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
