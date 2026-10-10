"""Сборка data/civic/astana/geo/{objects,yards,cells}.json и SOURCE.json из сырых выгрузок OSM.

Входы (только чтение):
  1. data/civic/astana/osm-objects/raw/*.json[.gz] — выгрузки Overpass `out geom;` (задача LOCAL-1);
     имя файла не важно: тип объекта определяется по тегам.
  2. data/civic/astana/osm-walking/overpass.json.gz — снимок пешеходной сети: в нём есть узлы-остановки,
     которые лежат прямо на линиях дорог (highway=bus_stop / public_transport=platform).
Объекты вне границы Астаны (полигоны районов из geofence.json) отбрасываются; двор берётся, только если внутри
весь его контур, контур парка/площадки — только целиком в городе (иначе объект — точка). Ничего не придумывается:
каждая запись — реальный объект OSM с его id и координатами.

    python3 -m engine.civic_geo.build_geo_data            # из data/civic/astana/osm-objects/raw
    python3 -m engine.civic_geo.build_geo_data --raw-dir tests/civic/R12/fixtures/osm-objects/raw --out /tmp/geo
"""
from __future__ import annotations

import argparse
import datetime as dt
import gzip
import hashlib
import json
from pathlib import Path

from . import geo
from .build_way_tags import kazakh_name
from .objects import DEFAULT_CELLS
from .paths import GEO_DIR, GEOFENCE, OSM_OBJECTS_DIR, OSM_WALKING_RAW, ROOT

YARD_SIMPLIFY_M = 1.5
AREA_SIMPLIFY_M = 2.0


def classify(tags: dict) -> str | None:
    """Тип объекта карты по тегам OSM (или None — не наш объект)."""
    if tags.get("highway") == "bus_stop":
        return "bus_stop"
    if tags.get("public_transport") == "platform" and tags.get("railway") is None and tags.get("train") != "yes":
        return "bus_stop"
    leisure = tags.get("leisure")
    if leisure == "playground":
        return "playground"
    if leisure == "pitch":
        return "pitch"
    if leisure in ("park", "garden"):
        return "park"
    if tags.get("amenity") in ("waste_disposal", "recycling"):
        return "waste"
    if tags.get("landuse") == "residential":
        return "yard"
    return None


def russian_name(tags: dict) -> str | None:
    """name:ru, иначе name, если оно не казахское (в Астане name часто по-казахски)."""
    if tags.get("name:ru"):
        return tags["name:ru"].strip()
    name = (tags.get("name") or "").strip()
    if name and kazakh_name({"name": name}) is None:
        return name
    return None


def _ring_from_geometry(geometry) -> list[list[float]]:
    return [[float(p["lon"]), float(p["lat"])] for p in geometry if p is not None]


def _close(ring):
    if ring and ring[0] != ring[-1]:
        ring = ring + [ring[0]]
    return ring


def _assemble_rings(parts: list[list[list[float]]]) -> list[list[list[float]]]:
    """Склеивает открытые куски внешней границы мультиполигона по совпадающим концам."""
    rings, open_parts = [], [p for p in parts if len(p) >= 2]
    while open_parts:
        cur = open_parts.pop(0)
        changed = True
        while cur[0] != cur[-1] and changed:
            changed = False
            for i, p in enumerate(open_parts):
                if p[0] == cur[-1]:
                    cur = cur + p[1:]
                elif p[-1] == cur[-1]:
                    cur = cur + list(reversed(p))[1:]
                elif p[-1] == cur[0]:
                    cur = p + cur[1:]
                elif p[0] == cur[0]:
                    cur = list(reversed(p)) + cur[1:]
                else:
                    continue
                open_parts.pop(i)
                changed = True
                break
        if cur[0] == cur[-1] and len(cur) >= 4:
            rings.append(cur)
    return rings


