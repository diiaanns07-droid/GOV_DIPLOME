"""K12 round 3: isolated importer of monthly building electricity readings + data-quality report.

Python standard library only. NOT wired into the product (STUPITS / main site).

One input row = one building x one billing period. Every row gets a status and its reasons;
nothing is dropped silently. EUI is computed only over the SAME complete analysis window for
every building; partial periods are never annualised or ranked against full years.
A high EUI marks a CANDIDATE for an energy audit, not proven savings or a fault.

Usage:
    python k12_energy_import.py INPUT.csv --window 2014-12-01:2015-11-30 --out OUT_DIR
"""
import argparse
import csv
import datetime as dt
import json
import math
import random
import sys
from collections import Counter, defaultdict
from pathlib import Path

SCHEMA_VERSION = "k12-energy-monthly-v1"
FIELDS = [
    "building_id", "city_id", "country", "object_type", "period_start", "period_end",
    "electricity_kwh", "unit", "value_status", "reading_type", "coverage_share",
    "floor_area_m2", "area_source", "kind", "source_id", "source_locator",
    "measurement_terms", "note",
]
REQUIRED = ["building_id", "city_id", "country", "object_type", "period_start", "period_end",
            "unit", "value_status", "reading_type", "kind", "source_id", "measurement_terms"]
KZ_CITIES = {"kz.shymkent", "kz.astana"}
VALUE_STATUS = {"reported", "reported_zero", "missing"}
READING_TYPES = {"actual", "estimated", "norm", "unknown"}
AREA_SOURCES = {"techpassport", "energy_passport", "operator_declared",
                "osm_footprint_x_floors", "dataset_metadata", "unknown"}
STRONG_AREA_SOURCES = {"techpassport", "energy_passport"}
KINDS = {"observed", "derived", "synthetic"}  # a meter reading cannot be a "hypothesis"
UNIT_FACTORS = {"kwh": 1.0, "квт·ч": 1.0, "квтч": 1.0, "квт.ч": 1.0,
                "mwh": 1000.0, "мвт·ч": 1000.0, "мвтч": 1000.0, "тыс.квт·ч": 1000.0}
NOT_ELECTRIC_ENERGY = {"kw", "квт", "gcal", "гкал", "m3", "м3", "м³", "gj", "гдж"}
LOW_ROW_COVERAGE = 0.8

