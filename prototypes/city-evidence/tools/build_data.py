"""Build web/data.js for the «Городские данные: Шымкент / Астана» demo from pinned K10 round-3 inputs.

Stdlib only, no network. Before reading, every K10 file is checked against package_manifest.json
(sha256 + bytes); a mismatch or a missing file aborts the build with a clear message.

Output: web/data.js  (window.CITY_EVIDENCE = {...}) — works both via file:// and via serve.py.
"""
import hashlib
import json
import math
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
APP = HERE.parent
K10 = APP / "inputs" / "k10"
OUT = APP / "web" / "data.js"

CITY_LABEL = {"shymkent": ("Шымкент", "KZ-79"), "astana": ("Астана", "KZ-71")}
GROUPS = {
    "school": ("education", "Школа"),
    "preschool": ("education", "Детский сад"),
    "college_university": ("education", "Колледж / вуз"),
    "hospital": ("health", "Больница"),
    "outpatient_clinic": ("health", "Поликлиника"),
    "pharmacy": ("health", "Аптека"),
    "government_office": ("government", "Госучреждение"),
}
FOOT = {
    "unknown": "правил для пешеходов нет (это не разрешение)",
    "conditional": "есть условия (чаще одностороннее движение)",
    "denied": "явный запрет для пешеходов",
    "allowed": "явное разрешение для пешеходов",
}


class InputError(RuntimeError):
    pass


def rel(p):
    try:
        return p.relative_to(APP)
    except ValueError:
        return p


def sha256(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


SOURCE_MANIFEST = APP / "source_manifest.json"
FOOT_CLASSES = {"unknown", "conditional", "denied", "allowed"}


def loads_strict(text, where):
    """json.loads without NaN/Infinity tokens, without overflow to inf (1e999) and without duplicate keys."""
    def no_constant(tok):
        raise ValueError(f"токен {tok}")

    def finite_float(tok):
        v = float(tok)
        if not math.isfinite(v):
            raise ValueError(f"{tok} переполняется до {v}")
        return v

    def unique(pairs):
        out = {}
        for k, v in pairs:
            if k in out:
                raise ValueError(f"повтор ключа {k!r}")
            out[k] = v
        return out
    try:
        return json.loads(text, parse_constant=no_constant, parse_float=finite_float, object_pairs_hook=unique)
    except ValueError as e:
        raise InputError(f"SEMANTIC: {where}: недопустимый JSON ({e})") from None


def anchored_sha(rel_path):
    """sha256 recorded for a copied input in source_manifest.json (the trust anchor written by copy_inputs.py)."""
    if not SOURCE_MANIFEST.exists():
        raise InputError("INTEGRITY: нет файла source_manifest.json (якорь входов)")
    sm = loads_strict(SOURCE_MANIFEST.read_text(encoding="utf-8"), "source_manifest.json")
    want = [f["sha256"] for f in sm["files"] if f["copied_to"] == rel_path]
    if len(want) != 1:
        raise InputError(f"INTEGRITY: {rel_path} не записан в source_manifest.json")
    return want[0]


def load_manifest():
    mp = K10 / "package_manifest.json"
    if not mp.exists():
        raise InputError(f"INTEGRITY: нет файла {rel(mp)} — запустите tools/copy_inputs.py")
    if K10 == APP / "inputs" / "k10" and sha256(mp) != anchored_sha("inputs/k10/package_manifest.json"):
        raise InputError("INTEGRITY: package_manifest.json не совпадает с sha256 в source_manifest.json")
    return loads_strict(mp.read_text(encoding="utf-8"), "package_manifest.json")


def _finite(*vals):
    return all(isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v) for v in vals)


