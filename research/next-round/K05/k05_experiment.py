#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
K05: воспроизводимый эксперимент «нет данных записано как ноль».

Что делает (только чтение data/, запись только в эту папку и во временный каталог):
  E1. Хэширует data/real_context*.json и data/city_data.json и ищет их потребителей в коде.
  E2. Вызывает настоящий fetch_real_context.handle_failure() с путями, подменёнными
      на временный каталог: показывает, что при сбое пишутся 25 нулей. Сеть не нужна.
  E3. Переводит текущие data/real_context*.json в наблюдения k05-obs-v1: 25 missing, 0 чисел.
  E4. Строит примеры из настоящих локальных файлов: настоящий ноль, число, устаревшее
      значение (из снимка OSM data/geo_sources) и синтетика (city_data.json).
  E5. Прогоняет валидатор по примерам и неверным примерам; сравнивает наивную сумму
      и агрегат без подмены null нулём.
Итог: experiment_output.json и examples/*.json.

Запуск из корня репозитория:  python research/next-round/K05/k05_experiment.py
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(HERE))
import k05_validator as V  # noqa: E402

AS_OF = "2026-10-05"
EX = HERE / "examples"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def rel(path: Path) -> str:
    return str(path.relative_to(ROOT))


def dump(path: Path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def e1_inventory():
    files = ["data/real_context.json", "data/real_context_meta.json", "data/city_data.json",
             "data/astana_districts.geojson", "data/geo_sources/astana_districts_overpass.json"]
    hashes = {f: sha256(ROOT / f) for f in files}
    # Кто читает real_context: git grep по отслеживаемым файлам кода (без research/).
    res = subprocess.run(["git", "grep", "-l", "real_context", "--", "*.py", "*.js", "*.html",
                          ":!research"], cwd=ROOT, capture_output=True, text=True)
    consumers = sorted(p for p in res.stdout.split() if p)
    rc = json.loads((ROOT / "data/real_context.json").read_text(encoding="utf-8"))
    meta = json.loads((ROOT / "data/real_context_meta.json").read_text(encoding="utf-8"))
    cells = [v for d in rc.values() for v in d.values()]
    return {
        "sha256": hashes,
        "code_files_mentioning_real_context": consumers,
        "real_context_cells": len(cells),
        "real_context_zero_cells": sum(1 for v in cells if v == 0),
        "real_context_null_cells": sum(1 for v in cells if v is None),
        "meta_status": meta.get("status"),
        "meta_districts_source": meta.get("districts_source"),
        "meta_generated_at": meta.get("generated_at"),
        "districts_geojson_retrieved_at": json.loads(
            (ROOT / "data/astana_districts.geojson").read_text(encoding="utf-8"))["metadata"]["retrieved_at"],
    }


def e2_reproduce_failure_path():
    spec = importlib.util.spec_from_file_location("fetch_real_context", ROOT / "fetch_real_context.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # только определения; main() не вызывается
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        mod.ROOT = tmp
        mod.OUT_PATH = tmp / "data" / "real_context.json"
        mod.META_PATH = tmp / "data" / "real_context_meta.json"
        mod.POINTS_PATH = tmp / "data" / "real_context_points.geojson"
        rc_first = mod.handle_failure("K05: имитация недоступности Overpass", "osm")
        out = json.loads(mod.OUT_PATH.read_text(encoding="utf-8"))
        meta = json.loads(mod.META_PATH.read_text(encoding="utf-8"))
        cells = [v for d in out.values() for v in d.values()]
        # Повторный сбой при существующем файле: файл и meta остаются старыми,
        # сам сбой нигде не записывается.
        before = mod.META_PATH.read_bytes()
        rc_second = mod.handle_failure("K05: второй сбой", "osm")
        meta_unchanged = mod.META_PATH.read_bytes() == before
    return {
        "first_failure_return_code": rc_first,
        "cells_written": len(cells),
        "zero_cells_written": sum(1 for v in cells if v == 0),
        "null_cells_written": sum(1 for v in cells if v is None),
        "meta_status_written": meta["status"],
        "second_failure_return_code": rc_second,
        "second_failure_meta_unchanged": meta_unchanged,
    }


def e3_legacy_conversion():
    rc = json.loads((ROOT / "data/real_context.json").read_text(encoding="utf-8"))
    meta = json.loads((ROOT / "data/real_context_meta.json").read_text(encoding="utf-8"))
    obs = V.legacy_real_context_to_observations(rc, meta)
    dump(EX / "missing_real_context_astana.json", obs)
    statuses = {}
    for o in obs:
        statuses[o["value_status"]] = statuses.get(o["value_status"], 0) + 1
    rejected = sum(1 for o in obs if V.validate(o, AS_OF)[0])
    schools = [o for o in obs if o["indicator_id"] == "osm_poi_count.schools"]
    naive = sum(rc[d]["schools"] for d in rc)
    return {
        "observations": len(obs),
        "value_status_counts": statuses,
        "numeric_values": sum(1 for o in obs if o["value"] is not None),
        "rejected_by_validator": rejected,
        "naive_sum_schools_all_districts": naive,
        "contract_sum_schools_all_districts": V.aggregate_sum(schools),
    }


def e4_build_examples():
    raw_path = ROOT / "data/geo_sources/astana_districts_overpass.json"
    raw = json.loads(raw_path.read_text(encoding="utf-8"))
    city = json.loads((ROOT / "data/astana_districts.geojson").read_text(encoding="utf-8"))
    osm_base = raw["osm3s"]["timestamp_osm_base"]
    retrieved = raw["_provenance"]["retrieved_at"]
    boundary_version = f"osm@{osm_base}"

    # Принадлежность городу — по osm_id шести районов из data/astana_districts.geojson.
    # (Первая версия брала центр вершин внешних путей и ошибочно засчитала
    # Целиноградский район, окружающий город кольцом: 6 вместо 5. См. REPORT.md.)
    city_ids = {f["properties"]["osm_id"] for f in city["features"]}
    by_level = {}
    for el in raw["elements"]:
        if el.get("type") != "relation":
            continue
        lvl = el["tags"].get("admin_level")
        by_level.setdefault(lvl, []).append(
            {"id": el["id"], "name": el["tags"].get("name"), "inside_astana": el["id"] in city_ids})

    def count_inside(level):
        return sum(1 for r in by_level.get(level, []) if r["inside_astana"])

    base = {
        "schema_version": V.SCHEMA_VERSION,
        "city_id": "kz.astana",
        "geo_unit_id": "kz.astana",
        "period": osm_base[:10],
        "unit": "count",
        "kind": "derived",
        "source": {
            "source_id": "osm-overpass-admin-2026-09-23",
            "url": "https://overpass-api.de/api/interpreter",
            "path": rel(raw_path),
            "retrieved_at": retrieved,
            "sha256": sha256(raw_path),
            "license": "ODbL",
        },
        "data_version": f"astana_osm_admin@{osm_base}",
        "boundary_version": boundary_version,
        "derivation": ("отношения снимка Overpass, чей id совпадает с osm_id одного из 6 районов "
                       "data/astana_districts.geojson; запрос покрывает admin_level 5–9 "
                       "в рамке 50.90,71.0,51.5,72.0, которая целиком содержит город"),
    }
    lvl9 = count_inside("9")
    real_zero = dict(base, obs_id=f"astana.osm_admin_relations.level9@{osm_base[:10]}",
                     indicator_id="osm_admin_relations.admin_level_9",
                     value=lvl9, value_status="reported_zero" if lvl9 == 0 else "reported",
                     source=dict(base["source"], locator="elements[?tags.admin_level=='9']"),
                     note="Настоящий ноль в снимке OSM: отношений admin_level=9 нет во всём запросе, рамка которого содержит город. "
                          "Это ноль в источнике, а не юридическое утверждение.")
    lvl6 = count_inside("6")
    real_count = dict(base, obs_id=f"astana.osm_admin_relations.level6@{osm_base[:10]}",
                      indicator_id="osm_admin_relations.admin_level_6",
                      value=lvl6, value_status="reported_zero" if lvl6 == 0 else "reported",
                      source=dict(base["source"], locator="elements[?tags.admin_level=='6']"),
                      note="Число районов Астаны (отношений OSM) с admin_level=6.")
    stale = dict(real_count, obs_id=real_count["obs_id"] + "#stale-demo", max_age_days=7,
                 note="То же настоящее значение с демонстрационной политикой max_age_days=7: "
                      f"при проверке на {AS_OF} оно устарело. Политика 7 дней — параметр примера.")

    cd_path = ROOT / "data/city_data.json"
    cd = json.loads(cd_path.read_text(encoding="utf-8"))
    esil = next(d for d in cd["districts"] if d["id"] == "esil")
    synthetic = {
        "schema_version": V.SCHEMA_VERSION,
        "obs_id": "astana_hackathon.esil.T1",
        "city_id": "kz.astana",
        "geo_unit_id": "kz.astana.esil",
        "indicator_id": "hackathon.T1",
        "period": "2026",
        "value": esil["indicators"]["T1"],
        "unit": "score_0_100",
        "value_status": "reported",
        "kind": "synthetic",
        "source": {"source_id": "tz-city-data", "path": rel(cd_path), "sha256": sha256(cd_path),
                   "locator": "districts[id=esil].indicators.T1", "retrieved_at": None, "license": None},
        "data_version": f"astana_hackathon@sha256:{sha256(cd_path)[:12]}",
        "boundary_version": None,
        "note": "Учебный показатель датасета ТЗ (шкала 0–100). Не измерение Астаны.",
    }
    for name, obj in [("real_zero_osm_admin_level9.json", real_zero),
                      ("real_count_osm_admin_level6.json", real_count),
                      ("stale_osm_admin_level6.json", stale),
                      ("synthetic_city_data_esil_T1.json", synthetic)]:
        dump(EX / name, obj)
    return {"admin_level_relations_in_snapshot": {k: len(v) for k, v in sorted(by_level.items())},
            "inside_astana": {k: [r["name"] for r in v if r["inside_astana"]] for k, v in sorted(by_level.items())},
            "level9_inside": lvl9, "level6_inside": lvl6, "boundary_version": boundary_version}


def e5_validate_all():
    results = {}
    current = {"kz.astana": None}
    raw = json.loads((ROOT / "data/geo_sources/astana_districts_overpass.json").read_text(encoding="utf-8"))
    current["kz.astana"] = f"osm@{raw['osm3s']['timestamp_osm_base']}"
    for path in sorted(EX.rglob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        items = data if isinstance(data, list) else [data]
        summary = {"REJECT": 0, "WARN": 0, "OK": 0, "codes": {}}
        for o in items:
            errors, warnings = V.validate(o, AS_OF, current)
            summary["REJECT" if errors else "WARN" if warnings else "OK"] += 1
            for m in errors + warnings:
                code = m.split(":")[0]
                summary["codes"][code] = summary["codes"].get(code, 0) + 1
        results[str(path.relative_to(HERE))] = summary
    # Агрегат, смешивающий синтетику с измерением, должен быть отклонён.
    real = json.loads((EX / "real_count_osm_admin_level6.json").read_text(encoding="utf-8"))
    syn = json.loads((EX / "synthetic_city_data_esil_T1.json").read_text(encoding="utf-8"))
    try:
        V.aggregate_sum([real, dict(syn, unit="count")])
        mix = "accepted"
    except ValueError as exc:
        mix = f"rejected: {exc}"
    return {"per_file": results, "aggregate_real_plus_synthetic": mix,
            "current_boundary": current}


def main():
    out = {"as_of": AS_OF, "python": sys.version.split()[0]}
    out["E1_inventory"] = e1_inventory()
    out["E2_failure_path"] = e2_reproduce_failure_path()
    out["E3_legacy_conversion"] = e3_legacy_conversion()
    out["E4_examples"] = e4_build_examples()
    out["E5_validation"] = e5_validate_all()
    # data/ не должен измениться.
    out["data_unchanged"] = all(sha256(ROOT / f) == h for f, h in out["E1_inventory"]["sha256"].items())
    dump(HERE / "experiment_output.json", out)
    print(json.dumps(out, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