# code -> (severity, Russian explanation). reject = row unusable; flag = row kept with a warning.
REASONS = {
    "REQUIRED_EMPTY": ("reject", "пусто обязательное поле"),
    "CITY_INVALID": ("reject", "city_id не из разрешённого списка (для KZ — kz.shymkent или kz.astana)"),
    "CITY_COUNTRY_MISMATCH": ("reject", "префикс city_id не совпадает с country"),
    "PERIOD_INVALID": ("reject", "дата не в формате YYYY-MM-DD"),
    "PERIOD_END_BEFORE_START": ("reject", "period_end раньше period_start"),
    "UNIT_NOT_ELECTRIC_ENERGY": ("reject", "единица не энергия электричества (кВт — мощность, Гкал/м³ — другой ресурс)"),
    "UNIT_UNKNOWN": ("reject", "неизвестная единица"),
    "UNIT_CONVERTED": ("flag", "значение переведено в kWh из MWh / тыс. кВт·ч"),
    "VALUE_NOT_NUMBER": ("reject", "electricity_kwh не число"),
    "VALUE_NEGATIVE": ("reject", "отрицательное потребление"),
    "DECIMAL_COMMA": ("flag", "десятичная запятая прочитана как точка"),
    "VALUE_STATUS_INVALID": ("reject", "value_status не reported / reported_zero / missing"),
    "VALUE_EMPTY_BUT_REPORTED": ("reject", "значение пусто, а value_status=reported"),
    "ZERO_NOT_CONFIRMED": ("reject", "0 без value_status=reported_zero: неясно, ноль это или нет данных"),
    "VALUE_STATUS_CONFLICT": ("reject", "есть значение, но value_status говорит missing/reported_zero"),
    "ZERO_REPORTED": ("flag", "подтверждённый ноль за период — проверить причину (закрытие, отключение)"),
    "READING_TYPE_INVALID": ("reject", "reading_type не actual / estimated / norm / unknown"),
    "COVERAGE_INVALID": ("reject", "coverage_share вне [0, 1] или не число"),
    "COVERAGE_UNKNOWN": ("flag", "покрытие периода учётом неизвестно"),
    "COVERAGE_LOW": ("flag", f"покрытие периода учётом < {LOW_ROW_COVERAGE}"),
    "AREA_NOT_NUMBER": ("reject", "floor_area_m2 не число"),
    "AREA_SOURCE_INVALID": ("reject", "area_source не из списка"),
    "KIND_INVALID": ("reject", "kind не observed / derived / synthetic"),
    "DUPLICATE_EXACT": ("reject", "точный дубликат строки (оставлена первая)"),
    "DUPLICATE_CONFLICT": ("reject", "тот же здание+период с разными значениями — отклонены все"),
    "PERIOD_OVERLAP": ("reject", "период пересекается с другим периодом того же здания — риск двойного учёта"),
}
# building-level reasons for not ranking, and building-level flags
BUILDING_REASONS = {
    "NO_ACCEPTED_ROWS": "нет принятых строк",
    "CITY_INCONSISTENT": "у здания разные city_id",
    "OBJECT_TYPE_INCONSISTENT": "у здания разные object_type",
    "KIND_MIXED": "смешаны synthetic и реальные строки",
    "AREA_UNKNOWN": "площадь неизвестна",
    "AREA_NOT_POSITIVE": "площадь 0 или отрицательная",
    "AREA_INCONSISTENT": "у здания разные значения площади",
    "INCOMPLETE_WINDOW": "окно анализа покрыто не полностью — EUI за неполный период не сравнивается с годовым",
    "NORM_ACCRUAL_IN_WINDOW": "в окне есть начисления по нормативу — это не измерение",
    "METERING_COVERAGE_BELOW_MIN": "взвешенное покрытие учётом ниже порога",
}
EXCLUSION_REASONS = {
    "PERIOD_CROSSES_WINDOW": "период выходит за границу окна анализа — не делится пропорционально",
    "ROW_COVERAGE_BELOW_MIN": "покрытие строки ниже заданного порога политики",
}
BUILDING_FLAGS = {
    "ESTIMATED_IN_WINDOW": "есть расчётные (estimated) показания",
    "READING_TYPE_UNKNOWN_IN_WINDOW": "тип показаний неизвестен",
    "ZERO_REPORTED_IN_WINDOW": "есть подтверждённые нулевые периоды",
    "COVERAGE_UNKNOWN": "покрытие учётом неизвестно хотя бы для части окна",
    "LOW_ROW_COVERAGE": f"есть периоды с покрытием < {LOW_ROW_COVERAGE}",
    "AREA_SOURCE_UNKNOWN": "источник площади неизвестен",
    "AREA_SOURCE_WEAK": "площадь не из техпаспорта/энергопаспорта",
    "UNIT_CONVERTED": "часть значений переведена из MWh",
}


def parse_date(s):
    try:
        return dt.date.fromisoformat(s.strip())
    except (ValueError, AttributeError):
        return None


def parse_number(s):
    """Returns (value or None, ok, used_decimal_comma). Empty string -> (None, True, False)."""
    s = (s or "").strip().replace(" ", "").replace(" ", "")
    if s == "":
        return None, True, False
    comma = "," in s
    if comma and "." in s:
        return None, False, False  # ambiguous thousands/decimal separators
    try:
        v = float(s.replace(",", "."))
    except ValueError:
        return None, False, False
    if math.isnan(v) or math.isinf(v):
        return None, False, False
    return v, True, comma


def norm_unit(u):
    return (u or "").strip().lower().replace(" ", "").replace("⋅", "·").replace("*", "·")


def city_ok(city_id, country):
    cc = (country or "").strip().lower()
    if not city_id.startswith(cc + "."):
        return "CITY_COUNTRY_MISMATCH"
    if cc == "kz" and city_id not in KZ_CITIES:
        return "CITY_INVALID"
    return None


