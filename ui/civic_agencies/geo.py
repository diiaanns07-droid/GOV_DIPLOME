"""Зона кризиса на карте: районы и дворы из реальных данных OSM (только чтение, без полигонов «от руки»).

Источники (оба уже в репозитории, лицензия ODbL, © OpenStreetMap contributors):
  data/astana_districts.geojson   — границы 6 районов Астаны (relation OSM);
  data/civic/astana/geo/yards.json — дворы R12 (landuse=residential), id «yard-<osm id>», точка и контур.
Объекты и участки улиц (osm-node-…, osm-w…-…) — через R12 engine.civic_geo.target_geometry, если он в сборке.

CONTRACT §8: зона кризиса — район, дворы или цели. Полигон, нарисованный от руки, R17 не принимает.
"""

from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DISTRICTS_PATH = ROOT / "data" / "astana_districts.geojson"
YARDS_PATH = ROOT / "data" / "civic" / "astana" / "geo" / "yards.json"

DISTRICTS = ("almaty", "baikonur", "esil", "nura", "saraishyk", "saryarka")
# Подписи районов — общие названия (как в словаре R11 district.<id>); казахские — по написанию R11.
DISTRICT_NAMES = {
    "almaty": {"ru": "Алматы", "kk": "Алматы"},
    "baikonur": {"ru": "Байконур", "kk": "Байқоңыр"},
    "esil": {"ru": "Есиль", "kk": "Есіл"},
    "nura": {"ru": "Нура", "kk": "Нұра"},
    "saraishyk": {"ru": "Сарайшык", "kk": "Сарайшық"},
    "saryarka": {"ru": "Сарыарка", "kk": "Сарыарқа"},
}
TARGET_RE = re.compile(r"^(yard-[0-9]{1,15}|cell-(-?[0-9]{1,6})-(-?[0-9]{1,6})|osm-(node|way|relation)-[0-9]{1,15}"
                       r"|osm-w[0-9]{1,15}-[0-9]{1,6})\Z")


def _rings(geometry: dict) -> list[list[list[list[float]]]]:
    """Polygon / MultiPolygon → список полигонов (каждый — список колец)."""
    if not isinstance(geometry, dict):
        return []
    if geometry.get("type") == "Polygon":
        return [geometry.get("coordinates") or []]
    if geometry.get("type") == "MultiPolygon":
        return list(geometry.get("coordinates") or [])
    return []


def _inside_ring(point, ring) -> bool:
    x, y = point
    inside = False
    for (ax, ay), (bx, by) in zip(ring, ring[1:]):
        if (ay > y) != (by > y) and x < ax + (y - ay) * (bx - ax) / (by - ay):
            inside = not inside
    return inside


def point_in_polygons(point, polygons) -> bool:
    for rings in polygons:
        if rings and _inside_ring(point, rings[0]) and not any(_inside_ring(point, hole) for hole in rings[1:]):
            return True
    return False


