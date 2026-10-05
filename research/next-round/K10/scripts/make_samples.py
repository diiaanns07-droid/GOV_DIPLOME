"""K10: build small committed samples from raw Overture extracts.

- samples/<city>_districts_overture.geojson: city polygon + district polygons
  (full precision) with Overture/OSM ids, versions and source licenses.
- samples/<city>_places_social_sample.jsonl: up to 15 places per social group,
  highest confidence first; no phones/emails/socials (not extracted at all).
- samples/<city>_road_segments_sample.geojson: up to 8 road segments per class.

Usage: python make_samples.py <raw_dir> <out_samples_dir>
"""
import json
import sys

import shapely

sys.path.insert(0, __file__.rsplit("/", 1)[0])
from check_districts import CITY_REGION, km2, load, osm_ref  # noqa: E402
from places_by_district import group  # noqa: E402

PER_GROUP = 15


def districts_geojson(raw, city):
    region, districts, extra = load(raw, city)
    feats = []
    for r in region + districts + extra:
        g = shapely.from_wkt(r["geometry"])
        feats.append({
            "type": "Feature",
            "properties": {
                "city": city, "region_code": CITY_REGION[city],
                "unit_kind": "city" if r["subtype"] == "region" else "district",
                "overture_subtype": r["subtype"], "admin_level": r.get("admin_level"),
                "name_primary": r["names"]["primary"],
                "names_common": {k: v for k, v in (r["names"].get("common") or [])}
                if isinstance(r["names"].get("common"), list) else r["names"].get("common"),
                "overture_division_id": r["division_id"], "overture_area_id": r["id"],
                "overture_version": r.get("version"), "osm_relation": osm_ref(r),
                "sources": [{k: s.get(k) for k in ("dataset", "license", "record_id", "update_time")}
                            for s in r.get("sources") or []],
                "area_km2_geodesic_wgs84": round(km2(g), 3),
            },
            "geometry": shapely.geometry.mapping(g),
        })
    return {"type": "FeatureCollection",
            "name": f"{city}_districts_overture_2026-09-23.1",
            "license_note": "Overture Maps divisions; geometry derived from OpenStreetMap (ODbL-1.0). "
                            "Attribution: (c) OpenStreetMap contributors, Overture Maps Foundation.",
            "crs_note": "EPSG:4326 lon/lat",
            "features": feats}


def places_sample(raw, city):
    region, *_ = load(raw, city)
    city_g = shapely.from_wkt(region[0]["geometry"])
    by = {}
    for line in open(f"{raw}/{city}_places.jsonl", encoding="utf-8"):
        p = json.loads(line)
        g = group(p)
        if g is None:
            continue
        pt = shapely.from_wkt(p["geometry"])
        if not city_g.contains(pt):
            continue
        by.setdefault(g, []).append((p, pt))
    out = []
    for g, items in sorted(by.items()):
        items.sort(key=lambda x: -(x[0].get("confidence") or 0))
        for p, pt in items[:PER_GROUP]:
            out.append({
                "city": city, "k10_group": g,
                "overture_id": p["id"], "overture_version": p.get("version"),
                "name_primary": (p.get("names") or {}).get("primary"),
                "basic_category": p.get("basic_category"),
                "taxonomy_hierarchy": (p.get("taxonomy") or {}).get("hierarchy"),
                "confidence": round(p.get("confidence") or 0, 4),
                "lon": round(pt.x, 6), "lat": round(pt.y, 6),
                "address_freeform": [a.get("freeform") for a in (p.get("addresses") or [])][:1],
                "sources": [{k: s.get(k) for k in ("dataset", "license", "update_time")}
                            for s in p.get("sources") or []],
                "kind": "observed_secondary",
            })
    return out


def segments_sample(raw, city, per_class=8):
    """First `per_class` road segments per class fully inside the city polygon (file order)."""
    from pyproj import Geod
    geod = Geod(ellps="WGS84")
    region, *_ = load(raw, city)
    city_g = shapely.from_wkt(region[0]["geometry"])
    taken = {}
    feats = []
    for line in open(f"{raw}/{city}_segment.jsonl", encoding="utf-8"):
        s = json.loads(line)
        if s.get("subtype") != "road":
            continue
        cls = s.get("class") or "(none)"
        if taken.get(cls, 0) >= per_class:
            continue
        g = shapely.from_wkt(s["geometry"])
        if not city_g.contains(g):
            continue
        taken[cls] = taken.get(cls, 0) + 1
        feats.append({"type": "Feature", "properties": {
            "city": city, "overture_id": s["id"], "overture_version": s.get("version"),
            "subtype": s.get("subtype"), "class": cls, "subclass": s.get("subclass"),
            "name_primary": (s.get("names") or {}).get("primary"),
            "road_surface": s.get("road_surface"), "connectors": len(s.get("connectors") or []),
            "length_m_geodesic": round(geod.geometry_length(g), 1),
            "sources": [{k: x.get(k) for k in ("dataset", "license", "record_id", "update_time")}
                        for x in s.get("sources") or []]},
            "geometry": shapely.geometry.mapping(g)})
    return {"type": "FeatureCollection", "name": f"{city}_road_segments_sample_overture_2026-09-23.1",
            "license_note": "Overture transportation; derived from OpenStreetMap (ODbL-1.0).",
            "features": feats}


if __name__ == "__main__":
    raw, outdir = sys.argv[1], sys.argv[2]
    for city in ("shymkent", "astana"):
        with open(f"{outdir}/{city}_road_segments_sample.geojson", "w", encoding="utf-8") as fh:
            json.dump(segments_sample(raw, city), fh, ensure_ascii=False)
        with open(f"{outdir}/{city}_districts_overture.geojson", "w", encoding="utf-8") as fh:
            json.dump(districts_geojson(raw, city), fh, ensure_ascii=False)
        rows = places_sample(raw, city)
        with open(f"{outdir}/{city}_places_social_sample.jsonl", "w", encoding="utf-8") as fh:
            for r in rows:
                fh.write(json.dumps(r, ensure_ascii=False) + "\n")
        print(city, "places sample rows:", len(rows))
