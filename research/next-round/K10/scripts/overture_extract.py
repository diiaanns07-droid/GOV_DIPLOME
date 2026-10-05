"""K10: read small city extracts from Overture Maps GeoParquet over HTTPS range requests.

Only row groups whose bbox statistics intersect the city bbox are downloaded.
No credentials are used: the bucket is public (anonymous S3 over HTTPS).

Usage:
  python overture_extract.py schema <theme> <type>
  python overture_extract.py extract <theme> <type> <city> <out.jsonl> [--cols a,b,c]

Writes one JSON object per row (geometry as WKT) plus a sidecar
<out>.provenance.json with release, file keys, row groups, bytes, timestamps.
"""
import io
import json
import os
import re
import sys
import time
from datetime import datetime, timezone

import pyarrow.parquet as pq
import requests
import shapely

BUCKET = "https://overturemaps-us-west-2.s3.us-west-2.amazonaws.com"
RELEASE = os.environ.get("OVERTURE_RELEASE", "2026-09-23.1")
CA = os.environ.get("REQUESTS_CA_BUNDLE", "/root/.ccr/ca-bundle.crt")

# Generous city bboxes (lon_min, lat_min, lon_max, lat_max); exact filtering
# against division polygons happens later, these only limit downloads.
CITY_BBOX = {
    "shymkent": (69.35, 42.10, 69.95, 42.55),
    "astana": (71.15, 50.95, 71.80, 51.35),
}

SESSION = requests.Session()
SESSION.verify = CA if os.path.exists(CA) else True
STATS = {"requests": 0, "bytes": 0}


class RangeFile(io.RawIOBase):
    """Minimal seekable read-only file over HTTP Range requests."""

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
        n = len(b)
        if self.pos >= self.size or n == 0:
            return 0
        end = min(self.pos + n, self.size) - 1
        for attempt in range(3):
            r = SESSION.get(self.url, headers={"Range": f"bytes={self.pos}-{end}"}, timeout=120)
            if r.status_code == 206:
                break
            time.sleep(2 * (attempt + 1))
        r.raise_for_status()
        data = r.content
        STATS["requests"] += 1
        STATS["bytes"] += len(data)
        b[: len(data)] = data
        self.pos += len(data)
        return len(data)


def list_keys(theme, typ):
    prefix = f"release/{RELEASE}/theme={theme}/type={typ}/"
    r = SESSION.get(f"{BUCKET}/?list-type=2&prefix={prefix}", timeout=60)
    r.raise_for_status()
    STATS["requests"] += 1
    return [
        (k, int(s))
        for k, s in re.findall(r"<Key>([^<]+\.parquet)</Key>.*?<Size>(\d+)</Size>", r.text)
    ]


def open_pf(key, size):
    return pq.ParquetFile(io.BufferedReader(RangeFile(f"{BUCKET}/{key}", size), buffer_size=1 << 20))


def bbox_stats(pf, rg):
    """Return (xmin, ymin, xmax, ymax) of a row group from bbox.* column stats."""
    md = pf.metadata.row_group(rg)
    vals = {}
    for c in range(md.num_columns):
        col = md.column(c)
        name = col.path_in_schema
        st = col.statistics
        if st is None or not st.has_min_max:
            continue
        if name == "bbox.xmin":
            vals["xmin"] = st.min
        elif name == "bbox.ymin":
            vals["ymin"] = st.min
        elif name == "bbox.xmax":
            vals["xmax"] = st.max
        elif name == "bbox.ymax":
            vals["ymax"] = st.max
    if len(vals) < 4:
        return None
    return vals["xmin"], vals["ymin"], vals["xmax"], vals["ymax"]


def intersects(a, b):
    return not (a[2] < b[0] or a[0] > b[2] or a[3] < b[1] or a[1] > b[3])


def to_jsonable(v):
    if isinstance(v, (bytes, bytearray)):
        return v.hex()
    if isinstance(v, dict):
        return {k: to_jsonable(x) for k, x in v.items()}
    if isinstance(v, list):
        return [to_jsonable(x) for x in v]
    if hasattr(v, "isoformat"):
        return v.isoformat()
    return v


def cmd_schema(theme, typ):
    keys = list_keys(theme, typ)
    pf = open_pf(*keys[0])
    print(json.dumps({"files": len(keys), "first": keys[0][0], "rows_first": pf.metadata.num_rows,
                      "row_groups_first": pf.metadata.num_row_groups}, ensure_ascii=False))
    print(pf.schema_arrow)
    print("STATS", STATS)


def cmd_extract(theme, typ, city, out, cols=None):
    bb = CITY_BBOX[city]
    started = datetime.now(timezone.utc).isoformat(timespec="seconds")
    keys = list_keys(theme, typ)
    prov = {"source": "Overture Maps Foundation", "bucket": BUCKET, "release": RELEASE,
            "theme": theme, "type": typ, "city": city, "query_bbox": bb,
            "started_utc": started, "files": []}
    n_out = 0
    with open(out, "w", encoding="utf-8") as fh:
        for key, size in keys:
            pf = open_pf(key, size)
            picked = [rg for rg in range(pf.metadata.num_row_groups)
                      if (s := bbox_stats(pf, rg)) is not None and intersects(s, bb)]
            entry = {"key": key, "size": size, "row_groups_total": pf.metadata.num_row_groups,
                     "row_groups_read": picked, "rows_kept": 0}
            if picked:
                names = pf.schema_arrow.names
                use = [c for c in (cols or names) if c in names]
                for rg in picked:
                    t = pf.read_row_group(rg, columns=use).to_pylist()
                    for row in t:
                        b = row.get("bbox")
                        if b and not intersects((b["xmin"], b["ymin"], b["xmax"], b["ymax"]), bb):
                            continue
                        if row.get("geometry") is not None:
                            row["geometry"] = shapely.from_wkb(row["geometry"]).wkt
                        fh.write(json.dumps(to_jsonable(row), ensure_ascii=False) + "\n")
                        entry["rows_kept"] += 1
                        n_out += 1
            prov["files"].append(entry)
            print(f"{key.split('/')[-1]}: rg {len(picked)}/{pf.metadata.num_row_groups}, kept {entry['rows_kept']}, "
                  f"bytes so far {STATS['bytes']}", file=sys.stderr)
    prov.update({"finished_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                 "rows_out": n_out, "http_requests": STATS["requests"], "bytes_downloaded": STATS["bytes"]})
    with open(out + ".provenance.json", "w", encoding="utf-8") as fh:
        json.dump(prov, fh, ensure_ascii=False, indent=1)
    print(json.dumps({k: prov[k] for k in ("rows_out", "http_requests", "bytes_downloaded")}))


if __name__ == "__main__":
    a = sys.argv[1:]
    if a[0] == "schema":
        cmd_schema(a[1], a[2])
    elif a[0] == "extract":
        cols = None
        if "--cols" in a:
            cols = a[a.index("--cols") + 1].split(",")
        cmd_extract(a[1], a[2], a[3], a[4], cols)
