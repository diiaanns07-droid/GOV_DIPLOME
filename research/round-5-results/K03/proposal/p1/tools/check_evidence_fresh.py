"""Проверить, что web/evidence.js построен из текущих кода и слоёв K03 и текущих мест web/data.js.

Формат привязки k03-binding-v1 (пишет tools/build_evidence.py, здесь — единственное описание):
  boundary_binding = {schema, rule, code{путь: sha256}, layers{путь: sha256}, places{город: sha256}, digest}
  - пути относительно inputs/k03_root/; code и layers — всё, что читают K03 Layers()/assign();
  - places[город] = sha256 JSON-списка [[id, lon, lat], ...] мест web/data.js (отсортирован, lon/lat округлены до 7 знаков);
  - digest = sha256 JSON остальных полей (sort_keys, без пробелов);
  - каждая запись place_district хранит lonlat места из data.js, по которому сделана привязка.
Только stdlib, без shapely. Код выхода 1, если привязка устарела или отсутствует.
Запуск: python3 tools/check_evidence_fresh.py
"""
import hashlib
import json
import sys
from pathlib import Path

APP = Path(__file__).resolve().parents[1]
SCHEMA = "k03-binding-v1"
K03_CODE = ["research/round-3-results/K03/boundary_validator.py", "research/round-3-results/K03/geo_common.py"]
K03_LAYERS = ["data/astana_districts.geojson", "data/geo_sources/astana_districts_overpass.json",
              "data/geo_sources/sara_osm.json",
              "research/round-3-results/K03/inputs/K10/astana_districts_overture.geojson",
              "research/round-3-results/K03/inputs/K10/shymkent_districts_overture.geojson"]


def sha256_file(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def parse_js(p):
    t = Path(p).read_text(encoding="utf-8")
    return json.loads(t[t.index("{"):t.rstrip().rindex(";")])


def places_digest(data, city):
    rows = sorted([p["id"], round(p["lon"], 7), round(p["lat"], 7)] for p in data["cities"][city]["places"])
    return hashlib.sha256(json.dumps(rows, separators=(",", ":")).encode()).hexdigest()


def digest(b):
    core = {k: b[k] for k in ("schema", "rule", "code", "layers", "places")}
    return hashlib.sha256(json.dumps(core, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def binding(app, rule, data):
    k3 = Path(app) / "inputs" / "k03_root"
    b = {"schema": SCHEMA, "rule": rule,
         "code": {p: sha256_file(k3 / p) for p in K03_CODE},
         "layers": {p: sha256_file(k3 / p) for p in K03_LAYERS},
         "places": {c: places_digest(data, c) for c in data["cities"]}}
    b["digest"] = digest(b)
    return b


def problems(app=APP):
    app = Path(app)
    ev = parse_js(app / "web" / "evidence.js")
    data = parse_js(app / "web" / "data.js")
    b = ev.get("boundary_binding")
    if not b:
        return ["в evidence.js нет boundary_binding — пересоберите tools/build_evidence.py"]
    out = []
    if b.get("schema") != SCHEMA:
        out.append(f"неизвестная схема привязки {b.get('schema')}")
    cur = binding(app, b.get("rule"), data)
    for part, what in (("code", "код K03"), ("layers", "слой K03"), ("places", "места data.js")):
        for k, v in cur[part].items():
            if b.get(part, {}).get(k) != v:
                out.append(f"{what} изменился после сборки evidence.js: {k}")
    if b.get("digest") != digest(b):
        out.append("digest привязки не соответствует её содержимому")
    if ev.get("assign_rule") != b.get("rule"):
        out.append(f"метка правила {ev.get('assign_rule')} ≠ binding.rule {b.get('rule')}")
    for city, cd in ev["cities"].items():
        dmap = {p["id"]: p for p in data["cities"][city]["places"]}
        for pid, r in cd["place_district"].items():
            p = dmap.get(pid)
            if p is None:
                out.append(f"{city}/{pid}: места нет в data.js")
            elif r.get("lonlat") != [p["lon"], p["lat"]]:
                out.append(f"{city}/{pid}: координаты в data.js не те, по которым сделана привязка")
        missing = sorted(set(dmap) - set(cd["place_district"]))
        if missing:
            out.append(f"{city}: {len(missing)} мест data.js без привязки")
    return out


def main():
    pr = problems()
    for p in pr:
        print("УСТАРЕЛО:", p)
    print("evidence.js актуален" if not pr else f"evidence.js устарел: {len(pr)} расхождений — запустите tools/build_evidence.py")
    return 1 if pr else 0


if __name__ == "__main__":
    sys.exit(main())
