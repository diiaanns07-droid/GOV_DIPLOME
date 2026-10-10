"""Чтение ml/datasets/LABELING_GUIDE_v2.md для LLM-промптов: правила берутся из одного документа,
чтобы владелец, LLM-разметчик и LLM-генератор работали по одним и тем же определениям."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
GUIDE = ROOT / "ml" / "datasets" / "LABELING_GUIDE_v2.md"
CATEGORIES_JSON = ROOT / "research" / "round-14" / "categories_v2.json"


def categories() -> list[dict]:
    return json.loads(CATEGORIES_JSON.read_text(encoding="utf-8"))["categories"]


def _plain(md: str) -> str:
    md = re.sub(r"\*\*|\*|`", "", md)
    return re.sub(r"[ \t]+", " ", md).strip()


def category_definitions(path: Path = GUIDE) -> dict[str, str]:
    """{id: «что сюда относится … Не сюда: …»} — абзацы под заголовком ### `id` до таблицы примеров."""
    text = path.read_text(encoding="utf-8")
    out = {}
    for m in re.finditer(r"^### `(\w+)` — [^\n]*\n(.*?)(?=^\||^### |^## )", text, re.M | re.S):
        out[m.group(1)] = _plain(" ".join(line for line in m.group(2).splitlines() if line.strip()))
    return out


def main_rules(path: Path = GUIDE) -> str:
    text = path.read_text(encoding="utf-8")
    m = re.search(r"^## 1\. Главные правила\n(.*?)^## ", text, re.M | re.S)
    return _plain(m.group(1)) if m else ""


def dispute_table(path: Path = GUIDE) -> list[tuple[str, str]]:
    text = path.read_text(encoding="utf-8")
    m = re.search(r"^## 3\. [^\n]*\n(.*?)(?=^## |\Z)", text, re.M | re.S)
    rows = []
    for line in (m.group(1) if m else "").splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) >= 2 and cells[1].startswith("`"):
            rows.append((cells[0], cells[1].strip("`")))
    return rows


def guide_sha256(path: Path = GUIDE) -> str:
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()