def validate_row(raw, line_no):
    r = {k: (raw.get(k) or "").strip() for k in FIELDS}
    reasons, flags = [], []
    empty = [k for k in REQUIRED if r[k] == ""]
    if empty:
        reasons.append("REQUIRED_EMPTY")
    out = {"line": line_no, "empty_required": empty, "building_id": r["building_id"], "city_id": r["city_id"],
           "country": r["country"].upper(), "object_type": r["object_type"],
           "period_start": r["period_start"], "period_end": r["period_end"],
           "reading_type": r["reading_type"], "value_status": r["value_status"], "kind": r["kind"],
           "area_source": r["area_source"] or "unknown", "source_id": r["source_id"],
           "measurement_terms": r["measurement_terms"], "kwh": None, "coverage": None, "area": None}
    if r["city_id"] and r["country"]:
        c = city_ok(r["city_id"], r["country"])
        if c:
            reasons.append(c)
    start, end = parse_date(r["period_start"]), parse_date(r["period_end"])
    if r["period_start"] and r["period_end"]:
        if start is None or end is None:
            reasons.append("PERIOD_INVALID")
        elif end < start:
            reasons.append("PERIOD_END_BEFORE_START")
    out["start"], out["end"] = start, end

    factor = None
    u = norm_unit(r["unit"])
    if u:
        if u in UNIT_FACTORS:
            factor = UNIT_FACTORS[u]
            if factor != 1.0:
                flags.append("UNIT_CONVERTED")
        elif u in NOT_ELECTRIC_ENERGY:
            reasons.append("UNIT_NOT_ELECTRIC_ENERGY")
        else:
            reasons.append("UNIT_UNKNOWN")

    v, ok, comma = parse_number(r["electricity_kwh"])
    if not ok:
        reasons.append("VALUE_NOT_NUMBER")
    if comma:
        flags.append("DECIMAL_COMMA")
    vs = r["value_status"]
    if vs and vs not in VALUE_STATUS:
        reasons.append("VALUE_STATUS_INVALID")
    elif ok and vs:
        if v is None and vs != "missing":
            reasons.append("VALUE_EMPTY_BUT_REPORTED")
        elif v is not None and vs == "missing":
            reasons.append("VALUE_STATUS_CONFLICT")
        elif v is not None and v < 0:
            reasons.append("VALUE_NEGATIVE")
        elif v == 0 and vs == "reported":
            reasons.append("ZERO_NOT_CONFIRMED")
        elif v is not None and v > 0 and vs == "reported_zero":
            reasons.append("VALUE_STATUS_CONFLICT")
        elif v == 0 and vs == "reported_zero":
            flags.append("ZERO_REPORTED")
    if v is not None and factor is not None:
        out["kwh"] = v * factor

    if r["reading_type"] and r["reading_type"] not in READING_TYPES:
        reasons.append("READING_TYPE_INVALID")
    cov, ok, _ = parse_number(r["coverage_share"])
    if not ok or (cov is not None and not 0.0 <= cov <= 1.0):
        reasons.append("COVERAGE_INVALID")
    elif cov is None:
        flags.append("COVERAGE_UNKNOWN")
    else:
        out["coverage"] = cov
        if cov < LOW_ROW_COVERAGE:
            flags.append("COVERAGE_LOW")
    area, ok, _ = parse_number(r["floor_area_m2"])
    if not ok:
        reasons.append("AREA_NOT_NUMBER")
    out["area"] = area
    if out["area_source"] not in AREA_SOURCES:
        reasons.append("AREA_SOURCE_INVALID")
    if r["kind"] and r["kind"] not in KINDS:
        reasons.append("KIND_INVALID")
    out["reasons"], out["flags"] = sorted(set(reasons)), sorted(set(flags))
    return out


def _signature(x):
    return (x["kwh"], x["value_status"], x["reading_type"], x["coverage"], x["area"])


def cross_row_checks(rows):
    """Duplicates and overlapping periods among rows that passed row-level checks."""
    alive = [x for x in rows if not x["reasons"]]
    by_key = defaultdict(list)
    for x in alive:
        by_key[(x["building_id"], x["start"], x["end"])].append(x)
    for group in by_key.values():
        if len(group) < 2:
            continue
        if len({_signature(x) for x in group}) == 1:
            for x in group[1:]:
                x["reasons"].append("DUPLICATE_EXACT")
        else:
            for x in group:
                x["reasons"].append("DUPLICATE_CONFLICT")
    by_building = defaultdict(list)
    for x in rows:
        if not x["reasons"]:
            by_building[x["building_id"]].append(x)
    for group in by_building.values():
        group.sort(key=lambda x: (x["start"], x["end"]))
        latest = group[0]  # row with the latest end so far: catches a long period over several short ones
        for x in group[1:]:
            if x["start"] <= latest["end"]:
                for y in (latest, x):
                    if "PERIOD_OVERLAP" not in y["reasons"]:
                        y["reasons"].append("PERIOD_OVERLAP")
            if x["end"] > latest["end"]:
                latest = x
    for x in rows:
        x["status"] = "rejected" if x["reasons"] else "accepted"
    return rows


