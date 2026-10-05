#!/usr/bin/env python3
"""Независимый Python-эталон расчёта city-whatif-v1 (для сверки с whatif.js). Только stdlib.

Повторяет: отпечаток среза, гаверсинус, ближайшую запись с ничьей по id, before/after/delta.
Валидацию импорта не дублирует (её проверяют тесты JS-модуля).
"""
import hashlib
import json
import math

R_EARTH_M = 6371008.8
PARAMS = {"formula": "haversine", "radius_m": R_EARTH_M, "coord_order": "lon,lat", "clamp": "[0,1]", "version": 1}
SCHEMA = "city-whatif-v1"


def haversine_m(lon1, lat1, lon2, lat2):
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = math.radians(lat2 - lat1), math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    a = min(1.0, max(0.0, a))
    return 2 * R_EARTH_M * math.asin(math.sqrt(a))


def _num(v):
    # как JSON.stringify: целые без «.0», остальное — кратчайшее представление (repr совпадает для наших float)
    if isinstance(v, float) and v.is_integer() and abs(v) < 1e21:
        return str(int(v))
    return repr(v)


def canon(v):
    if v is None or isinstance(v, bool):
        return json.dumps(v)
    if isinstance(v, (int, float)):
        return _num(v)
    if isinstance(v, str):
        return json.dumps(v, ensure_ascii=False)
    if isinstance(v, list):
        return "[" + ",".join(canon(x) for x in v) + "]"
    return "{" + ",".join(json.dumps(k, ensure_ascii=False) + ":" + canon(v[k]) for k in sorted(v)) + "}"


def source_snapshot(city_id, city_data, category):
    recs = sorted([[p["id"], p["lon"], p["lat"]] for p in city_data["places"] if p["group"] == category], key=lambda r: r[0])
    body = {"schema": SCHEMA, "city_id": city_id, "category": category, "release": city_data["release"],
            "places_sha256": city_data["files"]["places_social"]["sha256"], "bbox": city_data["bbox"],
            "records": recs, "params": PARAMS}
    return "wif1-sha256:" + hashlib.sha256(canon(body).encode("utf-8")).hexdigest()


def compute(city_data, scn):
    recs = [p for p in city_data["places"] if p["group"] == scn["category"]]
    prop = scn.get("proposed_object")
    rows = []
    for p in scn["control_points"]:
        best = None
        for r in recs:
            d = haversine_m(p["lon"], p["lat"], r["lon"], r["lat"])
            if best is None or d < best[0] or (d == best[0] and r["id"] < best[1]["id"]):
                best = (d, r)
        before = best[0] if best else None
        dprop = haversine_m(p["lon"], p["lat"], prop["lon"], prop["lat"]) if prop else None
        if before is None:
            after, src = dprop, ("proposed" if prop else None)
        elif prop and dprop < before:
            after, src = dprop, "proposed"
        else:
            after, src = before, "existing"
        rows.append({"point_id": p["id"], "before_m": before, "before_id": best[1]["id"] if best else None,
                     "after_m": after, "after_source": src,
                     "delta_m": (before - after) if before is not None and after is not None else None})
    return rows