def check_layer(city, name, fc, man, cm):
    """Semantic checks of one K10 layer; raises InputError('SEMANTIC: ...') before anything is written."""
    w = f"{city}/{name}"
    if fc.get("city") != city or fc.get("release") != man.get("release") or fc.get("bbox") != cm["bbox"]:
        raise InputError(f"SEMANTIC: {w}: заголовок (city/release/bbox) {fc.get('city')}/{fc.get('release')}/{fc.get('bbox')} "
                         f"≠ манифесту {city}/{man.get('release')}/{cm['bbox']}")
    bb = cm["bbox"]
    seen = set()
    for f in fc["features"]:
        fid, p, g = f.get("id"), f.get("properties") or {}, f.get("geometry") or {}
        if fid in seen:
            raise InputError(f"SEMANTIC: {w}: повтор id {fid}")
        seen.add(fid)
        if fid != p.get("overture_id"):
            raise InputError(f"SEMANTIC: {w}: id {fid} ≠ overture_id")
        coords = g.get("coordinates")
        pts = [coords] if g.get("type") == "Point" else (coords or [])
        if not pts or not all(isinstance(c, list) and len(c) >= 2 and _finite(c[0], c[1]) for c in pts):
            raise InputError(f"SEMANTIC: {w}: {fid}: координаты отсутствуют или не конечны")
        if name == "places_social":
            x, y = coords[:2]
            if p.get("city") != city or not (bb[0] <= x <= bb[2] and bb[1] <= y <= bb[3]):
                raise InputError(f"SEMANTIC: {w}: {fid}: объект другого города или вне квадрата ({x}, {y})")
            if p.get("k10_group") not in GROUPS:
                raise InputError(f"SEMANTIC: {w}: {fid}: неизвестная группа {p.get('k10_group')!r}")
            c = p.get("confidence")
            if c is not None and not (_finite(c) and 0 <= c <= 1):
                raise InputError(f"SEMANTIC: {w}: {fid}: confidence {c!r} вне [0, 1]")
        elif name == "segments":
            if not (_finite(p.get("k10_length_m")) and p["k10_length_m"] >= 0):
                raise InputError(f"SEMANTIC: {w}: {fid}: k10_length_m {p.get('k10_length_m')!r} не конечно или < 0")
            if p.get("subtype") == "road" and p.get("k10_foot_access") not in FOOT_CLASSES:
                raise InputError(f"SEMANTIC: {w}: {fid}: k10_foot_access {p.get('k10_foot_access')!r}")


def load_layer(city, name, fmeta, man, cm):
    path = K10 / fmeta["path"]
    if not path.exists():
        raise InputError(f"INTEGRITY: {city}/{name}: нет файла {rel(path)}")
    if path.stat().st_size != fmeta["bytes"] or sha256(path) != fmeta["sha256"]:
        raise InputError(f"INTEGRITY: {city}/{name}: sha256/размер не совпадают с package_manifest.json")
    fc = loads_strict(path.read_text(encoding="utf-8"), f"{city}/{name}")
    if len(fc.get("features", [])) != fmeta["features"]:
        raise InputError(f"INTEGRITY: {city}/{name}: число объектов не совпадает с манифестом")
    check_layer(city, name, fc, man, cm)
    return fc


ATTR = APP / "web" / "attribution" / "attribution.json"


def load_attribution(man):
    """Per-city provider list from K08 r4 attribution.json (built from records' sources[]).

    The file header `attribution` of K10 files names OSM/Overture only and does not match the records
    (K08 F1/F2); the UI must use this list. Each K08 entry must refer to the exact K10 file (sha256)."""
    if not ATTR.exists():
        raise InputError(f"INTEGRITY: нет файла {rel(ATTR)} (K08 атрибуция)")
    att = loads_strict(ATTR.read_text(encoding="utf-8"), "attribution.json")
    want = {f"data/{c}/{n}.geojson": fm["sha256"] for c, cm in man["cities"].items()
            for n, fm in ((k, v) for k, v in cm["files"].items())}
    out = {c: [] for c in man["cities"]}
    for f in att["files"]:
        if want.get(f["file"]) != f["sha256"]:
            raise InputError(f"INTEGRITY: атрибуция K08 относится к другому файлу: {f['file']}")
        for pv in f["providers"]:
            item = {"dataset": pv["dataset"], "license": pv["license"], "layer": f["file"].split("/")[-1].split(".")[0]}
            if item not in out[f["city"]]:
                out[f["city"]].append(item)
    return out


def r6(x):
    return round(x, 6)


