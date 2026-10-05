#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
K05 round 4: семантика k05-obs-v1.2 = правила v1.1 (импорт из round-3-results/K05) + территория.

Добавлено к v1.1:
  * spatial_unit обязателен; число при type=unknown — ошибка;
  * bbox должен быть корректным и лежать в охвате заявленного города (CITY_MISMATCH);
  * агрегат: территории одного типа (SPATIAL_MIX), bbox не пересекаются (OVERLAP),
    записи без spatial_unit (v1.1 E02) не смешиваются с новыми (LEGACY_UNIT);
  * проверка объектов выгрузки до подсчёта: город, точка в bbox, повтор id,
    неизвестная группа, неизвестная confidence.
Только стандартная библиотека.
"""

from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1] / "round-3-results" / "K05"))
import k05r3_contract as C3  # noqa: E402

SCHEMA_VERSION = "k05-obs-v1.2"
# Охват полигонов городов (K10 round 2, Overture 2026-09-23.1) с запасом 0,05°.
# Нужен только для грубой проверки «bbox не из другого города» (города ~1000 км друг от друга).
CITY_ENVELOPE = {
    "kz.shymkent": (69.25, 42.05, 69.99, 42.53),
    "kz.astana": (71.16, 50.80, 71.84, 51.41),
}


def _to_v11(obs: dict) -> dict:
    o = {k: v for k, v in obs.items() if k != "spatial_unit"}
    su = obs.get("spatial_unit") or {}
    if su.get("type") == "bbox":
        # K12 BOUNDARY_MIX сравнивает слой границ (часть до r<id>@<версия>). У bbox такой части нет,
        # и у каждого квадрата своя boundary_version — без этой замены любые два квадрата были бы
        # «разными слоями». Идентичность и пересечение bbox проверяет v1.2 (OVERLAP), слой — data_version.
        o["boundary_version"] = f"bbox-layer:{obs.get('data_version')}"
    src = dict(o.get("source") or {})
    src.pop("query", None)
    o["source"] = src
    o["schema_version"] = C3.SCHEMA_VERSION
    return o


def _bbox_ok(bb):
    return (isinstance(bb, list) and len(bb) == 4 and all(isinstance(v, (int, float)) for v in bb)
            and -180 <= bb[0] < bb[2] <= 180 and -90 <= bb[1] < bb[3] <= 90)


def _inside(bb, env):
    return env[0] <= bb[0] and env[1] <= bb[1] and bb[2] <= env[2] and bb[3] <= env[3]


def validate(obs, as_of=None, boundary_ref=None, release_index=None):
    if not isinstance(obs, dict):
        return ["NOT_OBJECT"], []
    errors, warnings = [], []
    if obs.get("schema_version") != SCHEMA_VERSION:
        errors.append(f"SCHEMA_VERSION: ожидается {SCHEMA_VERSION}")
    su = obs.get("spatial_unit")
    e3, w3 = C3.validate(_to_v11(obs), as_of, boundary_ref, release_index)
    errors += e3
    warnings += w3
    if not isinstance(su, dict):
        errors.append("SPATIAL_UNIT: нет spatial_unit")
        return errors, warnings
    numeric = obs.get("value_status") in ("reported", "reported_zero")
    if su.get("type") == "unknown":
        (errors if numeric else warnings).append(
            "SPATIAL_UNKNOWN: территория неизвестна" + ("; число без территории не допускается" if numeric else ""))
    if su.get("type") == "bbox":
        bb = su.get("bbox")
        if not _bbox_ok(bb):
            errors.append(f"BBOX: некорректный bbox {bb!r}")
        else:
            env = CITY_ENVELOPE.get(obs.get("city_id"))
            if env and not _inside(bb, env):
                errors.append(f"CITY_MISMATCH: bbox {bb} вне охвата города {obs.get('city_id')}")
        if su.get("edges_inclusive") is None:
            warnings.append("BBOX_EDGES: не указано, включены ли объекты на границе bbox")
        over = su.get("overlaps_districts") or {}
        if len(over) > 1:
            warnings.append(f"CROSSES_DISTRICTS: bbox делит {len(over)} района; районные значения к нему неприменимы")
    return errors, warnings


def _boxes_overlap(a, b):
    return a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]


def aggregate_sum(observations: list[dict], **kwargs) -> dict:
    """Сумма v1.2: одинаковый тип территории, непересекающиеся bbox, затем правила v1.1.

    kwargs передаются в v1.1 (например, expected_units из K12 patch).
    """
    if any("spatial_unit" not in o for o in observations):
        raise ValueError("LEGACY_UNIT: запись без spatial_unit (например, v1.1/E02) не смешивается с v1.2")
    types = {o["spatial_unit"]["type"] for o in observations}
    if len(types) > 1:
        raise ValueError(f"SPATIAL_MIX: {sorted(types)}")
    if "unknown" in types:
        raise ValueError("SPATIAL_UNKNOWN: агрегат по неизвестной территории")
    if types == {"bbox"}:
        boxes = [o["spatial_unit"]["bbox"] for o in observations]
        for i, a in enumerate(boxes):
            for b in boxes[i + 1:]:
                if _boxes_overlap(a, b):
                    raise ValueError(f"OVERLAP: bbox {a} и {b} пересекаются")
    return C3.aggregate_sum([_to_v11(o) for o in observations], **kwargs)


def check_features(fc: dict, expected_city: str, bbox: list, groups) -> dict:
    """Проверка объектов K10 places_social.geojson до подсчёта.

    Ошибки: CITY_MISMATCH (город коллекции/объекта), OUTSIDE_BBOX, DUPLICATE_ID, GROUP_UNKNOWN.
    Предупреждения: CONFIDENCE_UNKNOWN, POSSIBLE_DUPLICATE, COLOCATED (правила v1.1).
    """
    errors, warnings = [], []
    if fc.get("city") != expected_city:
        errors.append({"code": "CITY_MISMATCH", "where": "collection", "got": fc.get("city"), "want": expected_city})
    if fc.get("bbox") is not None and list(fc["bbox"]) != list(bbox):
        errors.append({"code": "BBOX_MISMATCH", "got": fc.get("bbox"), "want": bbox})
    seen = set()
    rows = []
    for f in fc.get("features", []):
        p = f.get("properties") or {}
        oid = p.get("overture_id") or f.get("id")
        x, y = (f.get("geometry") or {}).get("coordinates", [None, None])[:2]
        if p.get("city") != expected_city:
            errors.append({"code": "CITY_MISMATCH", "where": "feature", "id": oid, "got": p.get("city")})
        if x is None or not (bbox[0] <= x <= bbox[2] and bbox[1] <= y <= bbox[3]):
            errors.append({"code": "OUTSIDE_BBOX", "id": oid, "lon": x, "lat": y})
        if oid in seen:
            errors.append({"code": "DUPLICATE_ID", "id": oid})
        seen.add(oid)
        if p.get("k10_group") not in groups:
            errors.append({"code": "GROUP_UNKNOWN", "id": oid, "group": p.get("k10_group")})
        if p.get("confidence") is None:
            warnings.append({"code": "CONFIDENCE_UNKNOWN", "id": oid})
        if x is not None:
            rows.append({"overture_id": oid, "lon": x, "lat": y, "name_primary": p.get("name_primary"),
                         "k10_group": p.get("k10_group"),
                         "address_freeform": [a.get("freeform") for a in (p.get("addresses") or [])][:1]})
    qa = C3.check_objects([r for r in rows if r["overture_id"] not in
                           {e["id"] for e in errors if e["code"] == "DUPLICATE_ID"}])
    warnings += qa["warnings"]
    return {"errors": errors, "warnings": warnings}
