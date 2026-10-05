"""Stage 2 adapter: K10 slice -> K03 district status -> K05 observations -> web/evidence.js.

Minimal glue, not a platform:
  * district status of every place comes from K03 `assign()` (rule k03_assign_v1) run unmodified
    from inputs/k03_root/ (needs shapely + pyproj, see requirements-build.txt);
  * every number shown as a "fact" is a k05-obs-v1.1 observation validated by K05 `validate()`
    (stdlib) from inputs/k05_root/; any validation error aborts the build;
  * counts are numbers of Overture records in the K10 square, never city totals / capacity.

Usage (from prototypes/city-evidence/):  <python with shapely,pyproj> tools/build_evidence.py
Writes web/evidence.js only.
"""
import json
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
APP = HERE.parent
K03_DIR = APP / "inputs" / "k03_root" / "research" / "round-3-results" / "K03"
K05_DIR = APP / "inputs" / "k05_root" / "round-3-results" / "K05"
OUT = APP / "web" / "evidence.js"
AS_OF = "2026-10-05"
SLICE_ID = "k10r3"                         # scenario part of fact IDs (K02 ID pattern: [A-Za-z0-9_]+)

sys.path.insert(0, str(HERE))
from build_data import GROUPS, InputError, load_layer, load_manifest  # noqa: E402

GROUP_KK = {  # черновик казахских подписей, требует проверки носителем
    "school": "Мектеп", "preschool": "Балабақша", "college_university": "Колледж / ЖОО",
    "hospital": "Аурухана", "outpatient_clinic": "Емхана", "pharmacy": "Дәріхана",
    "government_office": "Мемлекеттік мекеме",
}


def load_k03():
    sys.path.insert(0, str(K03_DIR))
    import boundary_validator as BV  # noqa: E402  (K03 code, read before use: read-only, no network)
    return BV, BV.Layers()


def load_k05():
    sys.path.insert(0, str(K05_DIR))
    import k05r3_contract as C  # noqa: E402
    return C


def district_names():
    reg = json.loads((K03_DIR / "boundary_registry.json").read_text(encoding="utf-8"))
    out = {}
    for u in reg["units"]:
        out[u["unit_id"]] = {"ru": (u["names"].get("ru") or {}).get("value"),
                             "kk": (u["names"].get("kk") or {}).get("value"),
                             "legal_status": u.get("legal_status")}
    return out, reg.get("assignment_rule", {}).get("id", "k03_assign_v1")


def obs(city_id, geo, indicator, value, status, unit, *, kind, source, coverage, method, reason=None, note=None):
    return {"schema_version": "k05-obs-v1.1", "obs_id": f"{geo}/{SLICE_ID}/{indicator}", "city_id": city_id,
            "geo_unit_id": geo, "indicator_id": indicator, "period": "2026-09-23", "release": "2026-09-23.1",
            "value": value, "unit": unit, "value_status": status, "missing_reason": reason, "kind": kind,
            "source": source, "data_version": "overture-2026-09-23.1/k10r3-602f0c0", "boundary_version": None,
            "coverage": coverage, "method": method, "max_age_days": None, "derivation": None, "note": note}


