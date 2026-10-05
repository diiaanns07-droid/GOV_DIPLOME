#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
K05: изолированный валидатор контракта наблюдения (k05-obs-v1).

Только стандартная библиотека. Не импортирует engine/, не читает .env,
не пишет в data/. Контракт описан в observation.schema.json и REPORT.md.

Главное правило: «нет данных» — это value=null и value_status=missing,
а не 0. Настоящий ноль — value=0 и value_status=reported_zero.

Запуск:
    python k05_validator.py examples/*.json --as-of 2026-10-05
    python k05_validator.py --from-legacy ../../../data/real_context.json \
        ../../../data/real_context_meta.json --as-of 2026-10-05
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import date, datetime, timezone
from pathlib import Path

SCHEMA_VERSION = "k05-obs-v1"

CITIES = {"kz.astana", "kz.shymkent"}
VALUE_STATUSES = {"reported", "reported_zero", "missing", "suppressed", "not_applicable"}
NUMERIC_STATUSES = {"reported", "reported_zero"}
NULL_STATUSES = VALUE_STATUSES - NUMERIC_STATUSES
KINDS = {"observed", "derived", "hypothesis", "synthetic"}
# Синтетика и гипотезы не являются измерениями города.
MEASUREMENT_KINDS = {"observed", "derived"}

REQUIRED = ("schema_version", "obs_id", "city_id", "geo_unit_id", "indicator_id",
            "period", "value", "unit", "value_status", "kind", "source", "data_version")

# YYYY | YYYY-MM | YYYY-Qn | YYYY-MM-DD | интервал A/B из этих форм
_P = r"\d{4}(?:-(?:0[1-9]|1[0-2])(?:-\d{2})?|-Q[1-4])?"
PERIOD_RE = re.compile(rf"^{_P}(?:/{_P})?$")


def _parse_ts(value):
    if value is None:
        return None
    s = str(value).replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(s)
    except ValueError:
        try:
            dt = datetime.combine(date.fromisoformat(s[:10]), datetime.min.time())
        except ValueError:
            return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def validate(obs: dict, as_of: str | None = None, current_boundary: dict | None = None):
    """Проверяет одно наблюдение.

    Возвращает (errors, warnings). errors — нарушение контракта (запись
    отклоняется). warnings — запись допустима, но показывать её нужно
    с пометкой (устарела, другая версия границ, не измерение).
    """
    errors, warnings = [], []
    if not isinstance(obs, dict):
        return ["NOT_OBJECT: наблюдение должно быть JSON-объектом"], []

    for key in REQUIRED:
        if key not in obs:
            errors.append(f"MISSING_FIELD: нет поля {key}")
    if errors:
        return errors, warnings

    if obs["schema_version"] != SCHEMA_VERSION:
        errors.append(f"SCHEMA_VERSION: ожидается {SCHEMA_VERSION}")

    city = obs["city_id"]
    if city not in CITIES:
        errors.append(f"CITY: неизвестный city_id {city!r}")
    unit_id = obs["geo_unit_id"]
    if not isinstance(unit_id, str) or not (unit_id == city or unit_id.startswith(f"{city}.")):
        errors.append(f"CITY_MIX: geo_unit_id {unit_id!r} не принадлежит {city!r}")

    period = obs["period"]
    if not isinstance(period, str) or not PERIOD_RE.match(period):
        errors.append(f"PERIOD: {period!r} не YYYY, YYYY-MM, YYYY-Qn, YYYY-MM-DD или A/B")

    if not isinstance(obs["unit"], str) or not obs["unit"].strip():
        errors.append("UNIT: единица обязательна, для счётчиков — 'count'")

    status, value, kind = obs["value_status"], obs["value"], obs["kind"]
    if status not in VALUE_STATUSES:
        errors.append(f"VALUE_STATUS: {status!r} не из {sorted(VALUE_STATUSES)}")
    if kind not in KINDS:
        errors.append(f"KIND: {kind!r} не из {sorted(KINDS)}")

    is_number = isinstance(value, (int, float)) and not isinstance(value, bool)
    if value is not None and not is_number:
        errors.append(f"VALUE_TYPE: value должно быть числом или null, получено {type(value).__name__}")
    if status in NULL_STATUSES and value is not None:
        # Ключевое правило: отсутствие данных не может нести число (в т.ч. 0).
        errors.append(f"FALSE_VALUE: value_status={status}, но value={value!r}; нужно null")
    if status in NUMERIC_STATUSES and value is None:
        errors.append(f"NULL_REPORTED: value_status={status}, но value=null")
    if status == "reported_zero" and is_number and value != 0:
        errors.append(f"ZERO_STATUS: reported_zero при value={value!r}")
    if status == "reported" and is_number and value == 0:
        errors.append("IMPLICIT_ZERO: 0 нужно явно пометить reported_zero")

    src = obs["source"]
    if not isinstance(src, dict):
        errors.append("SOURCE: source должен быть объектом")
        src = {}
    for key in ("source_id", "locator"):
        if not src.get(key):
            errors.append(f"SOURCE: нет source.{key}")
    if status in NUMERIC_STATUSES and kind in MEASUREMENT_KINDS and not src.get("retrieved_at"):
        errors.append("SOURCE: у измеренного числа нет source.retrieved_at")
    if kind == "derived" and not obs.get("derivation"):
        errors.append("DERIVATION: у derived нет поля derivation")

    dv = str(obs["data_version"])
    synthetic_ns = dv.startswith("synthetic:") or dv.startswith("astana_hackathon")
    if kind == "synthetic" and not synthetic_ns:
        errors.append("SYNTHETIC_NS: synthetic должен быть в data_version synthetic:* или astana_hackathon*")
    if kind in MEASUREMENT_KINDS and synthetic_ns:
        errors.append("SYNTHETIC_NS: observed/derived не может лежать в синтетической версии данных")
    if kind in {"synthetic", "hypothesis"} and status in NUMERIC_STATUSES:
        warnings.append(f"NOT_MEASUREMENT: kind={kind}; не показывать как факт о городе")

    # Давность считается при проверке, а не хранится как статус.
    if as_of and status in NUMERIC_STATUSES:
        max_age = obs.get("max_age_days")
        retrieved = _parse_ts(src.get("retrieved_at"))
        ref = _parse_ts(as_of)
        if max_age is not None and retrieved and ref:
            age = (ref - retrieved).days
            if age > max_age:
                warnings.append(f"STALE: возраст {age} дн. > max_age_days={max_age}")

    bv = obs.get("boundary_version")
    if current_boundary and city in current_boundary and bv and bv != current_boundary[city]:
        warnings.append(f"BOUNDARY_MISMATCH: {bv!r} ≠ текущей {current_boundary[city]!r}")

    return errors, warnings


def aggregate_sum(observations: list[dict]) -> dict:
    """Сумма без подмены null нулём.

    Если хотя бы одно слагаемое отсутствует, итог — null со статусом missing
    и указанием покрытия. Смешение городов, единиц и синтетики с измерениями
    запрещено.
    """
    if not observations:
        return {"value": None, "value_status": "missing", "coverage": "0/0"}
    cities = {o["city_id"] for o in observations}
    units = {o["unit"] for o in observations}
    kinds = {o["kind"] for o in observations}
    if len(cities) > 1:
        raise ValueError(f"CITY_MIX: агрегат по нескольким городам {sorted(cities)}")
    if len(units) > 1:
        raise ValueError(f"UNIT_MIX: {sorted(units)}")
    if kinds & MEASUREMENT_KINDS and kinds - MEASUREMENT_KINDS:
        raise ValueError(f"KIND_MIX: измерения смешаны с {sorted(kinds - MEASUREMENT_KINDS)}")
    known = [o for o in observations if o["value_status"] in NUMERIC_STATUSES]
    coverage = f"{len(known)}/{len(observations)}"
    if len(known) < len(observations):
        return {"value": None, "value_status": "missing", "coverage": coverage,
                "known_partial_sum": sum(o["value"] for o in known) if known else None}
    total = sum(o["value"] for o in known)
    return {"value": total, "value_status": "reported_zero" if total == 0 else "reported",
            "coverage": coverage}


def legacy_real_context_to_observations(rc: dict, meta: dict, rc_path: str = "data/real_context.json"):
    """Переводит текущий формат real_context.json + meta в наблюдения k05-obs-v1.

    meta.status != 'ok' → все ячейки missing/null, независимо от записанных нулей.
    meta.status == 'ok' → числа reported, нули reported_zero (ноль объектов
    в снимке OSM, а не доказанный ноль в городе).
    """
    ok = meta.get("status") == "ok"
    generated = meta.get("generated_at")
    period = (generated or "")[:10] or "0000"
    bsrc = meta.get("districts_source", "unknown")
    out = []
    for did in sorted(rc):
        for cat in sorted(rc[did]):
            legacy = rc[did][cat]
            if ok:
                value, status = legacy, ("reported_zero" if legacy == 0 else "reported")
            else:
                value, status = None, "missing"
            out.append({
                "schema_version": SCHEMA_VERSION,
                "obs_id": f"astana.real_context.{did}.{cat}@{period}",
                "city_id": "kz.astana",
                "geo_unit_id": f"kz.astana.{did}",
                "indicator_id": f"osm_poi_count.{cat}",
                "period": period,
                "value": value,
                "unit": "count",
                "value_status": status,
                "kind": "observed",
                "source": {
                    "source_id": "osm-overpass",
                    "url": "https://overpass-api.de/api/interpreter",
                    "retrieved_at": generated if ok else None,
                    "locator": f"{rc_path}#/{did}/{cat}",
                    "license": "ODbL",
                },
                "data_version": f"astana_real_context@{generated}",
                "boundary_version": bsrc,
                "note": (f"legacy={legacy!r}; meta.status={meta.get('status')}; "
                         f"error={meta.get('error')!r}" if not ok else
                         "ноль/число объектов в снимке OSM, не официальный реестр"),
            })
    return out


def _load(path: Path):
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    return data if isinstance(data, list) else [data]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Валидатор наблюдений k05-obs-v1")
    ap.add_argument("files", nargs="*", type=Path)
    ap.add_argument("--from-legacy", nargs=2, type=Path, metavar=("REAL_CONTEXT", "META"))
    ap.add_argument("--as-of", default=None, help="дата проверки давности, YYYY-MM-DD")
    ap.add_argument("--boundary", action="append", default=[],
                    help="текущая версия границ city_id=version (можно несколько)")
    args = ap.parse_args(argv)
    current = dict(b.split("=", 1) for b in args.boundary)

    items = []
    if args.from_legacy:
        rc = json.load(open(args.from_legacy[0], encoding="utf-8"))
        meta = json.load(open(args.from_legacy[1], encoding="utf-8"))
        for o in legacy_real_context_to_observations(rc, meta):
            items.append((str(args.from_legacy[0]), o))
    for p in args.files:
        items.extend((str(p), o) for o in _load(p))

    bad = 0
    for origin, obs in items:
        errors, warnings = validate(obs, args.as_of, current)
        state = "REJECT" if errors else ("WARN" if warnings else "OK")
        bad += bool(errors)
        oid = obs.get("obs_id", "?") if isinstance(obs, dict) else "?"
        print(f"{state:6} {origin} {oid}")
        for m in errors + warnings:
            print(f"       {m}")
    print(f"итого: {len(items)} записей, отклонено {bad}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
