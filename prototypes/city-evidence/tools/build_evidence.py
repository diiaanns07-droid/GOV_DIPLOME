"""Build web/evidence.js (format city-evidence/2) — contract k05-obs-v1.2+k12r4+k05r5, K03 assign (v2.1 copy), QA labels.

Inputs (all committed, see source_manifest.json and inputs/r4/MANIFEST.json):
  * K10 r3 package (inputs/k10)              — places, segments, bbox, sha256-checked by build_data.load_layer
  * K05 r4 square observations (inputs/r4/K05/examples/<city>/square_place_record_counts.json)
      — read with loads_strict; every value is re-counted here from the K10 file; mismatch aborts
  * K03 v2.1 (inputs/k03v21_root, patched copy, checked against MANIFEST_K03.json) — district status per record
      (needs shapely + pyproj); the rule label comes from assign() itself; boundary_binding (k03-binding-v1) ties
      place_district to the K03 code/layers and to the data.js places (check: tools/check_evidence_fresh.py)
  * contract (tools/contract.py)             — validate_all over every observation; any error aborts

Semantics (same in contract, catalog and UI):
  * value 0 + reported_zero + coverage.complete=true  -> "0 records in the complete query result for this square"
  * the number of objects in the CITY is a separate observation with value null (missing, reason given)
  * capacity / official registry / population are null with missing_reason, never 0

Usage (from prototypes/city-evidence/):  <python with shapely,pyproj> tools/build_evidence.py
"""
import copy
import hashlib
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
APP = HERE.parent
K03_ROOT = APP / "inputs" / "k03v21_root"
K03_DIR = K03_ROOT / "research" / "round-3-results" / "K03"
K05_EX = APP / "inputs" / "r4" / "K05" / "examples"
OUT = APP / "web" / "evidence.js"
AS_OF = "2026-10-05"
FORMAT = "city-evidence/2"

sys.path.insert(0, str(HERE))
import build_data  # noqa: E402
from build_data import GROUPS, InputError, load_layer, load_manifest, r6  # noqa: E402
from check_evidence_fresh import binding as k03_binding  # noqa: E402
import contract as K  # noqa: E402

GROUP_KK = {  # черновик казахских подписей, требует проверки носителем
    "school": "Мектеп", "preschool": "Балабақша", "college_university": "Колледж / ЖОО",
    "hospital": "Аурухана", "outpatient_clinic": "Емхана", "pharmacy": "Дәріхана",
    "government_office": "Мемлекеттік мекеме",
}
# Reproducible category-doubt rule (QA only; records are never removed or re-categorised).
CATEGORY_DOUBT = [
    ("ad_or_business_page", re.compile(r"реклам|reklama|бизнес\s*страниц|business\s*page", re.I),
     "название похоже на рекламу или страницу бизнеса, а не на учреждение категории"),
    ("bare_place_name", re.compile(r"^(казахстан|kazakhstan|шымкент|shymkent|астана|astana)$", re.I),
     "название совпадает с названием страны или города, а не учреждения"),
]


