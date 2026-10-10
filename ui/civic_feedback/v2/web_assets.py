"""Генерация web/civic/feedback/categories_v2.js из research/round-14/categories_v2.json.

Интерфейсу категории нужны сразу и без сети (офлайн-финал), поэтому они встраиваются в JS,
но НЕ пишутся руками: файл всегда пересобирается этой командой, а тест проверяет, что он актуален.

  python -m ui.civic_feedback.v2.web_assets          # пересобрать
  python -m ui.civic_feedback.v2.web_assets --check  # код 1, если файл устарел
"""

import json
import sys
from pathlib import Path

from . import categories

TARGET = categories.ROOT / "web" / "civic" / "feedback" / "categories_v2.js"


def render() -> str:
    payload = categories.public_payload()
    body = json.dumps(payload, ensure_ascii=False, indent=1, sort_keys=False)
    return ("/* СГЕНЕРИРОВАНО: python -m ui.civic_feedback.v2.web_assets — не править руками.\n"
            " * Источник: research/round-14/categories_v2.json (+ сроки ответа R09). */\n"
            "window.BirgeCategoriesV2 = " + body + ";\n")


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    content = render()
    if "--check" in argv:
        current = TARGET.read_text(encoding="utf-8") if TARGET.exists() else ""
        if current != content:
            print(f"{TARGET} устарел: запустите python -m ui.civic_feedback.v2.web_assets", file=sys.stderr)
            return 1
        return 0
    Path(TARGET).write_text(content, encoding="utf-8")
    print(f"записано {TARGET}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