def place_rec(f):
    p = f["properties"]
    lon, lat = f["geometry"]["coordinates"][:2]
    sector, label = GROUPS[p["k10_group"]]
    addr = "; ".join(a.get("freeform") or "" for a in (p.get("addresses") or []) if a.get("freeform")) or None
    return {
        "id": f["id"], "lon": r6(lon), "lat": r6(lat),
        "name": p.get("name_primary"), "group": p["k10_group"], "group_label": label, "sector": sector,
        "category": p.get("basic_category"), "confidence": round(p["confidence"], 3) if p.get("confidence") is not None else None,
        "address": addr, "operating_status": p.get("operating_status"),
        "overture_version": p.get("overture_version"),
        "sources": [{"dataset": s.get("dataset"), "license": s.get("license"), "record_id": s.get("record_id"),
                     "update_time": s.get("update_time")} for s in (p.get("sources") or []) if s.get("property", "") == ""],
    }


def seg_rec(f):
    p = f["properties"]
    src = next((s for s in (p.get("sources") or []) if s.get("property", "") == ""), {}) or {}
    return {
        "id": f["id"], "coords": [[r6(x), r6(y)] for x, y, *_ in f["geometry"]["coordinates"]],
        "class": p.get("class"), "subclass": p.get("subclass"), "name": p.get("name_primary"),
        "length_m": round(p["k10_length_m"], 1), "foot_access": p["k10_foot_access"],
        "flags": p.get("k10_flags") or [], "crosses_edge": p["k10_crosses_bbox_edge"],
        "connectors": len(p.get("connectors") or []),
        "record_id": src.get("record_id"), "license": src.get("license"), "update_time": src.get("update_time"),
        "dataset": src.get("dataset"),
    }


def build():
    man = load_manifest()
    src_manifest = json.loads((APP / "source_manifest.json").read_text(encoding="utf-8"))
    k10_sha = next(x["sha"] for x in src_manifest["files"] if x["slot"] == "K10")
    cities = {}
    for city, cm in man["cities"].items():
        layers = {name: load_layer(city, name, fm, man, cm) for name, fm in cm["files"].items()}
        places = [place_rec(f) for f in layers["places_social"]["features"]]
        segs = [seg_rec(f) for f in layers["segments"]["features"] if f["properties"]["subtype"] == "road"]
        label, iso = CITY_LABEL[city]
        cities[city] = {
            "key": city, "label": label, "iso": iso, "bbox": cm["bbox"],
            "release": man["release"], "retrieved_utc": cm.get("finished_utc"),
            "attribution": layers["places_social"].get("attribution"),
            "kind": layers["places_social"].get("kind"),
            "places": places, "segments": segs,
            "counts": {
                "places": len(places),
                "places_by_group": dict(Counter(p["group"] for p in places)),
                "segments": len(segs),
                "segments_crossing_edge": sum(s["crosses_edge"] for s in segs),
                "road_km_full_geometry": round(sum(s["length_m"] for s in segs) / 1000, 2),
                "foot_access": dict(Counter(s["foot_access"] for s in segs)),
                "connectors": cm["files"]["connectors"]["features"],
            },
            "files": {name: {"path": "inputs/k10/" + fm["path"], "sha256": fm["sha256"]} for name, fm in cm["files"].items()},
        }
    attribution = load_attribution(man)
    for city, c in cities.items():
        c["attribution"] = attribution[city]
    return {
        "generated_by": "prototypes/city-evidence/tools/build_data.py",
        "inputs": {"k10_branch": "claude/save-work-handoff-j7pc05", "k10_sha": k10_sha,
                   "k10_data_commit": "602f0c0b6d5db741d20909082086982b3c812c07"},
        "groups": {g: {"sector": s, "label": l} for g, (s, l) in GROUPS.items()},
        "foot_access_labels": FOOT,
        "city_order": [c for c in ("shymkent", "astana") if c in cities],
        "cities": cities,
    }


def render_text(data):
    txt = json.dumps(data, ensure_ascii=False, separators=(",", ":"), sort_keys=True, allow_nan=False)
    return ("// GENERATED by tools/build_data.py from pinned K10 inputs — do not edit.\n"
            f"window.CITY_EVIDENCE = {txt};\n")


def main():
    try:
        data = build()
    except (InputError, KeyError, StopIteration) as e:
        print(f"ОШИБКА входных данных: {e}", file=sys.stderr)
        return 2
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(render_text(data), encoding="utf-8", newline="\n")
    for c in data["cities"].values():
        print(f"{c['key']}: {c['counts']['places']} объектов, {c['counts']['segments']} сегментов")
    print(f"wrote {OUT.relative_to(APP)} ({OUT.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
