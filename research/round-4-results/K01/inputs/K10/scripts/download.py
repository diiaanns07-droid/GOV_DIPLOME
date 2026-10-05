"""K10 round 3 package builder (NETWORK). Downloads one study square per city from Overture.

Reads selection/<city>_bbox_selection.json, fetches from the public Overture S3 bucket
(anonymous HTTPS, HTTP Range reads of row groups whose bbox statistics intersect):
  * places  : every place whose point lies in the square and matches the K10 social rule
  * segments: every transportation segment (road/rail/water) whose geometry intersects the square
  * connectors: every connector referenced by those segments (some lie outside the square)
Writes data/<city>/{places_social,segments,connectors}.geojson and package_manifest.json.

Deps: pyarrow, shapely, requests (see requirements-download.txt). No keys/secrets.
Usage (from the package dir): python scripts/download.py [--out data] [--manifest package_manifest.json]
"""
import hashlib
import io
import json
import os
import platform
import re
import sys
import time
from datetime import datetime, timezone

import pyarrow
import pyarrow.parquet as pq
import requests
import shapely
from shapely.geometry import box, mapping

HERE = os.path.dirname(os.path.abspath(__file__))
PKG = os.path.dirname(HERE)
sys.path.insert(0, HERE)
from k10_rules import BUCKET, RELEASE, flags_of, foot_access, levels_of, social_group  # noqa: E402
from geo_util import line_length_m, point_in_bbox  # noqa: E402

CA = os.environ.get("REQUESTS_CA_BUNDLE", "/root/.ccr/ca-bundle.crt")
S = requests.Session()
S.verify = CA if os.path.exists(CA) else True
STATS = {"requests": 0, "bytes": 0}
PF_CACHE = {}

PLACE_COLS = ["id", "geometry", "version", "confidence", "names", "basic_category", "taxonomy",
              "operating_status", "addresses", "sources", "bbox"]
SEG_COLS = ["id", "geometry", "version", "subtype", "class", "subclass", "subclass_rules", "names",
            "connectors", "road_surface", "road_flags", "level_rules", "width_rules",
            "access_restrictions", "speed_limits", "sources", "bbox"]
CONN_COLS = ["id", "geometry", "version", "sources", "bbox"]
NOT_EXTRACTED = {"places": ["phones", "emails", "socials", "websites", "brand"],
                 "segments": ["rail_flags", "prohibited_transitions", "routes", "destinations"]}


class RangeFile(io.RawIOBase):
    def __init__(self, url, size):
        self.url, self.size, self.pos = url, size, 0

    def readable(self):
        return True

    def seekable(self):
        return True

    def tell(self):
        return self.pos

    def seek(self, off, whence=0):
        self.pos = off if whence == 0 else self.pos + off if whence == 1 else self.size + off
        return self.pos

    def readinto(self, b):
        if self.pos >= self.size or not len(b):
            return 0
        end = min(self.pos + len(b), self.size) - 1
        for attempt in range(3):
            r = S.get(self.url, headers={"Range": f"bytes={self.pos}-{end}"}, timeout=120)
            if r.status_code == 206:
                break
            time.sleep(2 * (attempt + 1))
        r.raise_for_status()
        STATS["requests"] += 1
        STATS["bytes"] += len(r.content)
        b[: len(r.content)] = r.content
        self.pos += len(r.content)
        return len(r.content)


def list_keys(theme, typ):
    prefix = f"release/{RELEASE}/theme={theme}/type={typ}/"
    r = S.get(f"{BUCKET}/?list-type=2&prefix={prefix}", timeout=60)
    r.raise_for_status()
    STATS["requests"] += 1
    if "<IsTruncated>true</IsTruncated>" in r.text:
        raise RuntimeError("listing truncated")
    return prefix, [(k, int(s)) for k, s in
                    re.findall(r"<Key>([^<]+\.parquet)</Key>.*?<Size>(\d+)</Size>", r.text)]


def rg_bbox(pf, rg):
    md = pf.metadata.row_group(rg)
    v = {}
    for c in range(md.num_columns):
        col = md.column(c)
        st = col.statistics
        if st is None or not st.has_min_max:
            continue
        name = col.path_in_schema
        if name in ("bbox.xmin", "bbox.ymin"):
            v[name[-4:]] = st.min
        elif name in ("bbox.xmax", "bbox.ymax"):
            v[name[-4:]] = st.max
    return (v["xmin"], v["ymin"], v["xmax"], v["ymax"]) if len(v) == 4 else None


