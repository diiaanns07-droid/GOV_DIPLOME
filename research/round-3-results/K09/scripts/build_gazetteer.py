"""K09-T1: справочник названий (gazetteer) для эксперимента «поручение → ограничения».

Названия берутся ТОЛЬКО из входных файлов (не из примеров набора) и сохраняют уровень
подтверждения источника. Ничего официально не подтверждено.
Входы (см. inputs/MANIFEST.json):
- data/astana_districts.geojson — OSM osm_names (снимок 2026-09-22), в ветке;
- inputs/K03_territory_registry.json — K03 @ a8f1e17 (Шымкент: названия — hypothesis A12-F016);
- inputs/K10_*_districts_overture.geojson — K10 @ e91898d, Overture 2026-09-23.1 (геометрия и имена из OSM).
Тұран: в K10 STATUS — только macrohood в Overture; в A04/A11/A12 — район «по памяти» (hypothesis).
Запуск из корня репозитория: python3 research/round-3-results/K09/scripts/build_gazetteer.py
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
R = ROOT / "research/round-3-results/K09"
OUT = R / "dataset/gazetteer.json"


def load(p):
    return json.loads(Path(p).read_text(encoding="utf-8"))


osm = load(ROOT / "data/astana_districts.geojson")
k03 = load(R / "inputs/K03_territory_registry.json")
ov = {c: load(R / f"inputs/K10_{c}_districts_overture.geojson") for c in ("astana", "shymkent")}
model = load(ROOT / "data/city_data.json")
modeled = {d["id"] for d in model["districts"]}

entities = []
# --- Астана: 6 районов OSM (+ имена Overture для сверки)
ov_ast = {f["properties"]["osm_relation"].split("@")[0][1:]: f["properties"] for f in ov["astana"]["features"]
          if f["properties"].get("osm_relation")}
for f in osm["features"]:
    p = f["properties"]
    names = {k: v for k, v in p["osm_names"].items() if k in ("name", "name:ru", "name:kk")}
    o = ov_ast.get(str(p["osm_id"]), {})
    entities.append({
        "entity_id": f"astana.{p['id']}", "city": "astana", "level": "district", "engine_id": p["id"],
        "names": {"ru": sorted({names.get("name:ru"), o.get("names_common", {}).get("ru")} - {None}),
                  "kk": sorted({names.get("name:kk"), names.get("name"), o.get("names_common", {}).get("kk")} - {None})},
        "status": "observed_osm_overture_not_official",
        "modeled_in_training_model": p["id"] in modeled,
        "sources": [f"data/astana_districts.geojson osm_id {p['osm_id']} (OSM 2026-09-22)",
                    f"K10 Overture 2026-09-23.1 {o.get('osm_relation')}" if o else "K10: нет записи",
                    "K03 territory_registry: geometry verified_locally, official not_verified"]})
# --- Шымкент: 4 района county в Overture (K10)
local = {"Абай ауданы": "abay", "Әл-Фараби ауданы": "al_farabi", "Еңбекші ауданы": "enbekshi", "Қаратау ауданы": "karatau"}
for f in ov["shymkent"]["features"]:
    p = f["properties"]
    if p.get("unit_kind") != "district":
        continue
    nc = p.get("names_common", {})
    entities.append({
        "entity_id": f"shymkent.{local[p['name_primary']]}", "city": "shymkent", "level": "district",
        "engine_id": None,
        "names": {"ru": sorted({nc.get("ru")} - {None}), "kk": sorted({p["name_primary"], nc.get("kk")} - {None})},
        "status": "observed_overture_osm_not_official", "modeled_in_training_model": False,
        "sources": [f"K10 Overture 2026-09-23.1 {p.get('osm_relation')} division {p.get('overture_division_id')}",
                    "K03: русские названия есть как hypothesis A12-F016; стабильные ID не выданы"]})
# --- Тұран / Туранский: статус не подтверждён
k03_turan = [r for r in k03["rows"] if r["city"] == "shymkent" and "Туран" in (r.get("name_ru") or "")]
entities.append({
    "entity_id": "shymkent.turan?", "city": "shymkent", "level": "district_unconfirmed", "engine_id": None,
    "names": {"ru": [r["name_ru"] for r in k03_turan], "kk": ["Тұран"]},
    "status": "unconfirmed: district by memory hypothesis (A04-F014, A11-F016, A12-F016); macrohood (not county) in Overture per K10 STATUS",
    "modeled_in_training_model": False,
    "sources": ["K03 territory_registry (name_source: A12-F016 hypothesis)", "K10 STATUS.md п.3 «Тұран есть только как macrohood»"]})
cities = [{"entity_id": "astana", "level": "city", "names": {"ru": ["Астана"], "kk": ["Астана"]}, "status": "observed (OSM/Overture name)"},
          {"entity_id": "shymkent", "level": "city", "names": {"ru": ["Шымкент"], "kk": ["Шымкент"]}, "status": "observed (Overture name_primary)"}]
doc = {"generated_by": "research/round-3-results/K09/scripts/build_gazetteer.py",
       "note": "Ни одно название не подтверждено официально (БНС/НПА недоступны). Локальные ID Шымкента — только для эксперимента.",
       "cities": cities, "districts": entities}
OUT.write_text(json.dumps(doc, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
for e in entities:
    print(e["entity_id"], e["names"], e["modeled_in_training_model"])
