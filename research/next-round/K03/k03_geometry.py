"""K03: независимая проверка географии Астаны на сохранённых снимках OSM.

Входы (только чтение, из репозитория):
  data/geo_sources/astana_districts_overpass.json  — Overpass `out geom`, osm_base 2026-09-22T08:45:51Z
  data/geo_sources/sara_osm.json                    — OSM API full relation 19733918
  data/astana_districts.geojson                      — слой продукта
Сеть не используется. Нужны shapely и pyproj.
Запуск из корня: python research/next-round/K03/k03_geometry.py > research/next-round/K03/geometry_result.json
"""
from __future__ import annotations

import hashlib
import itertools
import json
import platform
from pathlib import Path

import pyproj
import shapely
from pyproj import Geod
from shapely.geometry import LineString, Point, shape
from shapely.ops import polygonize, unary_union

ROOT = Path(__file__).resolve().parents[3]
DATA = ROOT / "data"
GEOD = Geod(ellps="WGS84")
ASTANA = {3479876: "esil", 3482819: "almaty", 3486954: "saryarka", 8593081: "baikonur",
          20593940: "nura", 19733918: "saraishyk"}


def km2(geom) -> float:
    return abs(GEOD.geometry_area_perimeter(geom)[0]) / 1e6


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build_relation(element: dict):
    """Своя сборка: outer/inner пути → unary_union (узлы) → polygonize; inner вычитаются."""
    def rings(role):
        lines = [LineString([(p["lon"], p["lat"]) for p in m["geometry"]])
                 for m in element["members"]
                 if m["type"] == "way" and m.get("role", "") == role and m.get("geometry")]
        if not lines:
            return None
        return unary_union(list(polygonize(unary_union(lines))))
    outer, inner = rings("outer"), rings("inner")
    geom = outer if inner is None else outer.difference(inner)
    return geom.buffer(0)


def parts(geom):
    return sorted(getattr(geom, "geoms", [geom]), key=lambda g: -g.area)


def main() -> None:
    raw_path = DATA / "geo_sources/astana_districts_overpass.json"
    raw = json.loads(raw_path.read_text(encoding="utf-8"))
    rels = {e["id"]: e for e in raw["elements"] if e["type"] == "relation"}
    geoms = {rid: build_relation(e) for rid, e in rels.items()}

    product = json.loads((DATA / "astana_districts.geojson").read_text(encoding="utf-8"))
    prod = {f["properties"]["osm_id"]: shape(f["geometry"]) for f in product["features"]}

    out = {"inputs": {p: sha(DATA / p) for p in (
        "geo_sources/astana_districts_overpass.json", "geo_sources/sara_osm.json",
        "astana_districts.geojson")},
        "osm_base": raw["osm3s"]["timestamp_osm_base"],
        "relations": {}}

    for rid, e in sorted(rels.items()):
        t = e.get("tags", {})
        g = geoms[rid]
        row = {"name": t.get("name"), "name_ru": t.get("name:ru"), "name_kk": t.get("name:kk"),
               "admin_level": t.get("admin_level"), "kato_tag": t.get("kato"),
               "wikidata": t.get("wikidata"), "addr_region": t.get("addr:region"),
               "valid": g.is_valid, "area_km2_geodesic": round(km2(g), 3),
               "parts_km2": [round(km2(p), 3) for p in parts(g)]}
        if rid in prod:
            p = prod[rid]
            inter, union = km2(p.intersection(g)), km2(p.union(g))
            row["product_vs_raw_iou"] = round(inter / union, 6)
            row["product_area_km2_geodesic"] = round(km2(p), 3)
        out["relations"][str(rid)] = row

    # Перекрытия между районами Астаны (по сырым геометриям)
    ast = {ASTANA[r]: geoms[r] for r in ASTANA}
    out["astana_pair_overlaps_km2"] = {
        f"{a}|{b}": round(km2(ast[a].intersection(ast[b])), 6)
        for a, b in itertools.combinations(sorted(ast), 2)
        if ast[a].intersection(ast[b]).area > 0}
    union = unary_union(list(ast.values()))
    out["astana_union"] = {"area_km2": round(km2(union), 3),
                           "parts_km2": [round(km2(p), 3) for p in parts(union)]}

    # Площадные пересечения районов Астаны с соседями вне города
    neighbours = [r for r in rels if r not in ASTANA]
    conflicts = []
    for n in neighbours:
        for name, g in ast.items():
            inter = g.intersection(geoms[n])
            a = km2(inter) if inter.area > 0 else 0.0
            if a > 1e-6:
                rp = inter.representative_point()
                conflicts.append({"astana_district": name, "neighbour_relation": n,
                                  "neighbour_name": rels[n]["tags"].get("name"),
                                  "overlap_km2": round(a, 3),
                                  "sample_point_lonlat": [round(rp.x, 5), round(rp.y, 5)]})
    out["area_conflicts_with_neighbours"] = conflicts
    out["neighbours_touching_astana"] = sorted(
        rels[n]["tags"].get("name") for n in neighbours if geoms[n].boundary.intersection(union.boundary).length > 0)

    # Принадлежность частей (эксклавов) районов
    exclaves = []
    for name, g in ast.items():
        ps = parts(g)
        for p in ps[1:]:
            rp = p.representative_point()
            exclaves.append({"district": name, "part_km2": round(km2(p), 3),
                             "point_lonlat": [round(rp.x, 5), round(rp.y, 5)],
                             "also_inside": [rels[n]["tags"].get("name") for n in neighbours
                                             if geoms[n].covers(rp)]})
    out["exclaves"] = exclaves

    # Проверки точек из AST-A12: контрольная точка конфликта и тройная вершина
    checks = {}
    for label, lonlat in (("AST-A12 F012 point", (71.66574, 51.33028)),
                          ("AST-A12 F014 tri-point", (71.447389, 51.1311552))):
        pt = Point(*lonlat)
        checks[label] = {
            "covers": sorted([ASTANA.get(r, rels[r]["tags"].get("name")) for r in rels if geoms[r].covers(pt)]),
            "contains": sorted([ASTANA.get(r, rels[r]["tags"].get("name")) for r in rels if geoms[r].contains(pt)])}
    out["point_checks"] = checks

    sara = json.loads((DATA / "geo_sources/sara_osm.json").read_text(encoding="utf-8"))
    rel = next(e for e in sara["elements"] if e["type"] == "relation")
    out["saraishyk_api_relation"] = {"id": rel["id"], "version": rel.get("version"),
                                     "timestamp": rel.get("timestamp"), "changeset": rel.get("changeset")}
    out["versions"] = {"python": platform.python_version(), "shapely": shapely.__version__,
                       "pyproj": pyproj.__version__}
    print(json.dumps(out, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