def hit(a, b):
    return not (a[2] < b[0] or a[0] > b[2] or a[3] < b[1] or a[1] > b[3])


def scan(theme, typ, qbox, cols, keep):
    """Yield rows (geometry as shapely) of row groups intersecting qbox for which keep(row, geom) is True."""
    prefix, keys = list_keys(theme, typ)
    files, scanned = [], 0
    out = []
    for key, size in keys:
        if key not in PF_CACHE:  # footers are read once and reused for the second city
            PF_CACHE[key] = pq.ParquetFile(io.BufferedReader(RangeFile(f"{BUCKET}/{key}", size), buffer_size=1 << 20))
        pf = PF_CACHE[key]
        rgs = [rg for rg in range(pf.metadata.num_row_groups) if (s := rg_bbox(pf, rg)) and hit(s, qbox)]
        if not rgs:
            continue
        files.append({"url": f"{BUCKET}/{key}", "bytes_total": size,
                      "row_groups_total": pf.metadata.num_row_groups, "row_groups_read": rgs})
        use = [c for c in cols if c in pf.schema_arrow.names]
        for rg in rgs:
            for row in pf.read_row_group(rg, columns=use).to_pylist():
                scanned += 1
                b = row["bbox"]
                if not hit((b["xmin"], b["ymin"], b["xmax"], b["ymax"]), qbox):
                    continue
                g = shapely.from_wkb(row["geometry"])
                if keep(row, g):
                    out.append((row, g))
        print(f"  {typ} {key.rsplit('/', 1)[-1][:10]} rg={rgs}", file=sys.stderr)
    return {"listing_prefix": prefix, "files": files, "rows_scanned_in_row_groups": scanned,
            "columns": cols}, out


def jsonable(v):
    if isinstance(v, dict):
        return {k: jsonable(x) for k, x in v.items()}
    if isinstance(v, list):
        return [jsonable(x) for x in v]
    if isinstance(v, (bytes, bytearray)):
        return v.hex()
    if isinstance(v, float):
        return round(v, 9)
    return v


def names_min(n):
    return {"primary": (n or {}).get("primary")} if n else None


def write_fc(path, name, feats, extra):
    fc = {"type": "FeatureCollection", "name": name, **extra, "features": feats}
    data = json.dumps(fc, ensure_ascii=False, separators=(",", ":"), sort_keys=False).encode("utf-8")
    with open(path, "wb") as fh:
        fh.write(data)
    return {"path": os.path.relpath(path, PKG), "sha256": hashlib.sha256(data).hexdigest(),
            "bytes": len(data), "features": len(feats)}