def aggregate(rows, window, min_building_coverage=0.9, min_row_coverage=None):
    """Per-building totals over one analysis window. Returns (buildings, row_exclusions)."""
    w0, w1 = window
    window_days = (w1 - w0).days + 1
    by_b = defaultdict(list)
    for x in rows:
        if x["building_id"]:
            by_b[x["building_id"]].append(x)
    buildings, exclusions = [], []
    for bid, allrows in sorted(by_b.items()):
        acc = [x for x in allrows if x["status"] == "accepted"]
        b = {"building_id": bid, "rows_total": len(allrows), "rows_accepted": len(acc),
             "window_start": w0.isoformat(), "window_end": w1.isoformat(), "window_days": window_days,
             "reasons_not_ranked": [], "flags": [], "kwh_window": None, "eui_window": None,
             "eui_is_annual": False}
        if not acc:
            b["reasons_not_ranked"] = ["NO_ACCEPTED_ROWS"]
            b["city_id"] = allrows[0]["city_id"]
            buildings.append(b)
            continue
        cities = {x["city_id"] for x in acc}
        types = {x["object_type"] for x in acc}
        classes = {"synthetic" if x["kind"] == "synthetic" else "real" for x in acc}
        b["city_id"], b["object_type"] = "+".join(sorted(cities)), "+".join(sorted(types))
        b["country"] = acc[0]["country"]
        b["data_class"] = sorted(classes)[0]
        b["kinds"] = sorted({x["kind"] for x in acc})
        b["measurement_terms"] = sorted({x["measurement_terms"] for x in acc})
        if len(cities) > 1:
            b["reasons_not_ranked"].append("CITY_INCONSISTENT")
        if len(types) > 1:
            b["reasons_not_ranked"].append("OBJECT_TYPE_INCONSISTENT")
        if len(classes) > 1:
            b["reasons_not_ranked"].append("KIND_MIXED")
        areas = {x["area"] for x in acc}
        b["area_source"] = sorted({x["area_source"] for x in acc})
        if areas == {None}:
            b["reasons_not_ranked"].append("AREA_UNKNOWN")
        elif len(areas) > 1:
            b["reasons_not_ranked"].append("AREA_INCONSISTENT")
        elif next(iter(areas)) <= 0:
            b["reasons_not_ranked"].append("AREA_NOT_POSITIVE")
        b["floor_area_m2"] = next(iter(areas)) if len(areas) == 1 else None
        if "unknown" in b["area_source"]:
            b["flags"].append("AREA_SOURCE_UNKNOWN")
        elif not set(b["area_source"]) <= STRONG_AREA_SOURCES:
            b["flags"].append("AREA_SOURCE_WEAK")

        used = []
        for x in acc:
            if x["end"] < w0 or x["start"] > w1:
                continue  # outside the window: neither used nor a problem
            if x["start"] < w0 or x["end"] > w1:
                exclusions.append({"line": x["line"], "building_id": bid, "reason": "PERIOD_CROSSES_WINDOW"})
                continue
            if (min_row_coverage is not None and x["coverage"] is not None
                    and x["coverage"] < min_row_coverage):
                exclusions.append({"line": x["line"], "building_id": bid, "reason": "ROW_COVERAGE_BELOW_MIN"})
                continue
            used.append(x)
        with_value = [x for x in used if x["value_status"] in ("reported", "reported_zero")]
        covered = sum((x["end"] - x["start"]).days + 1 for x in with_value)
        b["days_with_value"] = covered
        b["rows_used"] = len(with_value)
        b["rows_missing_in_window"] = sum(1 for x in used if x["value_status"] == "missing")
        known = [x for x in with_value if x["coverage"] is not None]
        kd = sum((x["end"] - x["start"]).days + 1 for x in known)
        b["metering_coverage_weighted"] = (
            round(sum(((x["end"] - x["start"]).days + 1) * x["coverage"] for x in known) / kd, 4)
            if kd else None)
        if covered < window_days:
            b["reasons_not_ranked"].append("INCOMPLETE_WINDOW")
        if any(x["reading_type"] == "norm" for x in with_value):
            b["reasons_not_ranked"].append("NORM_ACCRUAL_IN_WINDOW")
        if b["metering_coverage_weighted"] is not None and b["metering_coverage_weighted"] < min_building_coverage:
            b["reasons_not_ranked"].append("METERING_COVERAGE_BELOW_MIN")
        if any(x["reading_type"] == "estimated" for x in with_value):
            b["flags"].append("ESTIMATED_IN_WINDOW")
        if any(x["reading_type"] == "unknown" for x in with_value):
            b["flags"].append("READING_TYPE_UNKNOWN_IN_WINDOW")
        if any(x["value_status"] == "reported_zero" for x in with_value):
            b["flags"].append("ZERO_REPORTED_IN_WINDOW")
        if len(known) < len(with_value):
            b["flags"].append("COVERAGE_UNKNOWN")
        if any(x["coverage"] is not None and x["coverage"] < LOW_ROW_COVERAGE for x in with_value):
            b["flags"].append("LOW_ROW_COVERAGE")
        if any("UNIT_CONVERTED" in x["flags"] for x in with_value):
            b["flags"].append("UNIT_CONVERTED")
        b["kwh_window"] = round(sum(x["kwh"] for x in with_value), 4)
        # same totals with each period scaled by 1/coverage: an ESTIMATE that assumes uniform
        # consumption in unmetered hours (sensitivity only, never the default)
        b["kwh_window_coverage_adjusted"] = round(sum(
            x["kwh"] / x["coverage"] if x["coverage"] else x["kwh"] for x in with_value), 4)
        if not b["reasons_not_ranked"]:
            b["eui_window"] = round(b["kwh_window"] / b["floor_area_m2"], 4)
            b["eui_is_annual"] = window_days in (365, 366)
        b["confidence"] = confidence(b)
        buildings.append(b)
    return buildings, exclusions


