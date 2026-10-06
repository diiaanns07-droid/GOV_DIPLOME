"""K10 round 10: pinned Overture Maps extract for one small bbox (anonymous public S3, HTTP Range).

Adapted from research/next-round/K10/scripts/overture_extract.py (same role, earlier round): only row groups whose
bbox statistics intersect the query box are read; rows are kept if their own bbox intersects the box.
Personal contact columns (phones, emails, socials) are never requested.

Usage (repo root, a Python with pyarrow, shapely, requests):
  python overture_bbox.py <theme> <type> <west> <south> <east> <north> <out.jsonl> [--cols a,b,c] [--release R]
Writes <out.jsonl> (geometry as WKT) and <out.jsonl>.provenance.json (release, keys, row groups, bytes, times, sha256).
"""
import hashlib
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
CA = os.environ.get("REQUESTS_CA_BUNDLE", "/root/.ccr/ca-bundle.crt")
NEVER = {"phones", "emails", "socials"}
S = requests.Session()
S.verify = CA if os.path.exists(CA) else True
STATS = {"requests": 0, "bytes": 0}


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
        n = len(b)
        if self.pos >= self.size or n == 0:
            return 0
        end = min(self.pos + n, self.size) - 1
        for attempt in range(4):
            r = S.get(self.url, headers={"Range": f"bytes={self.pos}-{end}"}, timeout=120)
            if r.status_code == 206:
                break
            time.sleep(2 ** (attempt + 1))
        r.raise_for_status()
        data = r.content
        STATS["requests"] += 1
        STATS["bytes"] += len(data)
        b[: len(data)] = data
        self.pos += len(data)
        return len(data)


def list_keys(release, theme, typ):
    prefix = f"release/{release}/theme={theme}/type={typ}/"
    out, token = [], None
    while True:
        url = f"{BUCKET}/?list-type=2&prefix={prefix}" + (f"&continuation-token={requests.utils.quote(token)}" if token else "")
        r = S.get(url, timeout=60)
        r.raise_for_status()
        STATS["requests"] += 1
        out += [(k, int(s)) for k, s in re.findall(r"<Key>([^<]+\.parquet)</Key>.*?<Size>(\d+)</Size>", r.text)]
        m = re.search(r"<NextContinuationToken>([^<]+)</NextContinuationToken>", r.text)
        if not m:
            return out
        token = m.group(1)


def rg_bbox(pf, rg):
    md, v = pf.metadata.row_group(rg), {}
    for c in range(md.num_columns):
        col = md.column(c)
        st = col.statistics
        if st is None or not st.has_min_max:
            continue
        name = col.path_in_schema
        if name in ("bbox.xmin", "bbox.ymin"):
            v[name[5:]] = st.min
        elif name in ("bbox.xmax", "bbox.ymax"):
            v[name[5:]] = st.max
    return (v["xmin"], v["ymin"], v["xmax"], v["ymax"]) if len(v) == 4 else None


def hit(a, b):
    return not (a[2] < b[0] or a[0] > b[2] or a[3] < b[1] or a[1] > b[3])


def plain(v):
    if isinstance(v, (bytes, bytearray)):
        return v.hex()
    if isinstance(v, dict):
        return {k: plain(x) for k, x in v.items()}
    if isinstance(v, list):
        return [plain(x) for x in v]
    if isinstance(v, tuple):
        return [plain(x) for x in v]
    if hasattr(v, "isoformat"):
        return v.isoformat()
    return v


def main(a):
    cols = a[a.index("--cols") + 1].split(",") if "--cols" in a else None
    release = a[a.index("--release") + 1] if "--release" in a else "2026-09-23.1"
    theme, typ, w, s, e, n, out = a[0], a[1], *map(float, a[2:6]), a[6]
    box = (w, s, e, n)
    prov = {"source": "Overture Maps Foundation", "bucket": BUCKET, "release": release, "theme": theme, "type": typ,
            "query_bbox": list(box), "started_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "excluded_columns": sorted(NEVER), "files": []}
    rows = 0
    with open(out, "w", encoding="utf-8") as fh:
        for key, size in list_keys(release, theme, typ):
            pf = pq.ParquetFile(io.BufferedReader(RangeFile(f"{BUCKET}/{key}", size), buffer_size=1 << 20))
            picked = [rg for rg in range(pf.metadata.num_row_groups) if (b := rg_bbox(pf, rg)) and hit(b, box)]
            ent = {"key": key, "size": size, "row_groups_total": pf.metadata.num_row_groups, "row_groups_read": picked, "rows_kept": 0}
            if picked:
                names = pf.schema_arrow.names
                use = [c for c in (cols or names) if c in names and c not in NEVER]
                if "bbox" not in use:
                    use.append("bbox")
                for rg in picked:
                    for row in pf.read_row_group(rg, columns=use).to_pylist():
                        b = row["bbox"]
                        if not hit((b["xmin"], b["ymin"], b["xmax"], b["ymax"]), box):
                            continue
                        if row.get("geometry") is not None:
                            row["geometry"] = shapely.from_wkb(row["geometry"]).wkt
                        fh.write(json.dumps(plain(row), ensure_ascii=False, sort_keys=True) + "\n")
                        ent["rows_kept"] += 1
                        rows += 1
            prov["files"].append(ent)
            print(f"{key.rsplit('/', 1)[-1]}: rg {len(picked)}/{pf.metadata.num_row_groups} kept {ent['rows_kept']} bytes {STATS['bytes']}", file=sys.stderr)
    prov.update({"finished_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"), "rows_out": rows,
                 "http_requests": STATS["requests"], "bytes_downloaded": STATS["bytes"],
                 "output_sha256": hashlib.sha256(open(out, "rb").read()).hexdigest()})
    prov["files"] = [f for f in prov["files"] if f["row_groups_read"]]
    with open(out + ".provenance.json", "w", encoding="utf-8") as fh:
        json.dump(prov, fh, ensure_ascii=False, indent=1)
    print(json.dumps({k: prov[k] for k in ("rows_out", "http_requests", "bytes_downloaded", "output_sha256")}))


if __name__ == "__main__":
    main(sys.argv[1:])