def build_city(city, out_dir):
    sel_path = os.path.join(PKG, "selection", f"{city}_bbox_selection.json")
    sel_bytes = open(sel_path, "rb").read()
    bb = tuple(json.loads(sel_bytes)["selected"]["bbox"])
    sq = box(*bb)
    started = datetime.now(timezone.utc).isoformat(timespec="seconds")
    os.makedirs(os.path.join(out_dir, city), exist_ok=True)
    lic = {"© OpenStreetMap contributors (ODbL-1.0)", "Overture Maps Foundation"}

    # places: point inside the square and K10 social rule
    pq_info, places = scan("places", "place", bb, PLACE_COLS,
                           lambda r, g: point_in_bbox(g.x, g.y, bb))
    n_all_places = len(places)
    pfeats = []
    for r, g in sorted(places, key=lambda x: x[0]["id"]):
        grp = social_group(r.get("taxonomy"), r.get("basic_category"))
        if grp is None:
            continue
        pfeats.append({"type": "Feature", "id": r["id"], "geometry": mapping(g), "properties": {
            "city": city, "k10_group": grp, "overture_id": r["id"], "overture_version": r.get("version"),
            "name_primary": (r.get("names") or {}).get("primary"), "basic_category": r.get("basic_category"),
            "taxonomy": jsonable(r.get("taxonomy")), "confidence": jsonable(r.get("confidence")),
            "operating_status": r.get("operating_status"), "addresses": jsonable(r.get("addresses")),
            "sources": jsonable(r.get("sources")), "kind": "observed_secondary"}})

    # segments: geometry intersects the square (full geometry kept, not clipped)
    sq_info, segs = scan("transportation", "segment", bb, SEG_COLS, lambda r, g: g.intersects(sq))
    sfeats, conn_ids, env = [], set(), list(bb)
    for r, g in sorted(segs, key=lambda x: x[0]["id"]):
        coords = list(g.coords)
        inside = all(point_in_bbox(x, y, bb) for x, y in coords)
        fa, _ = foot_access(r.get("access_restrictions"))
        cids = [c["connector_id"] for c in r.get("connectors") or []]
        conn_ids.update(cids)
        x0, y0, x1, y1 = g.bounds
        env = [min(env[0], x0), min(env[1], y0), max(env[2], x1), max(env[3], y1)]
        sfeats.append({"type": "Feature", "id": r["id"], "geometry": mapping(g), "properties": {
            "city": city, "overture_id": r["id"], "overture_version": r.get("version"),
            "subtype": r.get("subtype"), "class": r.get("class"), "subclass": r.get("subclass"),
            "subclass_rules": jsonable(r.get("subclass_rules")), "name_primary": (r.get("names") or {}).get("primary"),
            "connectors": jsonable(r.get("connectors")), "road_surface": jsonable(r.get("road_surface")),
            "road_flags": jsonable(r.get("road_flags")), "level_rules": jsonable(r.get("level_rules")),
            "width_rules": jsonable(r.get("width_rules")), "access_restrictions": jsonable(r.get("access_restrictions")),
            "speed_limits": jsonable(r.get("speed_limits")), "sources": jsonable(r.get("sources")),
            "k10_foot_access": fa, "k10_flags": flags_of(r.get("road_flags")), "k10_levels": levels_of(r.get("level_rules")),
            "k10_crosses_bbox_edge": not inside, "k10_length_m": round(line_length_m(coords), 2),
            "kind": "observed_secondary"}})

    # connectors: all ids referenced by kept segments; query box = envelope of kept segments
    cq_info, conns = scan("transportation", "connector", tuple(env), CONN_COLS, lambda r, g: r["id"] in conn_ids)
    cq_info["query_bbox_envelope_of_segments"] = [round(v, 7) for v in env]
    cfeats = []
    for r, g in sorted(conns, key=lambda x: x[0]["id"]):
        cfeats.append({"type": "Feature", "id": r["id"], "geometry": mapping(g), "properties": {
            "city": city, "overture_id": r["id"], "overture_version": r.get("version"),
            "sources": jsonable(r.get("sources")), "k10_inside_bbox": point_in_bbox(g.x, g.y, bb)}})

    common = {"release": RELEASE, "city": city, "bbox": list(bb),
              "attribution": sorted(lic), "kind": "observed_secondary (Overture/OSM), not an official registry"}
    files = {
        "places_social": write_fc(os.path.join(out_dir, city, "places_social.geojson"),
                                  f"{city}_places_social", pfeats, common),
        "segments": write_fc(os.path.join(out_dir, city, "segments.geojson"),
                             f"{city}_segments", sfeats, common),
        "connectors": write_fc(os.path.join(out_dir, city, "connectors.geojson"),
                               f"{city}_connectors", cfeats, common),
    }
    return {
        "city": city, "bbox": list(bb),
        "selection": {"path": os.path.relpath(sel_path, PKG), "sha256": hashlib.sha256(sel_bytes).hexdigest()},
        "started_utc": started, "finished_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "queries": {
            "places": {**pq_info, "query": "point within bbox AND K10 social rule (k10_rules.social_group)",
                       "places_in_bbox_any_category": n_all_places},
            "segments": {**sq_info, "query": "segment geometry intersects bbox (full geometry kept)"},
            "connectors": {**cq_info, "query": "connector id referenced by kept segments",
                           "referenced_ids": len(conn_ids)},
        },
        "files": files,
    }


def main():
    out = os.path.join(PKG, "data")
    man = {"package": "K10 round-3 compact geo-package (Shymkent + Astana)",
           "release": RELEASE, "bucket": BUCKET,
           "not_extracted_columns": NOT_EXTRACTED,
           "tool_versions": {"python": platform.python_version(), "pyarrow": pyarrow.__version__,
                             "shapely": shapely.__version__, "requests": requests.__version__},
           "cities": {}}
    for city in ("shymkent", "astana"):
        print(city, file=sys.stderr)
        man["cities"][city] = build_city(city, out)
    man["download_stats"] = dict(STATS)
    with open(os.path.join(PKG, "package_manifest.json"), "w", encoding="utf-8") as fh:
        json.dump(man, fh, ensure_ascii=False, indent=1)
    print(json.dumps({c: {k: v["features"] for k, v in d["files"].items()} for c, d in man["cities"].items()}))


if __name__ == "__main__":
    main()
