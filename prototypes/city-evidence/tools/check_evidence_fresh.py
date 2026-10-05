"""Check that web/evidence.js was built from the current K03 code/layers and the current places of web/data.js.

Binding format k03-binding-v1 (as proposed by K03 r5 P1, research/round-5-results/K03/proposal/p1, @ 5715a7f):
  boundary_binding = {schema, rule, code{path: sha256}, layers{path: sha256}, places{city: sha256}, digest}
  - paths are relative to the K03 copy the build uses (K03_ROOT below); code + layers = everything K03 Layers()/assign() read;
  - places[city] = sha256 of the sorted JSON list [[id, lon, lat], ...] of web/data.js places (lon/lat rounded to 7 digits);
  - digest = sha256 of the other fields (sort_keys, no spaces);
  - every place_district record keeps the lonlat of the data.js place it was assigned from.
Difference to P1: the K03 root is inputs/k03v21_root (patched copy), not inputs/k03_root (immutable original).
Stdlib only (no shapely). Exit code 1 if the binding is stale or missing.

    python3 tools/check_evidence_fresh.py
"""
import hashlib
import json
import sys
from pathlib import Path

APP = Path(__file__).resolve().parents[1]
K03_ROOT = Path("inputs") / "k03v21_root"
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
    k3 = Path(app) / K03_ROOT
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
        if set(dmap) != set(cd["place_district"]):
            out.append(f"{city}: набор мест data.js и place_district различается")
        for pid, r in cd["place_district"].items():
            p = dmap.get(pid)
            if p is not None and r.get("lonlat") != [p["lon"], p["lat"]]:
                out.append(f"{city}/{pid}: место сдвинулось после привязки к району")
                break
    return out


def main():
    try:
        sys.stdout.reconfigure(errors="replace")
    except AttributeError:
        pass
    pr = problems()
    if pr:
        print("evidence.js устарел:\n  " + "\n  ".join(pr[:20]))
        return 1
    print("evidence.js актуален: код и слои K03, места data.js совпадают с boundary_binding")
    return 0


if __name__ == "__main__":
    sys.exit(main())