def confidence(b):
    if b["reasons_not_ranked"]:
        return None
    f = set(b["flags"])
    if f & {"ESTIMATED_IN_WINDOW", "READING_TYPE_UNKNOWN_IN_WINDOW", "COVERAGE_UNKNOWN", "AREA_SOURCE_UNKNOWN"}:
        return "low"
    if (b["metering_coverage_weighted"] or 0) >= 0.95 and "AREA_SOURCE_WEAK" not in f:
        return "high"
    return "medium"


def group_key(b):
    return (b["city_id"], b.get("object_type"), b.get("data_class"))


def top_set(items, key, n):
    return {b["building_id"] for b in sorted(items, key=lambda b: (-key(b), b["building_id"]))[:n]}


def rank(buildings, top_share=0.2, sigmas=(0.1, 0.2, 0.3), n_sim=1000, seed=12):
    """Rank rankable buildings inside each (city, object_type, data_class) group."""
    groups = defaultdict(list)
    for b in buildings:
        if b["eui_window"] is not None:
            groups[group_key(b)].append(b)
    out = []
    for key in sorted(groups, key=lambda k: tuple(str(x) for x in k)):
        g = groups[key]
        n = max(1, round(top_share * len(g)))
        ordered = sorted(g, key=lambda b: (-b["eui_window"], b["building_id"]))
        base = {b["building_id"] for b in ordered[:n]}
        rng = random.Random(seed)
        mc, p_top = {}, {}
        for sig in sigmas:
            hits, overlaps = Counter(), []
            for _ in range(n_sim):
                noisy = {b["building_id"]: b["kwh_window"] / (b["floor_area_m2"] * math.exp(rng.gauss(0, sig)))
                         for b in g}
                s = set(sorted(noisy, key=lambda i: (-noisy[i], i))[:n])
                overlaps.append(len(s & base) / n)
                hits.update(s)
            overlaps.sort()
            mc[f"sigma_log_{sig}"] = {"mean_overlap": round(sum(overlaps) / n_sim, 3),
                                      "p10_overlap": round(overlaps[int(0.1 * n_sim)], 3)}
            if abs(sig - 0.2) < 1e-9:
                p_top = {i: hits[i] / n_sim for i in base | set(hits)}
        adj = top_set(g, lambda b: b["kwh_window_coverage_adjusted"] / b["floor_area_m2"], n)
        rows = []
        for i, b in enumerate(ordered, 1):
            p = round(p_top.get(b["building_id"], 0.0), 3) if p_top else None
            band = None if p is None else ("stable_in_top" if p >= 0.9 else "outside" if p <= 0.1 else "boundary")
            rows.append({"rank": i, "building_id": b["building_id"], "eui_window": b["eui_window"],
                         "eui_is_annual": b["eui_is_annual"], "in_top_n": b["building_id"] in base,
                         "p_top_sigma_0_2": p, "band": band, "confidence": b["confidence"],
                         "flags": b["flags"], "floor_area_m2": b["floor_area_m2"],
                         "metering_coverage_weighted": b["metering_coverage_weighted"]})
        out.append({"city_id": key[0], "object_type": key[1], "data_class": key[2], "n": len(g),
                    "top_n": n, "ranking": rows, "area_error_mc": mc,
                    "coverage_adjusted_top_overlap": round(len(base & adj) / n, 3),
                    "coverage_adjusted_entering": sorted(adj - base),
                    "coverage_adjusted_leaving": sorted(base - adj)})
    return out


