#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
K05 round 3: изолированный адаптер реальных данных K10 → k05-obs-v1.1.

Показатель: число ЗАПИСЕЙ Overture places выбранной группы (правило K10 group())
в полигоне района того же выпуска 2026-09-23.1. Это охват источника Overture
внутри рамки выгрузки K10, а не число объектов в городе и не официальный реестр.

Входы — только inputs/ (копии K10 @ e91898d с manifest). Код продукта, data/ и
эталоны не читаются для записи и не меняются; data/geo_sources/sara_osm.json
читается для эталонной версии границы Сарайшыка.

Требует shapely 2.1.2 и pyproj 3.7.2 (как у K10) для площади рамки.
Запуск: python research/round-3-results/K05/k05r3_adapter.py
Выход: examples/<city>/*.json, cases/*.json, adapter_summary.json
"""

from __future__ import annotations

import copy
import hashlib
import json
import sys
from pathlib import Path

from pyproj import Geod
from shapely.geometry import box, shape

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(HERE))
import k05r3_contract as C  # noqa: E402

IN = HERE / "inputs" / "k10"
K10_REF = "claude/save-work-handoff-j7pc05@e91898d596164bcf6e853b921a49f82126074a35"
RELEASE = "2026-09-23.1"
SNAPSHOT = "2026-09-23"
AS_OF = "2026-10-05"
MAX_AGE_DAYS = 45  # политика примера: выпуски Overture ежемесячные + запас; не норматив
GROUPS = ("school", "preschool", "college_university", "hospital", "outpatient_clinic",
          "pharmacy", "government_office")
THRESHOLDS = {"confidence>=0.0": ("conf_ge_0_0", 0.0), "confidence>=0.5": ("conf_ge_0_5", 0.5)}
CITY = {"shymkent": "kz.shymkent", "astana": "kz.astana"}
# Районы → id по OSM relation (Астана — те же id, что в data/astana_districts.geojson).
UNIT_BY_RELATION = {
    "5548210": "abai", "5550509": "al_farabi", "5551117": "enbekshi", "5551119": "karatau",
    "3479876": "esil", "3482819": "almaty", "3486954": "saryarka", "8593081": "baikonur",
    "20593940": "nura", "19733918": "saraishyk",
}
S3 = "https://overturemaps-us-west-2.s3.us-west-2.amazonaws.com"
GEOD = Geod(ellps="WGS84")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def rel(path: Path) -> str:
    return str(path.relative_to(ROOT))


def dump(path: Path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


def raw_sha(name: str) -> str:
    for line in (IN / "provenance/raw_extracts.sha256").read_text().splitlines():
        h, f = line.split()
        if f == name:
            return h
    raise KeyError(name)


def area_km2(geom) -> float:
    return abs(GEOD.geometry_area_perimeter(geom)[0]) / 1e6


def units(city: str):
    """Полигоны города и районов K10 + доля площади внутри рамки выгрузки places."""
    prov = json.loads((IN / f"provenance/{city}_places.provenance.json").read_text(encoding="utf-8"))
    bb = box(*prov["query_bbox"])
    gj = json.loads((IN / f"samples/{city}_districts_overture.geojson").read_text(encoding="utf-8"))
    out = {}
    for f in gj["features"]:
        p = f["properties"]
        g = shape(f["geometry"])
        a = area_km2(g)
        frac = area_km2(g.intersection(bb)) / a
        rel_id, ver = p["osm_relation"].lstrip("r").split("@")
        uid = CITY[city] if p["unit_kind"] == "city" else f"{CITY[city]}.{UNIT_BY_RELATION[rel_id]}"
        out[p["name_primary"]] = {
            "geo_unit_id": uid, "osm_relation": p["osm_relation"], "subtype": p["overture_subtype"],
            "area_km2": round(a, 3), "area_fraction_in_bbox": round(frac, 6),
            "boundary_version": f"overture:{RELEASE}/osm:r{rel_id}@{ver}",
        }
    return out, prov


def method(city, t, prov):
    return {
        "id": "k10_e02_places_by_district+k05r3_adapter",
        "steps": [
            f"K10 overture_extract.py: строки places выпуска {RELEASE}, bbox {prov['query_bbox']}",
            "K10 places_by_district.py: точка в полигоне города и района того же выпуска, группа по K10 group()",
            f"фильтр confidence >= {t}; счёт записей без дедупликации",
            "K05 adapter: отсутствующая в E02 группа = 0 записей; охват = доля площади района в bbox",
        ],
        "parameters": {"confidence_min": t, "query_bbox": prov["query_bbox"], "release": RELEASE,
                       "k10_ref": K10_REF, "group_rule": "places_by_district.group()"},
    }


def overture_counts(city):
    """Наблюдения по районам из K10 E02 (полная выгрузка в рамке, без лимита на группу)."""
    e02_path = IN / "results/E02_social_poi_by_district.json"
    e02 = json.loads(e02_path.read_text(encoding="utf-8"))
    res = next(r for r in e02["results"] if r["city"] == city)
    u, prov = units(city)
    obs, zero_partial = [], []
    for tkey, (tid, t) in THRESHOLDS.items():
        by_unit = res["counts_by_threshold"][tkey]
        for name, info in u.items():
            if info["geo_unit_id"] == CITY[city]:
                continue
            counts = by_unit.get(name, {})
            complete = info["area_fraction_in_bbox"] >= 0.999999
            for g in GROUPS:
                n = counts.get(g, 0)
                status, value, reason = ("reported_zero" if n == 0 else "reported"), n, None
                if n == 0 and not complete:
                    status, value, reason = "missing", None, "zero_in_partial_coverage"
                    zero_partial.append((info["geo_unit_id"], g, tid))
                obs.append({
                    "schema_version": C.SCHEMA_VERSION,
                    "obs_id": f"{info['geo_unit_id']}.overture_place_records.{g}.{tid}@{RELEASE}",
                    "city_id": CITY[city], "geo_unit_id": info["geo_unit_id"],
                    "indicator_id": f"overture_place_records.{g}.{tid}",
                    "period": SNAPSHOT, "release": RELEASE,
                    "value": value, "unit": "records", "value_status": status, "missing_reason": reason,
                    "kind": "derived",
                    "source": {
                        "source_id": f"overture-places-{RELEASE}",
                        "url": f"{S3}/release/{RELEASE}/theme=places/type=place/",
                        "sha256": raw_sha(f"{city}_places.jsonl"),
                        "retrieved_at": prov["started_utc"],
                        "locator": f"K10 E02 results[city={city}].counts_by_threshold['{tkey}']['{name}']['{g}']",
                        "license": "по записям: CDLA-Permissive-2.0 / CC0-1.0 / Apache-2.0 (см. K10 datasets.json)",
                        "evidence": f"{rel(e02_path)} sha256={sha256(e02_path)}; raw extract не в git",
                    },
                    "data_version": f"overture@{RELEASE}",
                    "boundary_version": info["boundary_version"],
                    "coverage": {
                        "complete": complete,
                        "scope": f"записи Overture {RELEASE} с точкой в полигоне района; не реестр и не все объекты",
                        "selection": "все записи выгрузки K10 в рамке, без лимита",
                        "area_fraction": info["area_fraction_in_bbox"], "cap_per_group": None,
                    },
                    "method": method(city, t, prov),
                    "max_age_days": MAX_AGE_DAYS,
                    "derivation": "count(records: group=g, confidence>=t, point in district polygon)",
                    "note": (None if complete else
                             f"район покрыт рамкой выгрузки на {info['area_fraction_in_bbox']:.2%}: значение — нижняя граница"),
                })
    return obs, zero_partial, u, prov


def sample_rows(city):
    path = IN / f"samples/{city}_places_social_sample.jsonl"
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()], path


def sample_counts(city, u, prov):
    """Число строк выборки K10 по группе (до 15 на группу с наибольшей confidence)."""
    rows, path = sample_rows(city)
    city_info = next(i for i in u.values() if i["geo_unit_id"] == CITY[city])
    obs = []
    for g in GROUPS:
        n = sum(1 for r in rows if r["k10_group"] == g)
        obs.append({
            "schema_version": C.SCHEMA_VERSION,
            "obs_id": f"{CITY[city]}.k10_sample_rows.{g}@{RELEASE}",
            "city_id": CITY[city], "geo_unit_id": CITY[city],
            "indicator_id": f"k10_sample_rows.{g}",
            "period": SNAPSHOT, "release": RELEASE,
            "value": n, "unit": "records", "value_status": "reported_zero" if n == 0 else "reported",
            "missing_reason": None, "kind": "derived",
            "source": {"source_id": "k10-places-social-sample", "path": rel(path), "sha256": sha256(path),
                       "retrieved_at": prov["started_utc"], "locator": f"rows[k10_group={g}]",
                       "license": "по записям Overture", "evidence": K10_REF},
            "data_version": f"overture@{RELEASE}",
            "boundary_version": city_info["boundary_version"],
            "coverage": {"complete": False,
                         "scope": "выборка K10 для образца, не полный счёт",
                         "selection": "до 15 записей на группу по убыванию confidence, в полигоне города, в рамке",
                         "area_fraction": city_info["area_fraction_in_bbox"], "cap_per_group": 15},
            "method": {"id": "k10_make_samples+count", "steps": [
                "K10 make_samples.py: PER_GROUP=15 по confidence", "K05: подсчёт строк по k10_group"],
                "parameters": {"cap_per_group": 15}},
            "max_age_days": MAX_AGE_DAYS,
            "derivation": "count(sample rows with k10_group=g)",
            "note": "Для групп с n<15 выборка содержит все записи группы в полигоне города внутри рамки",
        })
    return obs, rows


def official_missing(city):
    log = json.loads((IN / "access_log.json").read_text(encoding="utf-8"))
    entry = next(e for v in log.values() if isinstance(v, list) for e in v
                 if isinstance(e, dict) and e.get("host") == "stat.gov.kz")
    return {
        "schema_version": C.SCHEMA_VERSION,
        "obs_id": f"{CITY[city]}.official_registry.school_count@unknown",
        "city_id": CITY[city], "geo_unit_id": CITY[city],
        "indicator_id": "official_registry.school_count",
        "period": "unknown", "release": None,
        "value": None, "unit": "schools", "value_status": "missing",
        "missing_reason": "source_access_denied", "kind": "observed",
        "source": {"source_id": "stat.gov.kz", "url": entry["url"], "retrieved_at": None,
                   "locator": "не получено", "license": None,
                   "evidence": f"K10 access_log {entry['utc']} {entry['result']}"},
        "data_version": "official@not_retrieved",
        "boundary_version": None,
        "coverage": {"complete": False, "scope": "официальный показатель, не открыт",
                     "selection": "нет", "area_fraction": None, "cap_per_group": None},
        "method": {"id": "not_retrieved", "steps": ["один запрос, CONNECT 403 по политике сети среды"]},
        "note": "Отсутствие доступа, а не отсутствие данных. Overture-счёт сюда не подставляется.",
    }


def product_boundary_ref():
    """Эталон продукта для Астаны: версия известна только для Сарайшыка (sara_osm.json)."""
    gj = json.loads((ROOT / "data/astana_districts.geojson").read_text(encoding="utf-8"))
    sara = json.loads((ROOT / "data/geo_sources/sara_osm.json").read_text(encoding="utf-8"))
    sara_ver = {str(e["id"]): e.get("version") for e in sara["elements"] if e["type"] == "relation"}
    ref = {}
    for f in gj["features"]:
        rid = str(f["properties"]["osm_id"])
        ver = f["properties"].get("osm_version") or sara_ver.get(rid)
        ref[f"kz.astana.{f['properties']['id']}"] = f"product:osm:r{rid}@{ver or 'unknown'}"
    return ref


def find(obs, unit, indicator):
    return next(o for o in obs if o["geo_unit_id"] == unit and o["indicator_id"] == indicator)


def main():
    summary = {"as_of": AS_OF, "k10_ref": K10_REF, "release": RELEASE}
    all_obs = {}
    for city in ("shymkent", "astana"):
        obs, zero_partial, u, prov = overture_counts(city)
        s_obs, rows = sample_counts(city, u, prov)
        miss = official_missing(city)
        dump(HERE / f"examples/{city}/overture_place_record_counts.json", obs)
        dump(HERE / f"examples/{city}/k10_sample_row_counts.json", s_obs)
        dump(HERE / f"examples/{city}/official_registry_missing.json", miss)
        qa = C.check_objects(rows)
        dump(HERE / f"examples/{city}/sample_object_qa.json", qa)
        all_obs[city] = obs
        # Сверка: для групп с n<15 выборка = все записи группы в городе (порог 0.0).
        cross = {}
        for so in s_obs:
            g = so["indicator_id"].split(".")[1]
            district_sum = sum(o["value"] or 0 for o in obs if o["indicator_id"] == f"overture_place_records.{g}.conf_ge_0_0")
            cross[g] = {"sample_rows": so["value"], "e02_district_sum_conf_ge_0_0": district_sum,
                        "consistent": (so["value"] == district_sum) if so["value"] < 15 else (district_sum >= 15)}
        school = [o for o in obs if o["indicator_id"] == "overture_place_records.school.conf_ge_0_5"]
        summary[city] = {
            "units": u,
            "observations": len(obs),
            "status_counts": {s: sum(1 for o in obs if o["value_status"] == s) for s in
                              ("reported", "reported_zero", "missing")},
            "zero_in_partial_coverage": zero_partial,
            "real_zero_examples": [o["obs_id"] for o in obs if o["value_status"] == "reported_zero"],
            "sample_vs_e02": cross,
            "school_conf_ge_0_5_city_sum": C.aggregate_sum(school),
            "object_qa": {"errors": len(qa["errors"]),
                          "warnings": {c: sum(1 for w in qa["warnings"] if w["code"] == c)
                                       for c in ("POSSIBLE_DUPLICATE", "COLOCATED")}},
        }

    sh, ast = all_obs["shymkent"], all_obs["astana"]
    ref = product_boundary_ref()
    cases = {}
    # 1. настоящий ноль (полный охват района)
    cases["real_zero"] = find(sh, "kz.shymkent.enbekshi", "overture_place_records.government_office.conf_ge_0_5")
    # 2. missing: официальный источник закрыт
    cases["missing_access_denied"] = [official_missing("shymkent"), official_missing("astana")]
    # 3. неполная выборка / неполный охват
    cases["incomplete_sample"] = json.loads((HERE / "examples/astana/k10_sample_row_counts.json").read_text(encoding="utf-8"))[0]
    cases["partial_coverage_lower_bound"] = find(ast, "kz.astana.esil", "overture_place_records.school.conf_ge_0_0")
    # 4. смешение городов / периодов
    cases["city_mix"] = [find(sh, "kz.shymkent.abai", "overture_place_records.school.conf_ge_0_5"),
                         find(ast, "kz.astana.esil", "overture_place_records.school.conf_ge_0_5")]
    older = copy.deepcopy(find(ast, "kz.astana.almaty", "overture_place_records.school.conf_ge_0_5"))
    older.update({"obs_id": "FIXTURE.period_mix.almaty@2026-08-19.0", "period": "2026-08-19",
                  "release": "2026-08-19.0", "kind": "synthetic", "data_version": "synthetic:k05r3-fixture",
                  "note": "ФИКСТУРА: копия реальной записи с другим периодом; значение из 2026-08-19.0 не наблюдалось"})
    cases["period_mix"] = [find(ast, "kz.astana.nura", "overture_place_records.school.conf_ge_0_5"), older]
    # 5. дубликат объекта: реальные подозрения + фикстура одинакового id
    rows_a, _ = sample_rows("astana")
    rows_s, _ = sample_rows("shymkent")
    cases["duplicate_object"] = {
        "astana_real": [w for w in C.check_objects(rows_a)["warnings"] if w["code"] == "POSSIBLE_DUPLICATE"],
        "shymkent_real": [w for w in C.check_objects(rows_s)["warnings"] if w["code"] == "POSSIBLE_DUPLICATE"],
        "shymkent_colocated": [w for w in C.check_objects(rows_s)["warnings"] if w["code"] == "COLOCATED"],
        "fixture_same_id": C.check_objects([rows_a[0], dict(rows_a[0])])["errors"],
    }
    # 6. synthetic
    syn = copy.deepcopy(find(sh, "kz.shymkent.karatau", "overture_place_records.school.conf_ge_0_5"))
    syn.update({"obs_id": "FIXTURE.synthetic.karatau", "value": 40, "kind": "synthetic",
                "data_version": "synthetic:k05r3-fixture", "note": "ФИКСТУРА: синтетическое значение для теста"})
    cases["synthetic"] = syn
    # 7. устаревший снимок / вытесненный выпуск
    cases["stale_check"] = {"obs": find(ast, "kz.astana.nura", "overture_place_records.school.conf_ge_0_5"),
                            "as_of_fresh": AS_OF, "as_of_stale": "2026-12-01",
                            "release_index_real": ["2026-08-19.0", "2026-09-23.0", "2026-09-23.1"],
                            "release_index_fixture_newer": ["2026-09-23.1", "2026-10-21.0"]}
    # 8. несовпадающая граница (Сарайшык: Overture @16, продукт @17)
    cases["boundary_mismatch"] = {"obs": find(ast, "kz.astana.saraishyk", "overture_place_records.school.conf_ge_0_5"),
                                  "product_boundary_ref": ref}
    dump(HERE / "cases/cases.json", cases)

    # Прогон валидатора по всем примерам.
    val = {}
    for path in sorted((HERE / "examples").rglob("*.json")):
        if path.name == "sample_object_qa.json":
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        items = data if isinstance(data, list) else [data]
        r = {"REJECT": 0, "WARN": 0, "OK": 0, "codes": {}}
        for o in items:
            e, w = C.validate(o, AS_OF, ref if o["city_id"] == "kz.astana" else None,
                              cases["stale_check"]["release_index_real"])
            r["REJECT" if e else "WARN" if w else "OK"] += 1
            for m in e + w:
                r["codes"][m.split(":")[0]] = r["codes"].get(m.split(":")[0], 0) + 1
        val[rel(path)] = r
    summary["validation"] = val
    summary["product_boundary_ref"] = ref
    dump(HERE / "adapter_summary.json", summary)
    print(json.dumps({k: summary[k] for k in ("validation",)}, ensure_ascii=False, indent=1))
    for c in ("shymkent", "astana"):
        s = summary[c]
        print(c, s["status_counts"], "zero_partial:", s["zero_in_partial_coverage"],
              "qa:", s["object_qa"], "school>=0.5 sum:", s["school_conf_ge_0_5_city_sum"])
        print("  sample_vs_e02:", {g: (v["sample_rows"], v["e02_district_sum_conf_ge_0_0"], v["consistent"])
                                   for g, v in s["sample_vs_e02"].items()})


if __name__ == "__main__":
    main()