def city_observations(city, cm, places, assign_counts):
    city_id, geo = f"kz.{city}", f"kz.{city}.k10r3_bbox"
    pfile = cm["files"]["places_social"]
    src = {"source_id": "K10-r3-places", "path": "inputs/k10/" + pfile["path"], "sha256": pfile["sha256"],
           "locator": "features[].properties.k10_group", "license": "CDLA-Permissive-2.0 / CC0-1.0 / Apache-2.0 / ODbL-1.0 по записям",
           "retrieved_at": cm.get("finished_utc"), "url": None, "evidence": None}
    cov = {"complete": False, "scope": f"квадрат K10 {cm['bbox']} (~2×2 км), не весь город",
           "selection": "все записи Overture places внутри квадрата, отнесённые правилом K10 к соцгруппам",
           "area_fraction": None, "cap_per_group": None}
    meth = {"id": "count_records_in_bbox", "steps": ["k10_rules.social_group", "point in bbox", "count by group"]}
    rows = []
    by_group = Counter(p["properties"]["k10_group"] for p in places)
    rows.append(obs(city_id, geo, "places.total", len(places), "reported", "records", kind="observed",
                    source=src, coverage=cov, method=meth))
    for g in GROUPS:
        n = by_group.get(g, 0)
        if n:
            rows.append(obs(city_id, geo, f"places.{g}", n, "reported", "records", kind="observed",
                            source=src, coverage=cov, method=meth))
        else:  # zero records in a partial slice does not prove absence (K05 ZERO_ON_PARTIAL)
            rows.append(obs(city_id, geo, f"places.{g}", None, "missing", "records", kind="observed", source=src,
                            coverage=cov, method=meth, reason="zero_in_partial_coverage",
                            note="0 записей в срезе; не доказывает, что объектов нет"))
    k03 = {"source_id": "K03-k03_assign_v1", "path": "inputs/k03_root/research/round-3-results/K03/boundary_validator.py",
           "sha256": None, "url": None, "locator": "assign(L, lon, lat)['status']", "license": None,
           "retrieved_at": "2026-10-05 (K03 commit 44585de)", "evidence": None}
    k03["sha256"] = __import__("hashlib").sha256((K03_DIR / "boundary_validator.py").read_bytes()).hexdigest()
    dmeth = {"id": "k03_assign_v1", "steps": ["K03 assign() for each record", "count by status"]}
    # Status counts are complete over the slice's own records (the population is the slice, not the city).
    slice_cov = {"complete": True, "scope": f"{len(places)} записей объектов этого среза", "selection": "все записи среза",
                 "area_fraction": None, "cap_per_group": None}
    for st in ("matched", "ambiguous", "unmatched", "outside"):
        n = assign_counts.get(st, 0)
        o = obs(city_id, geo, f"district_status.{st}", n, "reported" if n else "reported_zero", "records",
                kind="derived", source=k03, coverage=slice_cov, method=dmeth)
        o["derivation"] = "число записей среза, для которых K03 assign() вернул статус " + st
        rows.append(o)
    segf = cm["files"]["segments"]
    ssrc = dict(src, source_id="K10-r3-segments", path="inputs/k10/" + segf["path"], sha256=segf["sha256"],
                locator="features[].properties.k10_foot_access")
    fa = Counter(s["properties"]["k10_foot_access"] for s in segs_of(cm))
    for k in ("unknown", "conditional", "denied", "allowed"):
        n = fa.get(k, 0)
        rows.append(obs(city_id, geo, f"segments.foot_{k}", n, "reported" if n else "reported_zero", "segments", kind="observed",
                        source=ssrc, coverage=dict(slice_cov, scope="все сегменты road пакета K10, пересекающие квадрат"),
                        method={"id": "count_segments_by_foot_access", "steps": ["k10_rules.foot_access"]}))
    nosrc = {"source_id": "none", "url": "https://data.egov.kz/", "locator": "официальный реестр не получен",
             "sha256": None, "path": None, "license": None, "retrieved_at": None, "evidence": "K10/K07 access_log: 403"}
    gap_cov = dict(cov, selection="нет данных")
    gap_meth = {"id": "not_computed", "steps": ["источник отсутствует в пакете"]}
    rows.append(obs(city_id, geo, "capacity.school_places", None, "missing", "places", kind="observed", source=nosrc,
                    coverage=gap_cov, method=gap_meth, reason="not_in_source"))
    rows.append(obs(city_id, geo, "registry.official_schools", None, "missing", "records", kind="observed", source=nosrc,
                    coverage=gap_cov, method=gap_meth, reason="source_access_denied"))
    rows.append(obs(city_id, geo, "population.children", None, "missing", "persons", kind="observed", source=nosrc,
                    coverage=gap_cov, method=gap_meth, reason="not_collected"))
    return rows


_SEGS = {}


def segs_of(cm):
    return _SEGS[cm["bbox"][0]]


def main():
    try:
        man = load_manifest()
        BV, L = load_k03()
        C = load_k05()
        names, rule = district_names()
        out = {"as_of": AS_OF, "slice_id": SLICE_ID, "assign_rule": rule, "group_kk": GROUP_KK,
               "district_names": names, "cities": {}}
        for city, cm in man["cities"].items():
            layers = {n: load_layer(city, n, fm) for n, fm in cm["files"].items()}
            _SEGS[cm["bbox"][0]] = [f for f in layers["segments"]["features"] if f["properties"]["subtype"] == "road"]
            places = layers["places_social"]["features"]
            assigned, counts = {}, Counter()
            for f in places:
                lon, lat = f["geometry"]["coordinates"][:2]
                r = BV.assign(L, lon, lat)
                counts[r["status"]] += 1
                assigned[f["id"]] = {"status": r["status"], "reason": r.get("reason"), "district": r.get("district"),
                                     "candidates": r.get("candidates") or [],
                                     "assign_city": r.get("city")}
            rows = city_observations(city, cm, places, counts)
            report = []
            for o in rows:
                errs, warns = C.validate(o, as_of=AS_OF)
                if errs:
                    raise InputError(f"K05 validate {o['obs_id']}: {errs}")
                report.append({"obs_id": o["obs_id"], "warnings": warns})
            mism = [pid for pid, a in assigned.items() if a["assign_city"] not in (city, None)]
            out["cities"][city] = {"place_district": assigned, "district_status_counts": dict(counts),
                                   "observations": rows, "validation": report, "city_mismatch": mism}
            print(f"{city}: {dict(counts)}; {len(rows)} наблюдений, ошибок K05 0, предупреждений "
                  f"{sum(len(r['warnings']) for r in report)}")
    except InputError as e:
        print(f"ОШИБКА входных данных: {e}", file=sys.stderr)
        return 2
    txt = json.dumps(out, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    OUT.write_text("// GENERATED by tools/build_evidence.py (K03 assign + K05 validate) — do not edit.\n"
                   f"window.CITY_OBS = {txt};\n", encoding="utf-8")
    print(f"wrote {OUT.relative_to(APP)} ({OUT.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