def read_csv(path):
    text = Path(path).read_text(encoding="utf-8-sig")
    first = text.splitlines()[0] if text else ""
    delim = ";" if first.count(";") > first.count(",") else ","
    reader = csv.DictReader(text.splitlines(), delimiter=delim)
    header = reader.fieldnames or []
    missing = [f for f in FIELDS if f not in header]
    extra = [f for f in header if f not in FIELDS]
    return list(reader), missing, extra, delim


def run(path, window, top_share=0.2, min_building_coverage=0.9, min_row_coverage=None,
        sensitivity_min_row_coverage=LOW_ROW_COVERAGE, n_sim=1000, seed=12):
    raw, missing, extra, delim = read_csv(path)
    if missing:
        return {"schema_version": SCHEMA_VERSION, "fatal": "SCHEMA_MISSING_COLUMNS",
                "missing_columns": missing}
    rows = cross_row_checks([validate_row(r, i + 2) for i, r in enumerate(raw)])
    buildings, exclusions = aggregate(rows, window, min_building_coverage, min_row_coverage)
    ranking = rank(buildings, top_share, n_sim=n_sim, seed=seed)
    strict_b, _ = aggregate(rows, window, min_building_coverage, sensitivity_min_row_coverage)
    strict_ranked = {b["building_id"] for b in strict_b if b["eui_window"] is not None}
    base_ranked = {b["building_id"] for b in buildings if b["eui_window"] is not None}
    result = {
        "schema_version": SCHEMA_VERSION, "input": str(path), "delimiter": delim, "extra_columns": extra,
        "window": [window[0].isoformat(), window[1].isoformat()],
        "policy": {"top_share": top_share, "min_building_coverage": min_building_coverage,
                   "min_row_coverage": min_row_coverage, "n_sim": n_sim, "seed": seed},
        "rows_total": len(rows),
        "rows_accepted": sum(x["status"] == "accepted" for x in rows),
        "rows_rejected": sum(x["status"] == "rejected" for x in rows),
        "row_reason_counts": dict(sorted(Counter(c for x in rows for c in x["reasons"]).items())),
        "row_flag_counts": dict(sorted(Counter(c for x in rows for c in x["flags"]).items())),
        "row_exclusion_counts": dict(sorted(Counter(e["reason"] for e in exclusions).items())),
        "buildings_total": len(buildings),
        "buildings_ranked": len(base_ranked),
        "building_reason_counts": dict(sorted(Counter(c for b in buildings for c in b["reasons_not_ranked"]).items())),
        "building_flag_counts": dict(sorted(Counter(c for b in buildings for c in b["flags"]).items())),
        "data_classes": dict(Counter(b.get("data_class", "unknown") for b in buildings)),
        "countries": sorted({x["country"] for x in rows if x["country"]}),
        "measurement_terms": sorted({x["measurement_terms"] for x in rows if x["measurement_terms"]}),
        "sensitivity_strict_row_coverage": {
            "min_row_coverage": sensitivity_min_row_coverage,
            "buildings_ranked": len(strict_ranked),
            "dropped_from_ranking": sorted(base_ranked - strict_ranked)},
        "groups": ranking,
    }
    return result, rows, buildings, exclusions


def _fmt(v, nd=1):
    return "—" if v is None else (f"{v:.{nd}f}" if isinstance(v, float) else str(v))