@lru_cache(maxsize=1)
def districts() -> dict:
    """{id: {"id", "polygons", "bbox", "geometry"}} — пусто, если файла нет (тогда зона рисуется без контура)."""
    try:
        data = json.loads(DISTRICTS_PATH.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return {}
    out = {}
    for feature in data.get("features") or []:
        props, geometry = feature.get("properties") or {}, feature.get("geometry") or {}
        did = props.get("id")
        polys = _rings(geometry)
        if did not in DISTRICTS or not polys:
            continue
        xs = [c[0] for poly in polys for c in poly[0]]
        ys = [c[1] for poly in polys for c in poly[0]]
        out[did] = {"id": did, "polygons": polys, "bbox": [min(xs), min(ys), max(xs), max(ys)], "geometry": geometry}
    return out


def district_of(point) -> str | None:
    if not isinstance(point, (list, tuple)) or len(point) != 2:
        return None
    for did, d in districts().items():
        bb = d["bbox"]
        if bb[0] <= point[0] <= bb[2] and bb[1] <= point[1] <= bb[3] and point_in_polygons(point, d["polygons"]):
            return did
    return None


@lru_cache(maxsize=1)
def yards() -> dict:
    """{yard id: {"id", "label_ru", "label_kk", "point", "polygon", "district"}} из R12 yards.json."""
    try:
        data = json.loads(YARDS_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    out = {}
    for item in data.get("items") or []:
        yid, point = item.get("id"), item.get("point")
        if not isinstance(yid, str) or not yid.startswith("yard-") or not isinstance(point, list):
            continue
        name_ru = item.get("name_ru")
        out[yid] = {"id": yid, "label_ru": f"Двор: {name_ru}" if name_ru else "Двор",
                    "label_kk": f"Аула: {item.get('name_kk') or name_ru}" if (item.get("name_kk") or name_ru) else "Аула",
                    "point": point, "polygon": item.get("polygon"), "district": district_of(point)}
    return out


def _r12_target(target_id: str) -> dict | None:
    try:
        from engine.civic_geo import target_geometry  # type: ignore
    except Exception:  # noqa: BLE001 — R12 нет в сборке
        return None
    kind = "segment" if re.match(r"^osm-w[0-9]+-[0-9]+$", target_id) else "object"
    try:
        found = target_geometry({"kind": kind, "id": target_id})
    except Exception:  # noqa: BLE001
        return None
    return found if isinstance(found, dict) else None


def target_info(target_id: str) -> dict | None:
    """Цель зоны: {"id", "kind", "label_ru", "label_kk", "district", "geometry"} или None (цели нет на карте)."""
    if not isinstance(target_id, str) or not TARGET_RE.match(target_id):
        return None
    if target_id.startswith("yard-"):
        yard = yards().get(target_id)
        if yard is None:
            return None
        geometry = {"type": "Polygon", "coordinates": yard["polygon"]} if yard.get("polygon") else \
            {"type": "Point", "coordinates": yard["point"]}
        return {"id": target_id, "kind": "area", "label_ru": yard["label_ru"], "label_kk": yard["label_kk"],
                "district": yard["district"], "geometry": geometry}
    if target_id.startswith("cell-"):
        try:
            from ui.civic_feedback.v2.record import cell_polygon  # type: ignore — сетка ячеек общая с R07/R12
        except Exception:  # noqa: BLE001
            return None
        ring = cell_polygon(target_id)
        if ring is None:
            return None
        centre = [sum(c[0] for c in ring[:4]) / 4, sum(c[1] for c in ring[:4]) / 4]
        return {"id": target_id, "kind": "area", "label_ru": "Примерное место", "label_kk": "Шамамен орны",
                "district": district_of(centre), "geometry": {"type": "Polygon", "coordinates": [ring]},
                "approximate": True}
    found = _r12_target(target_id)
    if not found or not isinstance(found.get("geometry"), dict):
        return None
    geometry = found["geometry"]
    point = None
    if geometry.get("type") == "Point":
        point = geometry.get("coordinates")
    elif geometry.get("type") == "LineString" and geometry.get("coordinates"):
        coords = geometry["coordinates"]
        point = coords[len(coords) // 2]
    return {"id": target_id, "kind": "segment" if target_id.startswith("osm-w") else "object",
            "label_ru": found.get("label_ru") or "", "label_kk": found.get("label_kk") or "",
            "district": district_of(point) if point else None, "geometry": geometry}


def zone_geometry(zone: dict) -> dict:
    """FeatureCollection зоны для слоя «Кризис»: контур района или контуры/точки целей. Нет данных — пустая."""
    features = []
    if zone.get("kind") == "district":
        d = districts().get(zone.get("district"))
        if d is not None:
            features.append({"type": "Feature", "geometry": d["geometry"],
                             "properties": {"id": d["id"], "kind": "district"}})
    else:
        for tid in zone.get("targets") or []:
            info = target_info(tid)
            if info is not None:
                features.append({"type": "Feature", "geometry": info["geometry"],
                                 "properties": {"id": tid, "kind": info["kind"]}})
    return {"type": "FeatureCollection", "features": features}


def zone_bbox(geometry: dict) -> list[float] | None:
    xs, ys = [], []

    def walk(coords):
        if isinstance(coords, (list, tuple)) and coords and isinstance(coords[0], (int, float)):
            xs.append(coords[0])
            ys.append(coords[1])
        elif isinstance(coords, (list, tuple)):
            for c in coords:
                walk(c)

    for feature in geometry.get("features") or []:
        walk((feature.get("geometry") or {}).get("coordinates"))
    if not xs:
        return None
    return [round(min(xs), 6), round(min(ys), 6), round(max(xs), 6), round(max(ys), 6)]
