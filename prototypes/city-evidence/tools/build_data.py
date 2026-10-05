"""Build web/data.js for the «Городские данные: Шымкент / Астана» demo from pinned K10 round-3 inputs.

Stdlib only, no network. Before reading, every K10 file is checked against package_manifest.json
(sha256 + bytes); a mismatch or a missing file aborts the build with a clear message.

Output: web/data.js  (window.CITY_EVIDENCE = {...}) — works both via file:// and via serve.py.
"""
import hashlib
import json
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


def sha256(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def load_manifest():
    mp = K10 / "package_manifest.json"
    if not mp.exists():
        raise InputError(f"нет файла {mp.relative_to(APP)} — запустите tools/copy_inputs.py")
    return json.loads(mp.read_text(encoding="utf-8"))


def load_layer(city, name, fmeta):
    path = K10 / fmeta["path"]
    if not path.exists():
        raise InputError(f"{city}/{name}: нет файла {path.relative_to(APP)}")
    if path.stat().st_size != fmeta["bytes"] or sha256(path) != fmeta["sha256"]:
        raise InputError(f"{city}/{name}: sha256/размер не совпадают с package_manifest.json")
    try:
        fc = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise InputError(f"{city}/{name}: повреждённый JSON ({e})")
    if len(fc.get("features", [])) != fmeta["features"]:
        raise InputError(f"{city}/{name}: число объектов не совпадает с манифестом")
    return fc


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
    }


def build():
    man = load_manifest()
    src_manifest = json.loads((APP / "source_manifest.json").read_text(encoding="utf-8"))
    k10_sha = next(x["sha"] for x in src_manifest["files"] if x["slot"] == "K10")
    cities = {}
    for city, cm in man["cities"].items():
        layers = {name: load_layer(city, name, fm) for name, fm in cm["files"].items()}
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
    return {
        "generated_by": "prototypes/city-evidence/tools/build_data.py",
        "inputs": {"k10_branch": "claude/save-work-handoff-j7pc05", "k10_sha": k10_sha,
                   "k10_data_commit": "602f0c0b6d5db741d20909082086982b3c812c07"},
        "groups": {g: {"sector": s, "label": l} for g, (s, l) in GROUPS.items()},
        "foot_access_labels": FOOT,
        "city_order": [c for c in ("shymkent", "astana") if c in cities],
        "cities": cities,
    }


def main():
    try:
        data = build()
    except (InputError, KeyError, StopIteration) as e:
        print(f"ОШИБКА входных данных: {e}", file=sys.stderr)
        return 2
    OUT.parent.mkdir(parents=True, exist_ok=True)
    txt = json.dumps(data, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    OUT.write_text("// GENERATED by tools/build_data.py from pinned K10 inputs — do not edit.\n"
                   f"window.CITY_EVIDENCE = {txt};\n", encoding="utf-8")
    for c in data["cities"].values():
        print(f"{c['key']}: {c['counts']['places']} объектов, {c['counts']['segments']} сегментов")
    print(f"wrote {OUT.relative_to(APP)} ({OUT.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
