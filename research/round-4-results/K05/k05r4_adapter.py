#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
K05 round 4: адаптер счётчиков записей K10 round 3 (квадрат 2×2 км) → k05-obs-v1.2.

Показатель — число записей Overture places группы K10 с confidence ≥ t внутри
заданного квадрата (полный ответ запроса K10 для этого квадрата и выпуска).
Это НЕ число объектов района или города: квадрат делит два района, районные
суммы E02 раунда 2 сюда не переносятся.

Входы — только inputs/k10_r3/ (побайтные копии K10 @ ea703f1, manifest).
Только стандартная библиотека (jsonschema нужен лишь тестам).
Запуск: python research/round-4-results/K05/k05r4_adapter.py [city ...]
Выход: examples/<city>/*.json, cases/cases.json, adapter_summary.json
"""

from __future__ import annotations

import copy
import hashlib
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(HERE))
import k05r4_contract as C  # noqa: E402

IN = HERE / "inputs" / "k10_r3"
K10_REF = "claude/save-work-handoff-j7pc05@ea703f1ddd3a411430a981164a78a7dda64ec909"
CITY = {"shymkent": "kz.shymkent", "astana": "kz.astana"}
THRESHOLDS = (("conf_ge_0_0", 0.0), ("conf_ge_0_5", 0.5))
MAX_AGE_DAYS = 45  # политика примера (как в раунде 3), не норматив
# Доли площади квадрата в районах K10 round 2 (посчитано pyproj/shapely, см. REPORT §2).
OVERLAPS = {"shymkent": {"Еңбекші ауданы": 0.4639, "Әл-Фараби ауданы": 0.5361},
            "astana": {"Байқоңыр ауданы": 0.6513, "Сарыарқа ауданы": 0.3487}}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def rel(path: Path) -> str:
    return str(path.relative_to(ROOT))


def dump(path: Path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


def load_rules():
    """SOCIAL_GROUPS и RELEASE из скопированного k10_rules.py (только константы)."""
    ns = {}
    exec(compile((IN / "scripts/k10_rules.py").read_text(encoding="utf-8"), "k10_rules", "exec"), ns)
    return ns["SOCIAL_GROUPS"], ns["RELEASE"]


GROUPS, RELEASE = load_rules()
SNAPSHOT = RELEASE.split(".")[0]


def city_inputs(city):
    places_path = IN / f"data/{city}/places_social.geojson"
    sel_path = IN / f"selection/{city}_bbox_selection.json"
    fc = json.loads(places_path.read_text(encoding="utf-8"))
    sel = json.loads(sel_path.read_text(encoding="utf-8"))
    man = json.loads((IN / "package_manifest.json").read_text(encoding="utf-8"))["cities"][city]
    if man["files"]["places_social"]["sha256"] != sha256(places_path):
        raise ValueError(f"{city}: sha256 places_social не совпадает с package_manifest")
    return fc, sel, man, places_path, sel_path


def base_obs(city, fc, sel, man, places_path, sel_path, edge_n):
    sq = sel["selected"]
    q = man["queries"]["places"]
    return {
        "schema_version": C.SCHEMA_VERSION,
        "city_id": CITY[city],
        "geo_unit_id": f"{CITY[city]}.k10sq_r{sq['row']}_c{sq['col']}",
        "period": SNAPSHOT, "release": RELEASE,
        "unit": "records", "kind": "derived", "missing_reason": None,
        "source": {
            "source_id": f"overture-places-{RELEASE}",
            "url": q["files"][0]["url"],
            "path": rel(places_path), "sha256": sha256(places_path),
            "retrieved_at": man["started_utc"],
            "license": "по записям: CDLA-Permissive-2.0 / CC0-1.0 / Apache-2.0",
            "query": q["query"],
            "evidence": f"{K10_REF}; row_groups {q['files'][0]['row_groups_read']}",
        },
        "data_version": f"overture@{RELEASE}",
        "boundary_version": f"k10_r3_square:r{sq['row']}_c{sq['col']}@{sha256(sel_path)[:12]}",
        "spatial_unit": {
            "type": "bbox", "crs": "EPSG:4326", "bbox": sq["bbox"], "edges_inclusive": True,
            "area_km2": None, "geometry_source": rel(sel_path), "geometry_sha256": sha256(sel_path),
            "overlaps_districts": OVERLAPS[city],
        },
        "coverage": {
            "complete": True,
            "scope": "все записи выпуска с точкой в квадрате (полный ответ запроса), не реестр района/города",
            "selection": "без лимита; правило группы K10 social_group",
            "area_fraction": 1.0, "cap_per_group": None,
        },
        "max_age_days": MAX_AGE_DAYS,
        "note": f"квадрат делит районы {OVERLAPS[city]}; записей ближе 100 м к краю: {edge_n}",
    }


def edge_count(fc, bb, m=100.0):
    import math
    n = 0
    for f in fc["features"]:
        x, y = f["geometry"]["coordinates"][:2]
        dx = min(x - bb[0], bb[2] - x) * 111320.0 * math.cos(math.radians(y))
        dy = min(y - bb[1], bb[3] - y) * 111320.0
        n += min(dx, dy) < m
    return n


def counts(city):
    fc, sel, man, places_path, sel_path = city_inputs(city)
    bb = sel["selected"]["bbox"]
    qa = C.check_features(fc, city, bb, GROUPS)
    if qa["errors"]:
        raise ValueError(f"{city}: входы не прошли проверку объектов: {qa['errors'][:3]}")
    edge_n = edge_count(fc, bb)
    base = base_obs(city, fc, sel, man, places_path, sel_path, edge_n)
    feats = [f["properties"] for f in fc["features"]]
    unknown_conf = sum(1 for p in feats if p.get("confidence") is None)
    obs = []
    for tid, t in THRESHOLDS:
        for g in GROUPS:
            n = sum(1 for p in feats if p["k10_group"] == g and p.get("confidence") is not None
                    and p["confidence"] >= t)
            o = copy.deepcopy(base)
            o.update({
                "obs_id": f"{base['geo_unit_id']}.overture_place_records.{g}.{tid}@{RELEASE}",
                "indicator_id": f"overture_place_records.{g}.{tid}",
                "value": n, "value_status": "reported_zero" if n == 0 else "reported",
                "derivation": f"count(features: k10_group={g}, confidence>={t}) в квадрате",
                "method": {"id": "k10r3_package+k05r4_adapter", "steps": [
                    "K10 download.py: точка в bbox И правило social_group, выпуск " + RELEASE,
                    f"K05: счёт записей группы с confidence >= {t}; confidence=null не считается",
                ], "parameters": {"confidence_min": t, "bbox": bb, "k10_ref": K10_REF}},
            })
            o["source"]["locator"] = f"{rel(places_path)}#features[k10_group={g}][confidence>={t}]"
            if unknown_conf and t > 0:
                # Неизвестная confidence не равна 0: порог не проверить → нижняя граница.
                o["coverage"]["complete"] = False
                o["coverage"]["selection"] += f"; {unknown_conf} записей без confidence не учтены"
                if n == 0:
                    o.update(value=None, value_status="missing", missing_reason="zero_in_partial_coverage")
            obs.append(o)
    # Категория вне правила K10: данных нет, это не 0.
    park = copy.deepcopy(base)
    park.update({
        "obs_id": f"{base['geo_unit_id']}.overture_place_records.park.conf_ge_0_0@{RELEASE}",
        "indicator_id": "overture_place_records.park.conf_ge_0_0",
        "value": None, "value_status": "missing", "missing_reason": "not_collected",
        "derivation": "не вычислялось: категория park не извлекалась",
        "method": {"id": "not_collected", "steps": ["группа park не входит в K10 social_group; выгрузка её не содержит"]},
    })
    park["source"]["locator"] = "нет: категория не извлекалась"
    park["coverage"] = dict(base["coverage"], complete=False, selection="категория не извлекалась")
    return obs, park, qa, fc, base


def main(cities):
    exp = json.loads((IN / "tests/expected_counts.json").read_text(encoding="utf-8"))["cities"]
    summary = {"k10_ref": K10_REF, "release": RELEASE, "cities": {}}
    built = {}
    for city in cities:
        obs, park, qa, fc, base = counts(city)
        dump(HERE / f"examples/{city}/square_place_record_counts.json", obs)
        dump(HERE / f"examples/{city}/square_not_collected_missing.json", park)
        dump(HERE / f"examples/{city}/square_object_qa.json", qa)
        by0 = {o["indicator_id"].split(".")[1]: o["value"] for o in obs if o["indicator_id"].endswith("conf_ge_0_0")}
        val = {}
        for o in obs + [park]:
            e, w = C.validate(o, "2026-10-05")
            for m in e + w:
                val[m.split(":")[0]] = val.get(m.split(":")[0], 0) + 1
            if e:
                raise ValueError(f"{o['obs_id']}: {e}")
        summary["cities"][city] = {
            "geo_unit_id": base["geo_unit_id"], "bbox": base["spatial_unit"]["bbox"],
            "records": len(fc["features"]),
            "counts_conf_ge_0_0": by0,
            "matches_k10_expected_counts": by0 == exp[city]["places_by_group"],
            "counts_conf_ge_0_5": {o["indicator_id"].split(".")[1]: o["value"] for o in obs
                                   if o["indicator_id"].endswith("conf_ge_0_5")},
            "real_zeros": [o["obs_id"] for o in obs if o["value_status"] == "reported_zero"],
            "validator_codes": val,
            "object_qa": {"errors": len(qa["errors"]),
                          "warnings": {c: sum(1 for w in qa["warnings"] if w["code"] == c)
                                       for c in ("POSSIBLE_DUPLICATE", "COLOCATED", "CONFIDENCE_UNKNOWN")}},
        }
        built[city] = (obs, park, fc)
    if set(cities) == {"shymkent", "astana"}:
        build_cases(built)
    dump(HERE / "adapter_summary.json", summary)
    print(json.dumps(summary, ensure_ascii=False, indent=1))


def find(obs, g, tid):
    return next(o for o in obs if o["indicator_id"] == f"overture_place_records.{g}.{tid}")


def build_cases(built):
    sh, sh_park, sh_fc = built["shymkent"]
    ast, ast_park, ast_fc = built["astana"]
    r3 = json.loads((ROOT / "research/round-3-results/K05/examples/shymkent/overture_place_record_counts.json")
                    .read_text(encoding="utf-8"))
    e02_enbekshi = next(o for o in r3 if o["geo_unit_id"] == "kz.shymkent.enbekshi"
                        and o["indicator_id"] == "overture_place_records.school.conf_ge_0_5")
    shifted = copy.deepcopy(find(sh, "school", "conf_ge_0_5"))
    shifted.update(obs_id="FIXTURE.period_shift", period="2026-08-19", release="2026-08-19.0",
                   kind="synthetic", data_version="synthetic:k05r4-fixture",
                   note="ФИКСТУРА: другой период; значение из 2026-08-19.0 не наблюдалось")
    shifted["spatial_unit"]["bbox"] = [69.62, 42.33, 69.64, 42.35]  # не пересекается с квадратом
    same_box = copy.deepcopy(find(sh, "pharmacy", "conf_ge_0_5"))
    same_box.update(obs_id="FIXTURE.overlap", geo_unit_id="kz.shymkent.fixture_box")
    same_box["spatial_unit"]["bbox"] = [69.60, 42.31, 69.63, 42.33]
    dup_fc = copy.deepcopy(sh_fc)
    dup_fc["features"].append(copy.deepcopy(dup_fc["features"][0]))
    wrong_city_fc = copy.deepcopy(sh_fc)
    wrong_city_fc["features"][0]["properties"]["city"] = "astana"
    unknown_conf_fc = copy.deepcopy(sh_fc)
    unknown_conf_fc["features"][0]["properties"]["confidence"] = None
    bb_sh = sh[0]["spatial_unit"]["bbox"]
    cases = {
        "real_zero": find(sh, "government_office", "conf_ge_0_5"),
        "missing_not_zero": [sh_park, ast_park],
        "period_mix": [find(sh, "school", "conf_ge_0_5"), shifted],
        "geometry_mix_legacy_district": [find(sh, "school", "conf_ge_0_5"), e02_enbekshi],
        "geometry_overlap": [find(sh, "pharmacy", "conf_ge_0_5"), same_box],
        "unknown_period_numeric": dict(find(sh, "school", "conf_ge_0_5"), period="unknown"),
        "unknown_spatial_numeric": dict(find(sh, "school", "conf_ge_0_5"),
                                        spatial_unit={"type": "unknown", "crs": "EPSG:4326"}),
        "unknown_confidence_qa": C.check_features(unknown_conf_fc, "shymkent", bb_sh, GROUPS),
        "repeated_object_qa": C.check_features(dup_fc, "shymkent", bb_sh, GROUPS),
        "real_possible_duplicates": {
            "shymkent": [w for w in C.check_features(sh_fc, "shymkent", bb_sh, GROUPS)["warnings"]
                         if w["code"] in ("POSSIBLE_DUPLICATE", "COLOCATED")],
            "astana": [w for w in C.check_features(ast_fc, "astana", ast[0]["spatial_unit"]["bbox"], GROUPS)["warnings"]
                       if w["code"] in ("POSSIBLE_DUPLICATE", "COLOCATED")]},
        "city_mismatch_feature_qa": C.check_features(wrong_city_fc, "shymkent", bb_sh, GROUPS),
        "city_mismatch_obs": dict(find(sh, "school", "conf_ge_0_5"), city_id="kz.astana",
                                  geo_unit_id="kz.astana.k10sq_r11_c12"),
        "city_mix_aggregate": [find(sh, "school", "conf_ge_0_5"), find(ast, "school", "conf_ge_0_5")],
    }
    dump(HERE / "cases/cases.json", cases)


if __name__ == "__main__":
    main(sys.argv[1:] or ["shymkent", "astana"])
