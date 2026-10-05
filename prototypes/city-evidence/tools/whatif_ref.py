"""Reference for «Если добавить объект» (city-whatif-v1, research/round-7/FEATURE_SPEC.txt), stdlib only.

Same rules as web/whatif.js: haversine in metres, R = 6371008.8, input [lon, lat], intermediate value clamped
to [0, 1], no rounding; before = nearest source record of the category in the slice, after = min(before,
distance to the hypothetical object), delta = before - after (null when before is null); ties -> smaller ID.

Usage:
  python3 tools/whatif_ref.py           -> writes tests/expected_whatif.json (deterministic cases, both cities)
  python3 tools/whatif_ref.py --check   -> exit 1 if tests/expected_whatif.json differs from a fresh run
tests/whatif.cjs compares web/whatif.js against this file.
"""
import json
import math
import sys
from pathlib import Path

APP = Path(__file__).resolve().parent.parent
OUT = APP / "tests" / "expected_whatif.json"
R_EARTH = 6371008.8
CATEGORIES = ("school", "outpatient_clinic")


def haversine(lon1, lat1, lon2, lat2):
    r = math.pi / 180
    p1, p2 = lat1 * r, lat2 * r
    dp, dl = (lat2 - lat1) * r, (lon2 - lon1) * r
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    a = min(1.0, max(0.0, a))
    return 2 * R_EARTH * math.asin(math.sqrt(a))


def nearest(cands, lon, lat):
    best = None
    for p in cands:
        d = haversine(lon, lat, p["lon"], p["lat"])
        if best is None or d < best[1] or (d == best[1] and p["id"] < best[0]["id"]):
            best = (p, d)
    return best


def compute(places, category, points, proposed):
    if category not in CATEGORIES:
        raise ValueError("bad_category")
    if proposed and proposed["category"] != category:
        raise ValueError("bad_category")
    cands = sorted((p for p in places if p["group"] == category), key=lambda p: p["id"])
    rows = []
    for cp in points:
        nb = nearest(cands, cp["lon"], cp["lat"])
        before = nb[1] if nb else None
        dp = haversine(cp["lon"], cp["lat"], proposed["lon"], proposed["lat"]) if proposed else None
        if before is None:
            after, na = dp, (None if dp is None else "proposed")
        elif dp is None or dp >= before:
            after, na = before, "source"
        else:
            after, na = dp, "proposed"
        delta = before - after if before is not None and after is not None else None
        rows.append({"id": cp["id"], "before": before, "after": after, "delta": delta,
                     "nearest_before": nb[0]["id"] if nb else None, "nearest_after": na, "proposed_distance": dp})
    return {"category": category, "candidates": len(cands), "rows": rows}


def load_data():
    text = (APP / "web" / "data.js").read_text(encoding="utf-8")
    body = text[text.index("window.CITY_EVIDENCE =") + len("window.CITY_EVIDENCE ="):].strip()
    return json.loads(body[:-1] if body.endswith(";") else body)


def cases(data):
    """Deterministic points from the bbox, one QA-colocated coordinate, one point on a source record."""
    out = []
    for city in sorted(data["cities"]):
        c = data["cities"][city]
        w, s, e, n = c["bbox"]
        lerp = lambda fx, fy: (round(w + (e - w) * fx, 6), round(s + (n - s) * fy, 6))  # noqa: E731
        base = [lerp(0.5, 0.5), lerp(0.1, 0.1), lerp(0.9, 0.9), lerp(0.1, 0.9), lerp(0.9, 0.1)]
        coloc = {}
        for p in c["places"]:
            coloc.setdefault((p["lon"], p["lat"]), []).append(p["id"])
        qa = sorted(k for k, v in coloc.items() if len(v) >= 3)
        for cat in CATEGORIES:
            src = sorted((p for p in c["places"] if p["group"] == cat), key=lambda p: p["id"])
            pts = base + qa[:1] + [(src[0]["lon"], src[0]["lat"])]
            points = [{"id": f"P{i + 1}", "lon": lo, "lat": la} for i, (lo, la) in enumerate(pts)]
            for name, prop in [("none", None), ("near_P2", lerp(0.12, 0.12)), ("far_corner", lerp(0.99, 0.01)),
                               ("same_as_P1", pts[0])]:
                proposed = None if prop is None else {"id": "X1", "lon": prop[0], "lat": prop[1], "category": cat,
                                                      "kind": "hypothetical"}
                out.append({"city": city, "category": cat, "name": name, "points": points, "proposed": proposed,
                            "result": compute(c["places"], cat, points, proposed)})
    return out


def main():
    data = load_data()
    doc = {"generator": "tools/whatif_ref.py", "formula": "haversine:R=6371008.8", "cases": cases(data)}
    text = json.dumps(doc, ensure_ascii=False, indent=1) + "\n"
    if "--check" in sys.argv:
        ok = OUT.exists() and OUT.read_text(encoding="utf-8") == text
        print(("OK " if ok else "STALE ") + str(OUT.relative_to(APP)))
        return 0 if ok else 1
    with open(OUT, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)
    print(f"wrote {OUT.relative_to(APP)}: {len(doc['cases'])} cases")
    return 0


if __name__ == "__main__":
    sys.exit(main())