def element_shape(el: dict):
    """(точка, полигоны или None) элемента Overpass `out geom;`. Для линии без замыкания полигона нет."""
    if el["type"] == "node":
        return [float(el["lon"]), float(el["lat"])], None
    if el["type"] == "way" and el.get("geometry"):
        ring = _ring_from_geometry(el["geometry"])
        if len(ring) >= 4 and ring[0] == ring[-1]:
            return None, [[ring]]
        return (ring[len(ring) // 2] if ring else None), None
    if el["type"] == "relation":
        outers = [_ring_from_geometry(m.get("geometry") or []) for m in el.get("members", [])
                  if m.get("type") == "way" and m.get("role") in ("outer", "")]
        rings = _assemble_rings(outers)
        if rings:
            return None, [[r] for r in rings]
    return None, None


def osm_id(el: dict) -> str:
    return f"osm-{el['type']}-{el['id']}"


def _load_elements(path: Path) -> list[dict]:
    raw = path.read_bytes()
    if path.suffix == ".gz":
        raw = gzip.decompress(raw)
    return json.loads(raw.decode("utf-8")).get("elements", [])


class CityBoundary:
    def __init__(self, geofence_path: Path = GEOFENCE):
        g = json.loads(Path(geofence_path).read_text("utf-8"))
        self.polygons = [p["rings"] for p in g["polygons"]]
        self.bbox = g["city_bbox"]

    def contains(self, p) -> bool:
        if not (self.bbox[0] <= p[0] <= self.bbox[2] and self.bbox[1] <= p[1] <= self.bbox[3]):
            return False
        return any(geo.point_in_polygon(p, rings) for rings in self.polygons)


def _file_entry(path: Path) -> dict:
    data = path.read_bytes()
    rel = path.resolve().relative_to(ROOT) if path.resolve().is_relative_to(ROOT) else path
    return {"path": str(rel), "sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data)}


def build(raw_dir: Path = OSM_OBJECTS_DIR / "raw", walking_raw: Path | None = OSM_WALKING_RAW,
          geofence_path: Path = GEOFENCE, evidence_type: str = "real") -> dict:
    boundary = CityBoundary(geofence_path)
    sources: list[dict] = []
    elements: list[tuple[dict, str]] = []
    raw_dir = Path(raw_dir)
    raw_files = sorted([p for p in raw_dir.glob("*.json*") if p.is_file()]) if raw_dir.is_dir() else []
    for p in raw_files:
        sources.append(_file_entry(p))
        elements.extend((el, p.name) for el in _load_elements(p))
    if walking_raw is not None and Path(walking_raw).is_file():
        sources.append(_file_entry(Path(walking_raw)) | {"use": "только узлы-остановки на линиях дорог"})
        for el in _load_elements(Path(walking_raw)):
            if el.get("type") == "node" and el.get("tags") and classify(el["tags"]) == "bus_stop":
                elements.append((el, Path(walking_raw).name))

    objects: dict[str, dict] = {}
    yards: dict[str, dict] = {}
    skipped = {"outside_city": 0, "no_geometry": 0, "duplicate": 0}
    other = {}
    for el, src in elements:
        tags = el.get("tags") or {}
        kind = classify(tags)
        if kind is None:
            key = tags.get("highway") or tags.get("amenity") or "other"
            other[key] = other.get(key, 0) + 1
            continue
        oid = osm_id(el)
        if oid in objects or oid in yards:
            skipped["duplicate"] += 1
            continue
        point, polys = element_shape(el)
        if kind == "yard":
            if not polys:
                skipped["no_geometry"] += 1
                continue
            # Мультиполигон из нескольких частей — каждая часть отдельным двором.
            for n, rings in enumerate(polys):
                ring = geo.simplify(rings[0], YARD_SIMPLIFY_M)
                if len(ring) < 4:
                    continue
                center = geo.bbox_center(ring)
                # Внутри Астаны должен быть весь двор, а не только центр (R10 B-009: двор на окраине,
                # 19 из 26 вершин за границей). Двор на границе не обрезаем — жалоба там идёт в ячейку 150 м.
                if not boundary.contains(center) or not all(boundary.contains(c) for c in ring):
                    skipped["outside_city"] += 1
                    continue
                yid = f"yard-{el['id']}" if el["type"] == "way" else f"yard-r{el['id']}" + (f"-{n}" if len(polys) > 1 else "")
                yards[yid] = {"id": yid, "kind": "yard", "osm": oid, "name_ru": russian_name(tags),
                              "name_kk": kazakh_name(tags), "point": center,
                              "polygon": [[geo.round_coord(c) for c in ring]]}
            continue
        polygon = None
        if polys:
            ring = geo.simplify(polys[0][0], AREA_SIMPLIFY_M)
            if len(ring) >= 4:
                point = geo.bbox_center(ring)
                # Контур парка/площадки рисуем, только если он целиком в городе; иначе объект остаётся точкой.
                if all(boundary.contains(c) for c in ring):
                    polygon = [[geo.round_coord(c) for c in ring]]
        if point is None:
            skipped["no_geometry"] += 1
            continue
        if not boundary.contains(point):
            skipped["outside_city"] += 1
            continue
        item = {"id": oid, "kind": kind, "name_ru": russian_name(tags), "name_kk": kazakh_name(tags),
                "point": geo.round_coord(point)}
        if kind == "park" and tags.get("leisure") == "garden":
            item["subkind"] = "garden"
        if kind == "waste" and tags.get("amenity") == "recycling":
            item["subkind"] = "recycling"
        if polygon:
            item["polygon"] = polygon
        item["src"] = src
        objects[oid] = item

    # Одна остановка часто нарисована дважды: узел highway=bus_stop и платформа рядом с тем же именем.
    stops = sorted((o for o in objects.values() if o["kind"] == "bus_stop"), key=lambda o: o["id"])
    for i, a in enumerate(stops):
        if a["id"] not in objects:
            continue
        for b in stops[i + 1:]:
            if b["id"] in objects and a["name_ru"] == b["name_ru"] and geo.haversine_m(a["point"], b["point"]) < 25:
                del objects[b["id"]]
                skipped["duplicate"] += 1

    items = sorted(objects.values(), key=lambda o: (o["kind"], o["id"]))
    counts: dict[str, int] = {}
    for o in items:
        counts[o["kind"]] = counts.get(o["kind"], 0) + 1
    return {
        "objects": items,
        "yards": sorted(yards.values(), key=lambda y: y["id"]),
        "sources": sources,
        "counts": counts | {"yard": len(yards)},
        "skipped": skipped,
        "not_used_tags": dict(sorted(other.items(), key=lambda kv: -kv[1])[:20]),
        "raw_dir_present": bool(raw_files),
        "evidence_type": evidence_type,
    }


LICENSE = {"id": "ODbL-1.0", "attribution": "© OpenStreetMap contributors",
           "url": "https://www.openstreetmap.org/copyright"}


def write(result: dict, out_dir: Path, raw_dir: Path) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    common = {"license": LICENSE, "evidence_type": result["evidence_type"]}
    objects = {"schema": "r12-geo-objects-v1", **common,
               "kinds": ["bus_stop", "playground", "pitch", "park", "waste"],
               "count": len(result["objects"]), "items": result["objects"]}
    yards = {"schema": "r12-geo-yards-v1", **common,
             "note": "Дворы — полигоны landuse=residential из OSM, упрощены с допуском 1,5 м.",
             "count": len(result["yards"]), "items": result["yards"]}
    cells = dict(DEFAULT_CELLS) | {
        "note": "Ячейки там, где двора нет: id cell-<ix>-<iy>, ix = floor((lon - origin_lon) / dlon), "
                "iy = floor((lat - origin_lat) / dlat), dlat = cell_m / m_per_deg_lat, "
                "dlon = cell_m / (m_per_deg_lon_equator * cos(ref_lat)). Те же константы, что у R07 (ui/civic_heat/geo.py).",
    }
    for name, data in (("objects.json", objects), ("yards.json", yards), ("cells.json", cells)):
        (out_dir / name).write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")) + "\n", "utf-8")
    source = {
        "schema": "r12-geo-source-v1",
        "built_at": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "builder": "engine/civic_geo/build_geo_data.py",
        "raw_dir": str(Path(raw_dir)),
        "raw_dir_present": result["raw_dir_present"],
        "inputs": result["sources"],
        "counts": result["counts"],
        "skipped": result["skipped"],
        "not_used_tags": result["not_used_tags"],
        "license": LICENSE,
        "evidence_type": result["evidence_type"],
        "status": ("full" if result["raw_dir_present"] else
                   "partial: нет выгрузки LOCAL-1 (data/civic/astana/osm-objects/raw) — только остановки из снимка "
                   "пешеходной сети; дворов, площадок и парков нет"),
    }
    (out_dir / "SOURCE.json").write_text(json.dumps(source, ensure_ascii=False, indent=1) + "\n", "utf-8")
    return source


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--raw-dir", default=str(OSM_OBJECTS_DIR / "raw"))
    ap.add_argument("--out", default=str(GEO_DIR))
    ap.add_argument("--no-walking", action="store_true", help="не брать остановки из снимка пешеходной сети")
    ap.add_argument("--evidence", default="real", choices=["real", "synthetic"],
                    help="synthetic — только для тестовой фикстуры")
    args = ap.parse_args(argv)
    result = build(Path(args.raw_dir), None if args.no_walking else OSM_WALKING_RAW, evidence_type=args.evidence)
    source = write(result, Path(args.out), Path(args.raw_dir))
    print(json.dumps({"counts": source["counts"], "skipped": source["skipped"], "status": source["status"]},
                     ensure_ascii=False))


if __name__ == "__main__":
    main()