def sha256(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def load_k03():
    """K03 copy must equal MANIFEST_K03.json (written by tools/setup_k03.py) before its code is imported."""
    mp = K03_ROOT / "MANIFEST_K03.json"
    if not mp.exists():
        raise InputError(f"INTEGRITY: нет {mp.relative_to(APP)} — запустите tools/setup_k03.py")
    want = K.loads_strict(mp.read_text(encoding="utf-8"))["files"]
    have = {str(p.relative_to(K03_ROOT)): sha256(p) for p in sorted(K03_ROOT.rglob("*"))
            if p.is_file() and "__pycache__" not in p.parts and p.name != "MANIFEST_K03.json"}
    if have != want:
        diff = sorted(set(have.items()) ^ set(want.items()))
        raise InputError(f"INTEGRITY: копия K03 не совпадает с MANIFEST_K03.json: {[d[0] for d in diff][:5]}")
    sys.path.insert(0, str(K03_DIR))
    import boundary_validator as BV  # noqa: E402  (K03 v2.1 patched copy, read-only, no network)
    return BV, BV.Layers()


def district_names():
    reg = K.loads_strict((K03_DIR / "boundary_registry.json").read_text(encoding="utf-8"))
    return {u["unit_id"]: {"ru": (u["names"].get("ru") or {}).get("value"), "kk": (u["names"].get("kk") or {}).get("value")}
            for u in reg["units"]}


def k05_square_obs(city, places_path, features):
    """K05 r4 observations for the square; values re-counted from the pinned K10 file."""
    obs = K.loads_strict((K05_EX / city / "square_place_record_counts.json").read_text(encoding="utf-8"))
    want_sha = sha256(places_path)
    for o in obs:
        if o["source"]["sha256"] != want_sha:
            raise InputError(f"INTEGRITY: {o['obs_id']}: source.sha256 K05 != файл K10 пакета")
        g = o["indicator_id"].split(".")[1]
        t = o["method"]["parameters"]["confidence_min"]
        n = sum(1 for f in features if f["properties"]["k10_group"] == g
                and f["properties"]["confidence"] is not None and f["properties"]["confidence"] >= t)
        if o["value"] != n:
            raise InputError(f"SEMANTIC: {o['obs_id']}: значение K05 {o['value']} != пересчёт {n}")
    return obs


def derived_obs(template, indicator, value, unit, *, scope, derivation, method_id, steps, source):
    o = copy.deepcopy(template)
    o.update({"indicator_id": indicator, "value": value, "unit": unit,
              "value_status": "reported_zero" if value == 0 else "reported", "missing_reason": None,
              "obs_id": f"{o['geo_unit_id']}.{indicator}@{o['release']}", "derivation": derivation,
              "method": {"id": method_id, "steps": steps}, "note": None, "source": source})
    o["coverage"] = {"complete": True, "scope": scope, "selection": "все записи пакета K10 для этого квадрата",
                     "area_fraction": 1.0, "cap_per_group": None}
    return o


def city_missing_obs(template, city, indicator, unit, reason, note):
    o = copy.deepcopy(template)
    o.update({"geo_unit_id": f"kz.{city}", "indicator_id": indicator, "value": None, "unit": unit,
              "value_status": "missing", "missing_reason": reason, "kind": "observed", "derivation": None,
              "obs_id": f"kz.{city}.{indicator}@{o['release']}", "note": note, "boundary_version": None,
              "method": {"id": "not_available", "steps": ["в сохранённом пакете источника нет"]},
              "spatial_unit": {"type": "city_polygon", "crs": "EPSG:4326", "bbox": None, "edges_inclusive": None,
                               "area_km2": None, "geometry_source": None, "geometry_sha256": None,
                               "overlaps_districts": None}})
    o["coverage"] = {"complete": False, "scope": "город целиком", "selection": "нет данных", "area_fraction": None,
                     "cap_per_group": None}
    o["source"] = {"source_id": "none", "url": "https://data.egov.kz/", "path": None, "sha256": None,
                   "retrieved_at": None, "license": None, "locator": "официальный источник не получен",
                   "evidence": "K10/K07 access_log: 403 по политике сети"}
    return o


def qa_labels(city, features):
    """COLOCATED groups and POSSIBLE_DUPLICATE pairs from the K05 contract rule + category-doubt rule."""
    rows = [{"overture_id": f["id"], "lon": f["geometry"]["coordinates"][0], "lat": f["geometry"]["coordinates"][1],
             "name_primary": f["properties"].get("name_primary"), "k10_group": f["properties"]["k10_group"],
             "address_freeform": [a.get("freeform") for a in (f["properties"].get("addresses") or [])][:1]}
            for f in features]
    qa = K.C3.check_objects(rows)
    by_xy = defaultdict(list)  # same key as check_objects (5 decimals)
    for r in rows:
        by_xy[(round(r["lon"], 5), round(r["lat"], 5))].append(r["overture_id"])
    colocated = [{"lon": xy[0], "lat": xy[1], "ids": ids} for xy, ids in by_xy.items() if len(ids) >= 3]
    n_reported = sum(1 for w in qa["warnings"] if w["code"] == "COLOCATED")
    if n_reported != len(colocated):
        raise InputError(f"SEMANTIC: {city}: COLOCATED {n_reported} у контракта != {len(colocated)} групп")
    dups = [{"rule": w["rule"], "distance_m": w["distance_m"], "a": w["a"]["id"], "b": w["b"]["id"]}
            for w in qa["warnings"] if w["code"] == "POSSIBLE_DUPLICATE"]
    doubts = {}
    for f in features:
        name = (f["properties"].get("name_primary") or "").strip()
        for rule_id, rx, why in CATEGORY_DOUBT:
            if rx.search(name):
                doubts[f["id"]] = {"rule": rule_id, "reason": why}
                break
    return {"colocated": colocated, "possible_duplicates": dups, "category_doubt": doubts,
            "rules": {"colocated": "≥3 записей с одинаковыми координатами (округление до 5 знаков) — K05 check_objects",
                      "possible_duplicate": "одинаковый адрес или имя < 100 м; одна группа и номер дома < 50 м — K05 check_objects",
                      "category_doubt": {r: why for r, _, why in CATEGORY_DOUBT}}}


def build():
    man = load_manifest()
    BV, L = load_k03()
    names = district_names()
    rule = BV.assign(L, 71.43, 51.128)["rule"]  # label from the code itself, not from a registry
    data = build_data.build()                   # the places data.js is built from (same rounding)
    binding = k03_binding(APP, rule, data)
    binding["root"] = str(K03_ROOT.relative_to(APP))
    out = {"format": FORMAT, "as_of": AS_OF, "contract": K.CONTRACT_ID, "assign_rule": rule, "boundary_binding": binding,
           "group_kk": GROUP_KK, "district_names": names, "cities": {}}
    for city, cm in man["cities"].items():
        layers = {n: load_layer(city, n, fm, man, cm) for n, fm in cm["files"].items()}
        places = layers["places_social"]["features"]
        segs = [f for f in layers["segments"]["features"] if f["properties"]["subtype"] == "road"]
        k05 = k05_square_obs(city, APP / "inputs" / "k10" / cm["files"]["places_social"]["path"], places)
        tmpl = next(o for o in k05 if o["indicator_id"].endswith("conf_ge_0_0"))
        assigned, counts = {}, Counter()
        for f in places:
            lon, lat = f["geometry"]["coordinates"][:2]
            lon, lat = r6(lon), r6(lat)              # exactly the coordinates shown in data.js
            r = BV.assign(L, lon, lat)
            if r.get("rule") != rule:
                raise InputError(f"SEMANTIC: правило K03 {r.get('rule')} ≠ {rule}")
            if r.get("city") not in (city, None):
                raise InputError(f"SEMANTIC: {city}: {f['id']} привязан к городу {r.get('city')}")
            counts[r["status"]] += 1
            assigned[f["id"]] = {"status": r["status"], "reason": r.get("reason"), "district": r.get("district"),
                                 "candidates": r.get("candidates") or [], "lonlat": [lon, lat]}
        k03_src = {"source_id": f"K03-{rule}", "url": None,
                   "path": "inputs/k03v21_root/research/round-3-results/K03/boundary_validator.py",
                   "sha256": sha256(K03_DIR / "boundary_validator.py"), "retrieved_at": "2026-10-05T00:00:00Z",
                   "license": None, "locator": "assign(L, lon, lat)['status'] (patched copy, not upstream)",
                   "evidence": "K03 @ 44585de + k03_assign_v2_1.patch @ 5715a7f", "query": None}
        rows = list(k05)
        for st in ("matched", "ambiguous", "unmatched", "outside"):
            rows.append(derived_obs(tmpl, f"k03_district_status.{st}", counts.get(st, 0), "records",
                                    scope=f"{len(places)} записей объектов этого квадрата",
                                    derivation=f"число записей квадрата со статусом {st} по {rule}",
                                    method_id=rule, steps=["K03 assign() для каждой записи", "счёт по статусу"],
                                    source=k03_src))
        seg_src = dict(tmpl["source"], source_id="K10-r3-segments", path="inputs/k10/" + cm["files"]["segments"]["path"],
                       sha256=cm["files"]["segments"]["sha256"], url=man["cities"][city]["queries"]["segments"]["files"][0]["url"],
                       query="segment geometry intersects bbox", locator="features[].properties.k10_foot_access")
        fa = Counter(s["properties"]["k10_foot_access"] for s in segs)
        for k in ("unknown", "conditional", "denied", "allowed"):
            rows.append(derived_obs(tmpl, f"segments_foot_access.{k}", fa.get(k, 0), "segments",
                                    scope="все сегменты road пакета K10, пересекающие квадрат",
                                    derivation=f"число сегментов с k10_foot_access={k}",
                                    method_id="k10_rules.foot_access", steps=["K10 k10_rules.foot_access по access_restrictions"],
                                    source=seg_src))
        rows.append(city_missing_obs(tmpl, city, "overture_place_records.city_total", "records", "not_collected",
                                     "в пакете K10 r3 только квадрат; число записей по городу не собиралось"))
        rows.append(city_missing_obs(tmpl, city, "official_registry.schools", "records", "source_access_denied",
                                     "официальный реестр (data.egov.kz) недоступен из среды"))
        rows.append(city_missing_obs(tmpl, city, "capacity.school_places", "places", "not_in_source",
                                     "мощности школ нет ни в одном сохранённом источнике"))
        rows.append(city_missing_obs(tmpl, city, "population.children", "persons", "not_collected",
                                     "численность детей не собиралась"))
        errors, warnings = K.validate_all(rows, AS_OF)
        if errors:
            raise InputError(f"SEMANTIC: {city}: контракт {K.CONTRACT_ID}: {errors[:5]}")
        out["cities"][city] = {"geo_unit_id": tmpl["geo_unit_id"], "spatial_unit": tmpl["spatial_unit"],
                               "release": tmpl["release"], "place_district": assigned,
                               "district_status_counts": dict(counts), "observations": rows,
                               "validation": {"errors": 0, "warnings": sorted({w.split(": ", 1)[1].split(":")[0] for w in warnings})},
                               "qa": qa_labels(city, places)}
        q = out["cities"][city]["qa"]
        print(f"{city}: {dict(counts)}; {len(rows)} наблюдений, ошибок 0; QA: colocated "
              f"{[len(g['ids']) for g in q['colocated']]}, дубли {len(q['possible_duplicates'])}, "
              f"сомнения в категории {len(q['category_doubt'])}")
    return out


def render_text(out):
    txt = K.dumps_strict(out, separators=(",", ":"), sort_keys=True)
    K.loads_strict(txt)  # round-trip: strict JSON only
    return ("// GENERATED by tools/build_evidence.py (contract k05-obs-v1.2+k12r4+k05r5, K03, QA) — do not edit.\n"
            f"window.CITY_OBS = {txt};\n")


def main():
    try:
        out = build()
    except (InputError, K.ContractError) as e:
        print(f"ОШИБКА входных данных: {e}", file=sys.stderr)
        return 2
    OUT.write_text(render_text(out), encoding="utf-8", newline="\n")
    print(f"wrote {OUT.relative_to(APP)} ({OUT.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
