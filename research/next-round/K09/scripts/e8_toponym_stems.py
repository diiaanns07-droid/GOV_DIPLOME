"""K09-E8: распознаёт ли словарь районов базового парсера A13-E4 (DIST, подстроки) названия
районов Астаны в русской и казахской записи OSM.

Входы (observed, в репозитории): data/astana_districts.geojson -> properties.osm_names
(name, name:ru, name:kk; OSM, ODbL, osm_base_timestamp 2026-09-22). Словарь DIST
извлекается из constraints_eval.py через ast (код A13 не исполняется).
Правило совпадения как в baseline_parse(): `stem in text.lower()`.
Это свойство тестового парсера, не города. Шымкент не проверяется: в репозитории
нет наблюдаемых названий его районов (у A04/A11/A12 они только гипотезы).
Запуск из корня репозитория: python3 research/next-round/K09/scripts/e8_toponym_stems.py
"""
import ast, json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
SRC = ROOT / "research/govtech-results/13_architecture_ai_thesis/extracted_files__21_/constraints_eval.py"
tree = ast.parse(SRC.read_text(encoding="utf-8"))
DIST = next(ast.literal_eval(n.value) for n in ast.walk(tree)
            if isinstance(n, ast.Assign) and any(getattr(t, "id", None) == "DIST" for t in n.targets))
geo = json.loads((ROOT / "data/astana_districts.geojson").read_text(encoding="utf-8"))
rows = []
for f in geo["features"]:
    p = f["properties"]
    for field in ("name:ru", "name", "name:kk"):
        text = p["osm_names"].get(field)
        if not text:
            continue
        hits = sorted({did for stem, did in DIST.items() if stem in text.lower()})
        rows.append({"district_id": p["id"], "field": field, "text": text, "parser_hits": hits,
                     "correct": hits == [p["id"]] if p["id"] in DIST.values() else hits == [],
                     "in_parser_dict": p["id"] in DIST.values()})
cross = [{"stem": s, "inside_other_stem": o} for s in DIST for o in DIST if s != o and s in o]
summary = {}
for field in ("name:ru", "name", "name:kk"):
    sub = [r for r in rows if r["field"] == field and r["in_parser_dict"]]
    summary[field] = {"districts": len(sub), "recognised_correctly": sum(r["correct"] for r in sub)}
print(json.dumps({"dist_dict": DIST, "summary": summary, "stem_inside_other_stem": cross, "rows": rows},
                 ensure_ascii=False, indent=1))