def write_outputs(result, rows, buildings, exclusions, out_dir, title):
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    (out / "report.json").write_text(json.dumps(result, indent=2, ensure_ascii=False, default=str) + "\n",
                                     encoding="utf-8")
    excl = defaultdict(list)
    for e in exclusions:
        excl[e["line"]].append(e["reason"])
    with open(out / "rows_validation.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["line", "building_id", "city_id", "period_start", "period_end", "status",
                    "reasons", "empty_required", "flags", "excluded_from_aggregation"])
        for x in rows:
            w.writerow([x["line"], x["building_id"], x["city_id"], x["period_start"], x["period_end"],
                        x["status"], ";".join(x["reasons"]), ";".join(x["empty_required"]),
                        ";".join(x["flags"]), ";".join(excl.get(x["line"], []))])
    with open(out / "buildings.csv", "w", newline="", encoding="utf-8") as f:
        cols = ["building_id", "city_id", "object_type", "data_class", "floor_area_m2", "area_source",
                "days_with_value", "window_days", "metering_coverage_weighted", "kwh_window",
                "eui_window", "eui_is_annual", "confidence", "reasons_not_ranked", "flags"]
        w = csv.writer(f)
        w.writerow(cols)
        for b in buildings:
            w.writerow([";".join(b[c]) if isinstance(b.get(c), list) else b.get(c) for c in cols])
    (out / "report.md").write_text(render_markdown(result, rows, buildings, exclusions, title), encoding="utf-8")


