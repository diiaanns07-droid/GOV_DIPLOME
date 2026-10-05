#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
K05 round 3: семантический валидатор k05-obs-v1.1, агрегат и проверка объектов.

Правила k05-obs-v1 (null ≠ 0, явный reported_zero, город, единица, synthetic
отдельно) берутся из research/next-round/K05/k05_validator.py без копирования.
Здесь добавлены: охват (coverage), метод, период unknown, причина отсутствия,
давность снимка, вытесненный выпуск, версия границы по территории, смешение
периодов/границ в агрегате и дубликаты объектов в выборке.
K12 round 4 (patch): конечность чисел, существующие даты периода, домен счётчика,
retrieved_at, вложенные территории и полнота географии в агрегате, проверка
набора (повтор obs_id) и строгая загрузка JSON.

Только стандартная библиотека. Структуру отдельно проверяет jsonschema
(schema/k05-obs-v1.1.schema.json) — см. tests/test_k05r3.py.
"""

from __future__ import annotations

import calendar
import json
import math
import re
import sys
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1] / "next-round" / "K05"))
import k05_validator as V1  # noqa: E402

SCHEMA_VERSION = "k05-obs-v1.1"
MISSING_REASONS = {None, "source_access_denied", "not_collected", "not_in_source",
                   "zero_in_partial_coverage", "suppressed_by_publisher"}
# Единицы-счётчики (целое ≥ 0): «count» из K12 и единицы, фактически используемые K05 r3/r4 и BUILD.
COUNT_UNITS = {"count", "records", "segments"}


def _finite(v) -> bool:
    """Конечное число: int (любой величины) или конечный float; bool и прочее — нет."""
    if isinstance(v, bool):
        return False
    if isinstance(v, int):
        return True
    return isinstance(v, float) and math.isfinite(v)


def _part_bounds(part: str):
    """(первый, последний день) одной части периода; ValueError для несуществующей даты."""
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", part):
        d = date.fromisoformat(part)
        return d, d
    if re.fullmatch(r"\d{4}-\d{2}", part):
        y, m = map(int, part.split("-"))
        return date(y, m, 1), date(y, m, calendar.monthrange(y, m)[1])
    if re.fullmatch(r"\d{4}-Q[1-4]", part):
        y, q = int(part[:4]), int(part[-1])
        return date(y, q * 3 - 2, 1), date(y, q * 3, calendar.monthrange(y, q * 3)[1])
    if re.fullmatch(r"\d{4}", part):
        return date(int(part), 1, 1), date(int(part), 12, 31)
    raise ValueError(part)


def period_bounds(period: str):
    """(начало, конец) периода; None для unknown; ValueError для несуществующей даты/формы."""
    if not period or period == "unknown":
        return None
    parts = period.split("/")
    if len(parts) > 2:
        raise ValueError(period)
    return _part_bounds(parts[0])[0], _part_bounds(parts[-1])[1]


def period_end(period: str):
    """Последний день периода или None для unknown/неразбираемого."""
    try:
        bounds = period_bounds(period)
    except ValueError:
        return None
    return bounds[1] if bounds else None


def validate(obs: dict, as_of: str | None = None, boundary_ref: dict | None = None,
             release_index: list | None = None):
    """(errors, warnings) для одного наблюдения k05-obs-v1.1.

    boundary_ref: {geo_unit_id: boundary_version или None (версия неизвестна)} — эталон,
    с которым сравнивается запись (например, слой продукта).
    release_index: список выпусков источника; если есть более новый, чем obs.release — SUPERSEDED.
    """
    if not isinstance(obs, dict):
        return ["NOT_OBJECT"], []
    errors, warnings = [], []
    for key in ("coverage", "method", "boundary_version"):
        if key not in obs:
            errors.append(f"MISSING_FIELD: нет поля {key}")
    if obs.get("schema_version") != SCHEMA_VERSION:
        errors.append(f"SCHEMA_VERSION: ожидается {SCHEMA_VERSION}")

    # Правила v1: подставляем версию v1, а unknown-период проверяем здесь.
    period = obs.get("period")
    v1_obs = dict(obs, schema_version=V1.SCHEMA_VERSION,
                  period="0000" if period == "unknown" else period)
    e1, w1 = V1.validate(v1_obs, as_of=None, current_boundary=None)
    errors += e1
    warnings += w1
    if errors:
        return errors, warnings

    status, value, kind = obs["value_status"], obs["value"], obs["kind"]
    numeric = status in V1.NUMERIC_STATUSES
    src, cov, method = obs["source"], obs["coverage"], obs["method"]

    if numeric and not _finite(value):
        errors.append("VALUE_NOT_FINITE: NaN/Infinity не является значением наблюдения")
    elif numeric and obs["unit"].strip() in COUNT_UNITS and (value < 0 or value != int(value)):
        errors.append(f"COUNT_DOMAIN: счётчик должен быть целым ≥ 0, получено {value!r}")
    if period != "unknown":
        try:
            start, finish = period_bounds(period)
            if start > finish:
                errors.append(f"PERIOD_REVERSED: начало {start} позже конца {finish}")
        except ValueError:
            errors.append(f"PERIOD_INVALID_DATE: {period!r} — несуществующая дата")
    retrieved = src.get("retrieved_at")
    if retrieved is not None and V1._parse_ts(retrieved) is None:
        errors.append(f"RETRIEVED_AT_INVALID: {retrieved!r} не дата/время ISO 8601")

    if period == "unknown":
        (warnings if not numeric else errors).append(
            "PERIOD_UNKNOWN: период неизвестен" + ("" if not numeric else "; число без периода не допускается"))

    if not (src.get("sha256") or src.get("url")):
        errors.append("SOURCE: нужен source.sha256 или source.url")

    reason = obs.get("missing_reason")
    if reason not in MISSING_REASONS:
        errors.append(f"MISSING_REASON: {reason!r}")
    if status == "missing" and reason is None:
        warnings.append("MISSING_REASON: не указано, почему значения нет (доступ, не собиралось, нет в источнике)")
    if numeric and reason is not None:
        errors.append("MISSING_REASON: у числа не может быть причины отсутствия")

    if not isinstance(cov, dict) or not isinstance(cov.get("complete"), bool):
        errors.append("COVERAGE: coverage.complete обязателен (true/false)")
    else:
        frac = cov.get("area_fraction")
        if cov["complete"] and frac is not None and frac < 1:
            errors.append(f"COVERAGE: complete=true при area_fraction={frac}")
        if not cov["complete"]:
            if status == "reported_zero":
                errors.append("ZERO_ON_PARTIAL: ноль при неполном охвате не доказывает отсутствие")
            elif numeric:
                warnings.append(f"PARTIAL_COVERAGE: значение — нижняя граница/выборка ({cov.get('selection')})")
    if not isinstance(method, dict) or not method.get("id") or not method.get("steps"):
        errors.append("METHOD: нужны method.id и method.steps")

    # Давность считается от конца периода (дата снимка), а не от времени скачивания.
    end = period_end(period)
    if as_of and numeric and obs.get("max_age_days") is not None and end:
        age = (date.fromisoformat(as_of[:10]) - end).days
        if age > obs["max_age_days"]:
            warnings.append(f"STALE: снимку {age} дн. > max_age_days={obs['max_age_days']}")
    rel = obs.get("release")
    if rel and release_index:
        newer = sorted(r for r in release_index if r > rel)
        if newer:
            warnings.append(f"SUPERSEDED: выпуск {rel} вытеснен {newer[-1]}")

    if boundary_ref is not None and obs["geo_unit_id"] in boundary_ref:
        ref, bv = boundary_ref[obs["geo_unit_id"]], obs.get("boundary_version")
        ref_rel, obs_rel = _relation(ref), _relation(bv)
        if ref_rel is None or obs_rel is None or ref_rel[0] != obs_rel[0]:
            warnings.append(f"BOUNDARY_UNVERIFIED: не сопоставить {bv!r} с эталоном {ref!r}")
        elif ref_rel[1] is None or obs_rel[1] is None:
            warnings.append(f"BOUNDARY_VERSION_UNKNOWN: relation {obs_rel[0]}, версия эталона или записи неизвестна")
        elif ref_rel[1] != obs_rel[1]:
            warnings.append(f"BOUNDARY_MISMATCH: relation {obs_rel[0]} @{obs_rel[1]} ≠ эталону @{ref_rel[1]}")
    return errors, warnings


def _relation(bv):
    """'...osm:r19733918@16' → ('19733918', '16'); '@unknown' → (id, None)."""
    m = re.search(r"r(\d+)@(\w+)", bv or "")
    if not m:
        return None
    return m.group(1), (None if m.group(2) == "unknown" else m.group(2))


def aggregate_sum(observations: list[dict], expected_units: list[str] | None = None) -> dict:
    """Сумма одного показателя по территориям одного города, периода и версии данных.

    null не превращается в 0; неполный охват любого слагаемого делает итог неполным.
    expected_units — полный список территорий, которые должна покрыть сумма (например,
    все районы города). Без него итог помечается geography_checked=false.
    """
    geo = {"geography_checked": expected_units is not None}
    if not observations:
        return {"value": None, "value_status": "missing", "coverage_complete": False, "n": "0/0", **geo}
    for key, code in (("city_id", "CITY_MIX"), ("period", "PERIOD_MIX"), ("unit", "UNIT_MIX"),
                      ("indicator_id", "INDICATOR_MIX"), ("data_version", "DATA_VERSION_MIX")):
        vals = {o[key] for o in observations}
        if len(vals) > 1:
            raise ValueError(f"{code}: {sorted(map(str, vals))}")
    if "unknown" in {o["period"] for o in observations}:
        raise ValueError("PERIOD_UNKNOWN: агрегат по неизвестному периоду")
    kinds = {o["kind"] for o in observations}
    if kinds & V1.MEASUREMENT_KINDS and kinds - V1.MEASUREMENT_KINDS:
        raise ValueError(f"KIND_MIX: {sorted(kinds)}")
    # boundary_version у каждой территории своя (…/osm:r<id>@<версия>); смешение — это разные
    # слои/выпуски границ, т.е. различие части до r<id>@<версия>.
    layers = {re.sub(r"r\d+@\w+$", "", o.get("boundary_version") or "") for o in observations}
    if len(layers) > 1:
        raise ValueError(f"BOUNDARY_MIX: слои границ {sorted(layers)}")
    units = [o["geo_unit_id"] for o in observations]
    if len(set(units)) != len(units):
        raise ValueError("DUPLICATE_UNIT: территория встречается дважды")
    for outer in set(units):
        nested = sorted(u for u in units if u.startswith(outer + "."))
        if nested:
            raise ValueError(f"NESTED_UNIT: {outer} вместе с вложенными {nested} — двойной счёт")
    if expected_units is not None:
        extra = sorted(set(units) - set(expected_units))
        if extra:
            raise ValueError(f"UNEXPECTED_UNIT: {extra} нет в expected_units")
        geo["units"] = f"{len(units)}/{len(set(expected_units))}"
        absent = sorted(set(expected_units) - set(units))
        if absent:
            geo["missing_units"] = absent
    known = [o for o in observations if o["value_status"] in V1.NUMERIC_STATUSES]
    not_finite = [o.get("obs_id") for o in known if not _finite(o["value"])]
    if not_finite:
        raise ValueError(f"VALUE_NOT_FINITE: {not_finite}")
    complete = len(known) == len(observations) and all(o["coverage"]["complete"] for o in observations)
    n = f"{len(known)}/{len(observations)}"
    if len(known) < len(observations) or "missing_units" in geo:
        return {"value": None, "value_status": "missing", "coverage_complete": False, "n": n,
                "known_partial_sum": sum(o["value"] for o in known) if known else None, **geo}
    total = sum(o["value"] for o in known)
    if total == 0 and not complete:
        # как у записи: ноль при неполном охвате не доказывает отсутствие
        return {"value": None, "value_status": "missing", "missing_reason": "zero_in_partial_coverage",
                "coverage_complete": False, "n": n, "known_partial_sum": 0, **geo}
    return {"value": total, "value_status": "reported_zero" if total == 0 else "reported",
            "coverage_complete": complete, "n": n, **geo}


def validate_dataset(observations: list[dict]):
    """(errors, warnings) по набору записей: то, чего не видит validate() одной записи.

    DUPLICATE_OBS_ID (ошибка): один obs_id с разным содержимым.
    DUPLICATE_RECORD (предупреждение): точный повтор записи.
    CONFLICTING_OBSERVATION (ошибка): разные obs_id для одной ячейки
      (город, территория, показатель, период, версия данных) с разными значениями.
    """
    errors, warnings = [], []
    by_id, by_cell = {}, {}
    for i, o in enumerate(observations):
        oid = o.get("obs_id")
        if oid in by_id:
            if by_id[oid] == o:
                warnings.append(f"DUPLICATE_RECORD: {oid!r} повторён без изменений (позиция {i})")
            else:
                errors.append(f"DUPLICATE_OBS_ID: {oid!r} с разным содержимым (позиция {i})")
            continue
        by_id[oid] = o
        cell = tuple(o.get(k) for k in ("city_id", "geo_unit_id", "indicator_id", "period", "data_version"))
        prev = by_cell.setdefault(cell, o)
        if prev is not o and (prev.get("value"), prev.get("value_status")) != (o.get("value"), o.get("value_status")):
            errors.append(f"CONFLICTING_OBSERVATION: {prev.get('obs_id')!r} и {oid!r} расходятся для {cell}")
    return errors, warnings


def loads_strict(text: str):
    """json.loads без NaN/Infinity, без переполнения до inf (1e999) и без повтора ключей."""
    def no_constant(name):
        raise ValueError(f"JSON_NONFINITE: токен {name}")

    def finite_float(token):
        v = float(token)
        if not math.isfinite(v):
            raise ValueError(f"JSON_NONFINITE: {token} переполняется до {v}")
        return v

    def unique_keys(pairs):
        out = {}
        for k, v in pairs:
            if k in out:
                raise ValueError(f"JSON_DUPLICATE_KEY: {k!r}")
            out[k] = v
        return out

    return json.loads(text, parse_constant=no_constant, parse_float=finite_float, object_pairs_hook=unique_keys)


def _norm(s):
    return re.sub(r"[^\w]+", " ", (s or "").lower()).strip()


def _dist_m(a, b):
    k = math.cos(math.radians((a["lat"] + b["lat"]) / 2))
    return math.hypot((a["lon"] - b["lon"]) * 111320 * k, (a["lat"] - b["lat"]) * 110540)


def _house_number(addr):
    nums = re.findall(r"\b(\d+[a-zа-яәіңғүұқөһ]?)\b", _norm(addr))
    return nums[-1] if nums else None


def check_objects(rows: list[dict], id_key="overture_id") -> dict:
    """Проверка объектов выборки до подсчёта.

    DUPLICATE_ID (ошибка): один id дважды.
    POSSIBLE_DUPLICATE (предупреждение, нужна ручная проверка):
      a) одинаковый нормализованный адрес и < 100 м;
      b) одинаковое имя и < 100 м;
      c) одна группа, один номер дома и < 50 м (ловит запись на двух языках).
    COLOCATED (предупреждение): ≥3 объектов с одинаковыми координатами — вероятная
      координата-заглушка, привязка к району ненадёжна.
    """
    errors, warnings = [], []
    seen = {}
    for r in rows:
        rid = r.get(id_key)
        if rid in seen:
            errors.append({"code": "DUPLICATE_ID", "id": rid})
        seen[rid] = r
    for i, a in enumerate(rows):
        addr_a = _norm((a.get("address_freeform") or [None])[0])
        for b in rows[i + 1:]:
            d = _dist_m(a, b)
            if d >= 100:
                continue
            addr_b = _norm((b.get("address_freeform") or [None])[0])
            why = None
            if addr_a and addr_a == addr_b:
                why = "same_address"
            elif _norm(a.get("name_primary")) == _norm(b.get("name_primary")):
                why = "same_name"
            elif (d < 50 and a.get("k10_group") == b.get("k10_group")
                  and _house_number(addr_a) and _house_number(addr_a) == _house_number(addr_b)):
                why = "same_group_same_house_number"
            if why:
                warnings.append({"code": "POSSIBLE_DUPLICATE", "rule": why, "distance_m": round(d, 1),
                                 "a": {"id": a.get(id_key), "name": a.get("name_primary"), "group": a.get("k10_group")},
                                 "b": {"id": b.get(id_key), "name": b.get("name_primary"), "group": b.get("k10_group")}})
    by_xy = {}
    for r in rows:
        by_xy.setdefault((round(r["lon"], 5), round(r["lat"], 5)), []).append(r)
    for xy, group in by_xy.items():
        if len(group) >= 3:
            warnings.append({"code": "COLOCATED", "lon": xy[0], "lat": xy[1], "n": len(group),
                             "names": [g.get("name_primary") for g in group]})
    return {"errors": errors, "warnings": warnings}
