"""K11 round 7: generate isolated city-whatif-v1 scenario fixtures (Cyrillic/Kazakh names and ids).

    python make_fixtures.py --app-root <copy of prototypes/city-evidence> --app-sha <SHA> [--out fixtures]

bbox and the K11 snapshot fingerprint come from <app-root>/web/data.js (see whatif_io.snapshot_fingerprint).
Writes the files and fixtures/MANIFEST.json (expected outcome per file, sha256, bytes). Bytes are written
with Path.write_bytes, so the result does not depend on the OS code page or newline translation.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
import unicodedata

sys.path.insert(0, str(Path(__file__).resolve().parent))
import whatif_io as W  # noqa: E402


def inside(bbox, fx, fy):
    return [round(bbox[0] + (bbox[2] - bbox[0]) * fx, 6), round(bbox[1] + (bbox[3] - bbox[1]) * fy, 6)]


def scenario(city, snap, bbox, category, ids, proposed_id, proposed_at=(0.5, 0.5)):
    pts = [{"id": pid, "lon": inside(bbox, 0.1 + 0.08 * i, 0.2 + 0.06 * i)[0],
            "lat": inside(bbox, 0.1 + 0.08 * i, 0.2 + 0.06 * i)[1]} for i, pid in enumerate(ids)]
    prop = None
    if proposed_id:
        lon, lat = inside(bbox, *proposed_at)
        prop = {"id": proposed_id, "lon": lon, "lat": lat, "category": category, "kind": "hypothetical"}
    return {"schema_version": W.SCHEMA, "city_id": city, "source_snapshot": snap, "category": category,
            "control_points": pts, "proposed_object": prop}


def jb(obj):
    return W.dumps(obj) if set(obj) == set(W.TOP_KEYS) else (
        json.dumps(obj, ensure_ascii=False, indent=1) + "\n").encode("utf-8")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--app-root", required=True)
    ap.add_argument("--app-sha", required=True)
    ap.add_argument("--out", default=str(Path(__file__).resolve().parent / "fixtures"))
    a = ap.parse_args()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    snap = {c: W.snapshot_fingerprint(a.app_root, c) for c in W.CITIES}
    bbox = {c: W.city_bbox(a.app_root, c) for c in W.CITIES}
    sh, ast = "shymkent", "astana"

    base_sh = scenario(sh, snap[sh], bbox[sh], "school", ["нүкте-1", "дүкен-2", "аялдама-3"], "жаңа-мектеп")
    base_as = scenario(ast, snap[ast], bbox[ast], "outpatient_clinic", ["точка-1"], "проект-поликлиника-ә",
                       proposed_at=(0.7, 0.3))
    ten = scenario(sh, snap[sh], bbox[sh], "school", [f"Т-{i:02d}" for i in range(1, 11)], None)

    cases = []  # (file name, bytes, expected, city, note)

    def add(name, data, expected, city, note=""):
        cases.append((unicodedata.normalize("NFC", name), data, expected, city, note))

    add("Шымкент_мектеп_жоба.json", W.dumps(base_sh), "accept", sh, "Kazakh ids, school, 3 points + project")
    add("Астана емхана ұсынысы.json", W.dumps(base_as), "accept", ast, "spaces + Kazakh in file name")
    add("Шымкент_без_проекта_10_точек.json", W.dumps(ten), "accept", sh, "max 10 points, proposed_object null")
    add("с_BOM_блокнот.json", b"\xef\xbb\xbf" + W.dumps(base_sh).replace(b"\n", b"\r\n"), "accept", sh,
        "UTF-8 BOM + CRLF as saved by Windows Notepad -> note utf8_bom_stripped")
    with_res = dict(base_sh, results={"distances": [{"id": "нүкте-1", "before": 1.0, "after": 0.5}], "delta": 999})
    add("с_результатами.json", jb(with_res), "accept", sh, "imported results are dropped, never trusted")

    text = W.dumps(base_sh).decode("utf-8")
    first_lon = json.dumps(base_sh["control_points"][0]["lon"])
    add("nan.json", text.replace(first_lon, "NaN", 1).encode("utf-8"), "E_NONFINITE", sh)
    add("infinity.json", text.replace(first_lon, "Infinity", 1).encode("utf-8"), "E_NONFINITE", sh)
    add("1e999.json", text.replace(first_lon, "1e999", 1).encode("utf-8"), "E_NONFINITE", sh)
    add("дубль_ключа.json", text.replace('"city_id": "shymkent",', '"city_id": "shymkent",\n "city_id": "astana",', 1)
        .encode("utf-8"), "E_DUPLICATE_KEY", sh)
    dup = json.loads(text)
    dup["control_points"][1]["id"] = dup["control_points"][0]["id"]
    add("дубль_id.json", W.dumps(dup), "E_DUPLICATE_ID", sh)
    add("чужой_срез.json", W.dumps(dict(base_sh, source_snapshot=snap[ast])), "E_SNAPSHOT", sh,
        "snapshot of the other city")
    add("чужой_город.json", jb(dict(base_sh, city_id="almaty")), "E_CITY", sh)
    out_box = json.loads(W.dumps(base_as).decode("utf-8"))
    out_box["control_points"][0]["lon"] = bbox[ast][2] + 0.01
    add("вне_квадрата_Астана.json", W.dumps(out_box), "E_OUTSIDE_BBOX", ast)
    eleven = scenario(sh, snap[sh], bbox[sh], "school", [f"Т-{i:02d}" for i in range(1, 12)], None)
    add("11_точек.json", W.dumps(eleven), "E_POINTS", sh)
    two = dict(base_sh, proposed_object=[base_sh["proposed_object"], dict(base_sh["proposed_object"], id="екінші")])
    add("два_проекта.json", jb(two), "E_MULTIPLE_PROJECTS", sh)
    url = json.loads(text)
    url["control_points"][0]["id"] = "https://example.org/x"
    add("url_в_id.json", W.dumps(url), "E_ID_FORBIDDEN", sh)
    nfd = json.loads(text)
    nfd["control_points"][0]["id"] = unicodedata.normalize("NFD", "дом-й")
    add("nfd_id.json", W.dumps(nfd), "E_ID_NOT_NFC", sh, "visually equal to NFC 'дом-й' but different code points")
    # Kazakh letters (ү, қ, ә ...) do not exist in cp1251 at all, so the ANSI-code-page case uses Russian ids
    ru = scenario(sh, snap[sh], bbox[sh], "school", ["точка-1", "магазин-2", "остановка-3"], "новая-школа")
    add("cp1251.json", W.dumps(ru).decode("utf-8").encode("cp1251"), "E_NOT_UTF8", sh,
        "Russian-only scenario saved in the Windows ANSI code page (Kazakh text cannot be encoded in cp1251)")
    # >256 KiB case is generated inside test_whatif_io.py (no 256 KiB blob in Git)
    add("версия_2.json", jb(dict(base_sh, schema_version="city-whatif-v2")), "E_VERSION", sh)
    wrong_cat = json.loads(text)
    wrong_cat["proposed_object"]["category"] = "outpatient_clinic"
    add("категория_проекта.json", W.dumps(wrong_cat), "E_CATEGORY", sh)
    add("лишнее_поле.json", jb(dict(base_sh, script="<script>alert(1)</script>")), "E_UNKNOWN_FIELD", sh)

    rows = []
    for name, data, expected, city, note in cases:
        (out / name).write_bytes(data)
        rows.append({"file": name, "expected": expected, "city_id": city, "bytes": len(data),
                     "sha256": hashlib.sha256(data).hexdigest(), "note": note})
    manifest = {"generated_by": "research/round-7-results/K11/make_fixtures.py",
                "app_sha": a.app_sha, "schema": W.SCHEMA,
                "snapshot_convention": "whatif_io.snapshot_fingerprint (K11 fixture convention, not BUILD API)",
                "cities": {c: {"source_snapshot": snap[c], "bbox": bbox[c]} for c in W.CITIES},
                "files": rows}
    (out / "MANIFEST.json").write_bytes((json.dumps(manifest, ensure_ascii=False, indent=1) + "\n").encode("utf-8"))
    print(f"{len(rows)} fixtures -> {out} (accept: {sum(r['expected'] == 'accept' for r in rows)})")


if __name__ == "__main__":
    main()
