"""Перевод корпуса v1 (6 меток, R08 раунд 12) в 12 категорий v2 (R02, раунд 14).

Две метки на каждую строку:
  label_table — строго по таблице v1_to_v2 из research/round-14/categories_v2.json (как велит CONTRACT §3);
  label       — уточнённая по ml/datasets/LABELING_GUIDE_v2.md: таблица переводит весь v1-«other» в «other»,
                но в v1 туда попали мусор, ЖКХ, шум, собаки, парковка — в v2 это отдельные категории;
                снег/лёд из roads/sidewalks/transport_stops в v2 — snow_ice. Правило записано в поле rule.
Для обучения v2 используйте label; label_table нужен, чтобы показать, сколько шума даёт механический перевод.

Источник — файлы v1 только для чтения (ml/civic_classifier/ не меняем):
    git show origin/claude/wizardly-ptolemy-qy8ltw:ml/civic_classifier/data/corpus_synthetic_v2.jsonl > /tmp/v1.jsonl
    git show origin/claude/wizardly-ptolemy-qy8ltw:ml/civic_classifier/data/split_v2.json > /tmp/v1_split.json
    python -m ml.datasets.v1_in_v2.convert /tmp/v1.jsonl --split /tmp/v1_split.json
(после сборки R01 эти файлы лежат в ml/civic_classifier/data/ — тогда пути можно не указывать).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
CATEGORIES_JSON = ROOT / "research" / "round-14" / "categories_v2.json"
DEFAULT_SRC = ROOT / "ml" / "civic_classifier" / "data" / "corpus_synthetic_v2.jsonl"
DEFAULT_SPLIT = ROOT / "ml" / "civic_classifier" / "data" / "split_v2.json"
OUT = HERE / "corpus_v1_in_v2.jsonl"
MANIFEST = HERE / "manifest_v1_in_v2.json"

# Уточнения: (имя правила, условие на метку v1, регулярка по тексту, метка v2). Первое совпадение выигрывает.
SNOW = r"снег|снега|наледи|наледь|гололёд|гололед|лёд|\bлед|сугроб|\bқар\b|қары|көктайғақ|мұз"
RULES = (
    ("snow_anywhere", {"roads", "sidewalks", "transport_stops", "landscaping", "other"}, SNOW, "snow_ice"),
    ("underpass_lighting", {"sidewalks"}, r"освещени|жарық", "lighting"),
    ("waste_from_other", {"other"}, r"мусор|контейнер|қоқыс", "waste"),
    ("utilities_from_other", {"other"}, r"отоплени|горяч\w* вод|холодн\w* вод|\bлифт|подвал|крыш\w* дома|подъезд|"
                                        r"квитанц|жылу|ыстық су|жертөле|шатыры|түбіртек", "utilities"),
    ("parking_from_other", {"other"}, r"парковк|тұрақ", "parking"),
    ("noise_from_other", {"other"}, r"шум|ночью|бездомн|бродяч|собак|иесіз ит|құрылыс шуы|шулайды", "noise_safety"),
)


def load_table() -> dict:
    return json.loads(CATEGORIES_JSON.read_text(encoding="utf-8"))["v1_to_v2"]


# Вопросы, благодарности и нецелевые сообщения v1 остаются «other», даже если в них есть слово «парковка».
KEEP_OTHER_FAMILIES = {"question", "thanks", "irrelevant"}
# Маркеры обезличивания v1 → формат v3 (ml/labeling/anonymize.py), чтобы корпуса можно было смешивать.
MARKERS = {"<phone>": "[телефон]", "<email>": "[email]", "<id>": "[номер]", "<url>": "[ссылка]"}


def refine(label_v1: str, text: str, table: dict, family: str = "") -> tuple[str, str]:
    low = text.lower()
    if family in KEEP_OTHER_FAMILIES:
        return table[label_v1], "table"
    for name, from_labels, rx, target in RULES:
        if label_v1 in from_labels and re.search(rx, low):
            return target, name
    return table[label_v1], "table"


def new_markers(text: str) -> str:
    for old, new in MARKERS.items():
        text = text.replace(old, new)
    return re.sub(r"\s+([.,!?])", r"\1", text)


def convert(src: Path, split_path: Path | None) -> tuple[list[dict], dict]:
    table = load_table()
    split = {}
    if split_path and split_path.exists():
        split = json.loads(split_path.read_text(encoding="utf-8")).get("split", {})
    rows = [json.loads(line) for line in src.read_text(encoding="utf-8").splitlines() if line.strip()]
    out, rules, moved = [], {}, {}
    for r in rows:
        lab, rule = refine(r["label"], r["text"], table, r.get("family", ""))
        rules[rule] = rules.get(rule, 0) + 1
        if lab != table[r["label"]]:
            key = f"{r['label']}→{lab}"
            moved[key] = moved.get(key, 0) + 1
        out.append({"id": "v1-" + r["id"], "text": new_markers(r["text"]), "label": lab, "label_table": table[r["label"]],
                    "label_v1": r["label"], "rule": rule, "lang": r.get("language", ""),
                    "template_id": "v1-" + r.get("template_id", ""), "family": r.get("family", ""),
                    "split": split.get(r["id"], ""), "ambiguous": r.get("ambiguous", False),
                    "evidence": "synthetic", "corpus": "synthetic_v2_r08_relabeled_v2"})
    by_label: dict[str, int] = {}
    for r in out:
        by_label[r["label"]] = by_label.get(r["label"], 0) + 1
    manifest = {
        "source": src.name, "source_sha256": hashlib.sha256(src.read_bytes().replace(b"\r\n", b"\n")).hexdigest(),
        "source_origin": "origin/claude/wizardly-ptolemy-qy8ltw @ 14c3384, ml/civic_classifier/data/",
        "rows": len(out), "rules": dict(sorted(rules.items())), "moved_vs_table": dict(sorted(moved.items())),
        "label_disagrees_with_table": sum(moved.values()), "by_label": dict(sorted(by_label.items())),
        "note": "label — уточнённая метка v2 (для обучения); label_table — механический перевод v1_to_v2; "
                "маркеры <phone>/<email>/<id>/<url> заменены на [телефон]/[email]/[номер]/[ссылка]",
    }
    return out, manifest


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="v1 (6 меток) → v2 (12 категорий)")
    ap.add_argument("src", nargs="?", type=Path, default=DEFAULT_SRC)
    ap.add_argument("--split", type=Path, default=DEFAULT_SPLIT)
    ap.add_argument("--out", type=Path, default=OUT)
    args = ap.parse_args(argv)
    if not args.src.exists():
        print(f"Нет файла {args.src}. См. docstring: git show …:ml/civic_classifier/data/corpus_synthetic_v2.jsonl",
              file=sys.stderr)
        return 1
    rows, manifest = convert(args.src, args.split)
    with open(args.out, "w", encoding="utf-8", newline="\n") as fh:
        for r in rows:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    manifest["output"] = args.out.name
    manifest["output_sha256"] = hashlib.sha256(args.out.read_bytes()).hexdigest()
    (args.out.parent / MANIFEST.name).write_text(json.dumps(manifest, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"{manifest['rows']} строк; отличается от таблицы: {manifest['label_disagrees_with_table']}")
    print("перемещено:", manifest["moved_vs_table"])
    print("категории:", manifest["by_label"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