def render_markdown(result, rows, buildings, exclusions, title):
    L = [f"# {title}", ""]
    classes = result["data_classes"]
    L.append(f"Схема `{result['schema_version']}`. Окно анализа: {result['window'][0]} — {result['window'][1]}. "
             f"Страны во входе: {', '.join(result['countries']) or '—'}. Классы данных зданий: {classes}.")
    L.append("")
    L.append("> Высокий EUI — **кандидат на энергообследование**, а не доказанная экономия и не доказанная "
             "неисправность. Рейтинг строится только внутри группы «город × тип объекта × класс данных» "
             "и только по зданиям с полностью покрытым окном.")
    L.append("")
    L.append("**Условия использования измерений (как указаны во входе):** " +
             "; ".join(result["measurement_terms"]) + ". Лицензия кода/репозитория не доказывает права на измерения.")
    L.append("")
    L.append("## 1. Строки")
    L.append("")
    L.append(f"Прочитано {result['rows_total']}, принято {result['rows_accepted']}, "
             f"отклонено {result['rows_rejected']}. Каждая строка с причинами — `rows_validation.csv`.")
    L.append("")
    if result["row_reason_counts"] or result["row_flag_counts"] or result["row_exclusion_counts"]:
        L += ["| Код | Тип | Строк | Что значит |", "|---|---|---|---|"]
        for c, n in result["row_reason_counts"].items():
            L.append(f"| `{c}` | отклонение | {n} | {REASONS[c][1]} |")
        for c, n in result["row_exclusion_counts"].items():
            L.append(f"| `{c}` | не входит в итог окна | {n} | {EXCLUSION_REASONS[c]} |")
        for c, n in result["row_flag_counts"].items():
            L.append(f"| `{c}` | предупреждение | {n} | {REASONS[c][1]} |")
        L.append("")
    rejected = [x for x in rows if x["status"] == "rejected"]
    if rejected:
        L += ["Отклонённые строки (первые 40):", "", "| Строка файла | Здание | Период | Причины |", "|---|---|---|---|"]
        for x in rejected[:40]:
            L.append(f"| {x['line']} | {x['building_id'] or '—'} | {x['period_start']}…{x['period_end']} | "
                     f"{', '.join(x['reasons'])} |")
        L.append("")
    L.append("## 2. Здания")
    L.append("")
    L.append(f"Всего {result['buildings_total']}, в рейтинге {result['buildings_ranked']}.")
    L.append("")
    if result["building_reason_counts"]:
        L += ["| Почему не в рейтинге | Зданий | Что значит |", "|---|---|---|"]
        for c, n in result["building_reason_counts"].items():
            L.append(f"| `{c}` | {n} | {BUILDING_REASONS[c]} |")
        L.append("")
    if result["building_flag_counts"]:
        L += ["| Предупреждение по зданию | Зданий | Что значит |", "|---|---|---|"]
        for c, n in result["building_flag_counts"].items():
            L.append(f"| `{c}` | {n} | {BUILDING_FLAGS[c]} |")
        L.append("")
    not_ranked = [b for b in buildings if b["reasons_not_ranked"]]
    if not_ranked:
        L += ["| Здание | Город | Дней с данными / окно | Причины |", "|---|---|---|---|"]
        for b in not_ranked[:40]:
            L.append(f"| {b['building_id']} | {b.get('city_id')} | {b.get('days_with_value', '—')} / "
                     f"{b['window_days']} | {', '.join(b['reasons_not_ranked'])} |")
        L.append("")
    L.append("## 3. Рейтинг по EUI внутри групп")
    L.append("")
    for g in result["groups"]:
        annual = all(r["eui_is_annual"] for r in g["ranking"])
        unit = "кВт·ч/м² за год" if annual else "кВт·ч/м² за окно (не год)"
        L.append(f"### {g['city_id']} · {g['object_type']} · {g['data_class']} — {g['n']} зданий, топ-{g['top_n']}")
        L.append("")
        L += [f"| Место | Здание | EUI, {unit} | В топ-{g['top_n']} | P(топ) при σ_log 0,2 | Зона | Доверие | Предупреждения |",
              "|---|---|---|---|---|---|---|---|"]
        show = [r for r in g["ranking"] if r["rank"] <= g["top_n"] + 3]
        for r in show:
            L.append(f"| {r['rank']} | {r['building_id']} | {_fmt(r['eui_window'])} | "
                     f"{'да' if r['in_top_n'] else 'нет'} | {_fmt(r['p_top_sigma_0_2'], 2)} | {r['band']} | "
                     f"{r['confidence']} | {', '.join(r['flags']) or '—'} |")
        L.append("")
        L.append(f"Показаны места 1…{min(g['n'], g['top_n'] + 3)}; полный список — `report.json`.")
        L.append("")
        L.append("**Как меняется рейтинг.**")
        L.append("")
        for s, v in g["area_error_mc"].items():
            L.append(f"- Ошибка площади ({s.replace('sigma_log_', 'σ_log = ')}): среднее совпадение топ-{g['top_n']} "
                     f"{v['mean_overlap']}, P10 {v['p10_overlap']}.")
        bands = Counter(r["band"] for r in g["ranking"])
        L.append(f"- При σ_log = 0,2: устойчиво в топе {bands.get('stable_in_top', 0)}, на границе "
                 f"{bands.get('boundary', 0)}, вне топа {bands.get('outside', 0)}.")
        L.append(f"- Неполный учёт: если досчитать каждый период как значение / покрытие (допущение равномерного "
                 f"потребления в неучтённые часы), совпадение топа {g['coverage_adjusted_top_overlap']}; "
                 f"входят {', '.join(g['coverage_adjusted_entering']) or '—'}; "
                 f"выходят {', '.join(g['coverage_adjusted_leaving']) or '—'}.")
        L.append("")
    s = result["sensitivity_strict_row_coverage"]
    L.append(f"**Строгая политика учёта.** Если не принимать периоды с покрытием < {s['min_row_coverage']}, "
             f"в рейтинге остаётся {s['buildings_ranked']} из {result['buildings_ranked']} зданий "
             f"(выпадают из-за неполного окна: {len(s['dropped_from_ranking'])}).")
    L.append("")
    L.append("## 4. Чего этот отчёт не утверждает")
    L.append("")
    L.append("- Не оценивает экономию, окупаемость и причину высокого потребления.")
    L.append("- Не сравнивает разные города и типы объектов между собой.")
    L.append("- Модель ошибки площади (лог-нормальная, σ_log 0,1–0,3) — допущение для чувствительности.")
    L.append("- Досчёт по покрытию — оценка, а не измерение; по умолчанию не используется.")
    L.append("")
    return "\n".join(L)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("input")
    ap.add_argument("--window", required=True, help="YYYY-MM-DD:YYYY-MM-DD, inclusive")
    ap.add_argument("--out", required=True)
    ap.add_argument("--title", default="Отчёт о качестве месячных данных электроэнергии")
    ap.add_argument("--top-share", type=float, default=0.2)
    ap.add_argument("--min-building-coverage", type=float, default=0.9)
    ap.add_argument("--min-row-coverage", type=float, default=None)
    ap.add_argument("--n-sim", type=int, default=1000)
    ap.add_argument("--seed", type=int, default=12)
    a = ap.parse_args(argv)
    w = [parse_date(x) for x in a.window.split(":")]
    if len(w) != 2 or None in w or w[1] < w[0]:
        ap.error("--window must be YYYY-MM-DD:YYYY-MM-DD")
    res = run(a.input, tuple(w), a.top_share, a.min_building_coverage, a.min_row_coverage,
              n_sim=a.n_sim, seed=a.seed)
    if isinstance(res, dict):
        print(json.dumps(res, ensure_ascii=False, indent=1))
        return 2
    result, rows, buildings, exclusions = res
    write_outputs(result, rows, buildings, exclusions, a.out, a.title)
    print(json.dumps({k: result[k] for k in ("rows_total", "rows_accepted", "rows_rejected",
                                             "buildings_total", "buildings_ranked")}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
