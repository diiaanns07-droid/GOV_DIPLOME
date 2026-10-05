"""K06 round 5 REVIEW: audit of numbers and their labels in the city-evidence BUILD demo.

Re-runnable on any BUILD version:
  python3 audit_numbers.py --app-root <extracted prototypes/city-evidence> [--json out.json]
  python3 audit_numbers.py --url http://127.0.0.1:8765/ [--json out.json]     (serve.py serves web/)
With --url only web/ files are read (data.js, evidence.js, facts.js, app.js, index.html); checks that need
inputs/k10 are reported as SKIP. Standard library only; the network is used only for the given --url.

Every check stores the observed values and the file (with SHA256) they came from. Status:
  PASS  number and label agree with the data and the oracle;
  WARN  number correct, label/semantics weaker than it should be or a latent risk (not shown in UI yet);
  FAIL  wrong number or a label that claims more than the data (city registry, walking time, inside-square km);
  SKIP  input not available in this mode.
Exit code: 1 if any FAIL, else 0.

Scope: lengths (full geometry beyond the bbox vs length inside the square), straight-line distance vs
walking route, record counts vs number of city facilities. No transport forecast, no bus data.
"""
import argparse, hashlib, json, math, os, re, sys, urllib.request
from collections import Counter
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from geo_oracle import polyline_m, vincenty_m  # WGS84 Vincenty, copied from round-4 K06 @ 33684f9

WEB_FILES = ("data.js", "evidence.js", "facts.js", "app.js", "index.html")
LEN_REL_TOL = 0.005      # sphere vs ellipsoid, see geo_oracle
LEN_ROUND_M = 0.05       # data.js rounds length_m to 0.1 m
VERTEX_ROUND_M = 0.07    # data.js rounds coords to 1e-6 deg: <= 0.056 m (lat) / 0.035 m (lon) per vertex


class Src:
    def __init__(self, app_root=None, url=None):
        self.app_root, self.url, self.files = app_root, url, {}

    def web(self, name):
        if name not in self.files:
            if self.url:
                with urllib.request.urlopen(self.url.rstrip("/") + "/" + name, timeout=20) as r:
                    b = r.read()
                where = self.url.rstrip("/") + "/" + name
            else:
                where = os.path.join(self.app_root, "web", name)
                b = open(where, "rb").read()
            self.files[name] = {"where": where, "sha256": hashlib.sha256(b).hexdigest(), "text": b.decode("utf-8")}
        return self.files[name]

    def input_path(self, rel):
        return os.path.join(self.app_root, rel) if self.app_root else None

    def ref(self, name):
        f = self.web(name)
        return {"file": f["where"], "sha256": f["sha256"]}


def js_object(text, var):
    m = re.search(r"window\." + var + r"\s*=\s*(\{.*\})\s*;\s*$", text, re.S)
    if not m:
        raise ValueError(f"window.{var} not found")
    return json.loads(m.group(1))


def clip_to_bbox(coords, bb):
    """Liang-Barsky clip of each piece to bbox (lon/lat); returns list of clipped pieces [[p, q], ...]."""
    out = []
    for (x0, y0), (x1, y1) in zip([c[:2] for c in coords], [c[:2] for c in coords[1:]]):
        dx, dy = x1 - x0, y1 - y0
        t0, t1, ok = 0.0, 1.0, True
        for p, q in ((-dx, x0 - bb[0]), (dx, bb[2] - x0), (-dy, y0 - bb[1]), (dy, bb[3] - y0)):
            if p == 0:
                if q < 0:
                    ok = False; break
            else:
                t = q / p
                if p < 0:
                    t0 = max(t0, t)
                else:
                    t1 = min(t1, t)
                if t0 > t1:
                    ok = False; break
        if ok and t1 > t0:
            out.append([[x0 + t0 * dx, y0 + t0 * dy], [x0 + t1 * dx, y0 + t1 * dy]])
    return out


def inside(x, y, bb):
    return bb[0] <= x <= bb[2] and bb[1] <= y <= bb[3]


def app_haversine(lon1, lat1, lon2, lat2):
    """Python port of web/app.js haversine() (R = 6371008.8) to compare with the WGS84 oracle."""
    R, r = 6371008.8, math.pi / 180
    a = math.sin((lat2 - lat1) * r / 2) ** 2 + math.cos(lat1 * r) * math.cos(lat2 * r) * math.sin((lon2 - lon1) * r / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


def has(text, *needles):
    return {n: (n in text) for n in needles}


def audit(src):
    D = js_object(src.web("data.js")["text"], "CITY_EVIDENCE")
    E = js_object(src.web("evidence.js")["text"], "CITY_OBS")
    app, facts, html = src.web("app.js")["text"], src.web("facts.js")["text"], src.web("index.html")["text"]
    checks = []

    def add(cid, city, status, what, observed, sources):
        checks.append({"id": cid, "city": city, "status": status, "what": what, "observed": observed,
                       "source": [src.ref(s) if s in WEB_FILES else s for s in sources]})

    for city, c in D["cities"].items():
        bb, k = c["bbox"], c["counts"]
        obs = {o["indicator_id"]: o for o in E["cities"][city]["observations"]}
        # ADAPTER (BUILD r6): v1.2 build uses K05 r4 indicator ids. Provide the round-4 names as aliases derived from the
        # real observations (no value is invented): places.<g> = overture_place_records.<g>.conf_ge_0_0,
        # places.total = sum of those, registry.official_schools = official_registry.schools.
        if "places.total" not in obs:
            grp = {k.split(".")[1]: o for k, o in obs.items() if k.startswith("overture_place_records.") and k.endswith(".conf_ge_0_0")}
            for g, o in grp.items():
                obs["places." + g] = o
            any_o = next(iter(grp.values()))
            obs["places.total"] = dict(any_o, value=sum(o["value"] or 0 for o in grp.values()), indicator_id="places.total")
            if "official_registry.schools" in obs:
                obs["registry.official_schools"] = obs["official_registry.schools"]

        # N1 record counts are consistent across data.js and evidence.js
        by_g = dict(Counter(p["group"] for p in c["places"]))
        ok = (k["places"] == len(c["places"]) == obs["places.total"]["value"] and k["places_by_group"] == by_g
              and all(obs["places." + g]["value"] == n for g, n in by_g.items()))
        add("N1_record_counts", city, "PASS" if ok else "FAIL",
            "counts.places / places_by_group = len(places) = K05 observation places.*",
            {"places": k["places"], "by_group": by_g, "evidence_total": obs["places.total"]["value"],
             "evidence_unit": obs["places.total"].get("unit"), "evidence_kind": obs["places.total"]["kind"]},
            ["data.js", "evidence.js"])

        # N2 count labels say "records in the slice", never "facilities of the city"
        # ADAPTER: label strings of the v1.2 build (same meaning: records of the square, not city facilities)
        lab = has(app, "в полном ответе запроса по квадрату", "не реестр города") | has(html, "не число всех школ города") | has(facts, " в квадрате", "Выбранные категории в квадрате")
        bad = re.findall(r"(школ[а-я]* (?:в )?город[а-я]*|объектов города|всего в городе)", app + facts)
        bad = [b for b in bad if "не число всех школ города" not in html or b not in ("школ города",)]
        cov = obs["places.total"].get("coverage") or {}
        # ADAPTER: round 5 (BUILD r5 A3) made the square count a complete query result (coverage.complete=true) and moved
        # "how many in the city" to a separate unknown observation. Invariant kept: the city total is never given as a number.
        city_total = next((o for o in E["cities"][city]["observations"] if o["geo_unit_id"] == "kz." + city
                           and o["indicator_id"].endswith("city_total")), None)
        city_unknown = city_total is not None and city_total["value"] is None and city_total.get("missing_reason") is not None
        status = "PASS" if all(lab.values()) and not bad and city_unknown else "FAIL"
        add("N2_count_labels", city, status, "count labels: records of a 2x2 km slice, not city facilities",
            {"label_strings_present": lab, "claims_city_total": bad, "coverage_complete": cov.get("complete"), "city_total_unknown": city_unknown,
             "coverage_scope": cov.get("scope")}, ["app.js", "index.html", "facts.js", "evidence.js"])

        # N3 unknowns stay null (not 0)
        nulls = {i: (obs[i]["value"], obs[i]["kind"]) for i in ("capacity.school_places", "registry.official_schools", "population.children")}
        zeros = {g: n for g, n in by_g.items() if n == 0}
        add("N3_unknown_not_zero", city, "PASS" if all(v is None for v, _ in nulls.values()) and not zeros else "FAIL",
            "capacity / official registry / population are null (unknown), not 0",
            {"values_kind": nulls, "zero_groups": zeros}, ["evidence.js"])

        # N4 segment count and edge crossing recomputed from coords
        segs = c["segments"]
        cross = [s for s in segs if not all(inside(x, y, bb) for x, y in s["coords"])]
        flag_bad = sum((s in cross) != bool(s["crosses_edge"]) for s in segs)
        add("N4_segments_edge", city, "PASS" if k["segments"] == len(segs) and k["segments_crossing_edge"] == len(cross) and not flag_bad else "FAIL",
            "segment count and 'crosses edge' flag recomputed from coordinates vs bbox",
            {"segments": k["segments"], "crossing_edge_stated": k["segments_crossing_edge"], "crossing_edge_recomputed": len(cross),
             "flag_mismatches": flag_bad}, ["data.js"])

        # N5 road km: full geometry vs inside the square
        full = sum(polyline_m(s["coords"]) for s in segs)
        inside_m = sum(polyline_m(p) for s in segs for p in clip_to_bbox(s["coords"], bb))
        outside_cross = [(1 - sum(polyline_m(p) for p in clip_to_bbox(s["coords"], bb)) / polyline_m(s["coords"])) for s in cross]
        shown = [f for f in ("app.js", "facts.js", "index.html") if "road_km" in src.web(f)["text"]]
        # if a km total is displayed, the displaying file must say that it includes geometry beyond the edge
        label_full = {f: any(x in src.web(f)["text"] for x in ("за краем", "за край квадрата", "вся геометрия")) for f in shown}
        status = "FAIL" if shown and not all(label_full.values()) else ("WARN" if not shown else "PASS")
        add("N5_road_km_full_vs_inside", city, status,
            "road_km_full_geometry includes parts of edge-crossing segments outside the square; not displayed in UI",
            {"stated_road_km_full_geometry": k.get("road_km_full_geometry"), "oracle_full_km": round(full / 1000, 3),
             "oracle_inside_square_km": round(inside_m / 1000, 3), "outside_km": round((full - inside_m) / 1000, 3),
             "outside_share": round(1 - inside_m / full, 4), "max_outside_share_of_one_crossing_segment": round(max(outside_cross or [0]), 3),
             "displayed_in": shown, "display_label_mentions_beyond_edge": label_full,
             "note": "if a km total is ever shown it must say 'вся геометрия, в т.ч. за краем' or use the inside value"},
            ["data.js", "app.js", "facts.js", "index.html"])

        # N6 per-segment length_m vs oracle, label of the road card
        worst, nbad = 0.0, 0
        for s in segs:
            o = polyline_m(s["coords"])
            d = abs(s["length_m"] - o)
            nbad += d > LEN_REL_TOL * o + LEN_ROUND_M + VERTEX_ROUND_M * len(s["coords"])  # error sources add up
            worst = max(worst, d / o if o else 0)
        rel = sorted(s["length_m"] / polyline_m(s["coords"]) - 1 for s in segs if polyline_m(s["coords"]) > 10)
        card = has(app, "(вся линия, выходит за квадрат)", "геодезическая, K10")
        status = "FAIL" if nbad or not card["(вся линия, выходит за квадрат)"] else ("WARN" if card["геодезическая, K10"] else "PASS")
        add("N6_segment_length_label", city, status,
            "road card length = whole line (marked when it leaves the square); 'геодезическая' although K10 uses a sphere",
            {"segments_outside_tolerance": nbad, "max_rel_diff": round(worst, 5), "median_rel_diff_ge10m": round(rel[len(rel) // 2], 5),
             "label_strings": card,
             "note": "K10 k10_length_m = haversine on a sphere R=6371008.8 (K06 round 4); WGS84 differs by -0.07..-0.18 % median"},
            ["data.js", "app.js"])

        # N7 straight-line distance: formula vs oracle and labels vs walking route
        pts = [(p["lon"], p["lat"]) for p in c["places"]]
        corners = [(bb[0], bb[1]), (bb[2], bb[3]), (bb[0], bb[3]), (bb[2], bb[1])]
        pairs = [(a, b) for a in corners for b in pts[:20]]
        errs = [abs(app_haversine(*a, *b) - vincenty_m(*a, *b)) / vincenty_m(*a, *b) for a, b in pairs]
        lab = has(app, "По прямой", "нижняя граница пешего пути", "не время в пути и не доступность") | has(html, "расстояния по прямой")
        walk = re.findall(r"(?:\$\{[^}]+\}|\d+)\s*(?:мин\b|минут)", app + facts + html)
        status = "PASS" if max(errs) <= LEN_REL_TOL and all(lab.values()) and not walk else "FAIL"
        add("N7_straight_line_distance", city, status,
            "distance from a point: haversine 'по прямой', explicitly a lower bound of the walking route; no minutes",
            {"pairs": len(pairs), "max_rel_diff_vs_wgs84": round(max(errs), 5), "label_strings": lab, "walking_time_strings": walk},
            ["app.js", "index.html", "facts.js"])

        # N8 provenance of lengths and counts against inputs/k10 (app-root only)
        if src.app_root:
            try:
                man = json.load(open(src.input_path("inputs/k10/package_manifest.json"), encoding="utf-8"))
                cm = man["cities"][city]
                bad_sha, segs_in, places_in = [], None, None
                for name, fm in cm["files"].items():
                    p = src.input_path("inputs/k10/" + fm["path"])
                    if hashlib.sha256(open(p, "rb").read()).hexdigest() != fm["sha256"]:
                        bad_sha.append(name)
                sg = json.load(open(src.input_path("inputs/k10/" + cm["files"]["segments"]["path"]), encoding="utf-8"))["features"]
                pl = json.load(open(src.input_path("inputs/k10/" + cm["files"]["places_social"]["path"]), encoding="utf-8"))["features"]
                kl = {f["id"]: f["properties"]["k10_length_m"] for f in sg if f["properties"]["subtype"] == "road"}
                len_bad = sum(abs(round(kl[s["id"]], 1) - s["length_m"]) > 1e-9 for s in segs)
                ok = not bad_sha and not len_bad and len(pl) == k["places"] and len(kl) == k["segments"] and bb == cm["bbox"]
                add("N8_provenance_k10", city, "PASS" if ok else "FAIL",
                    "data.js counts / lengths / bbox equal pinned inputs/k10 (sha256 vs package_manifest)",
                    {"sha_mismatch": bad_sha, "length_m_mismatch": len_bad, "places_in_k10": len(pl), "roads_in_k10": len(kl)},
                    ["data.js", "inputs/k10/package_manifest.json"])
            except FileNotFoundError as e:
                add("N8_provenance_k10", city, "SKIP", "inputs/k10 missing", {"error": str(e)}, [])
        else:
            add("N8_provenance_k10", city, "SKIP", "--url mode: inputs/k10 is not served", {}, [])
    return checks


def main(argv=None):
    ap = argparse.ArgumentParser(description="K06 round-5 audit of numbers and labels in the city-evidence demo")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--app-root"); g.add_argument("--url")
    ap.add_argument("--json")
    a = ap.parse_args(argv)
    src = Src(a.app_root, a.url)
    checks = audit(src)
    rep = {"target": a.app_root or a.url, "files": {n: {"where": f["where"], "sha256": f["sha256"]} for n, f in src.files.items()},
           "summary": dict(Counter(c["status"] for c in checks)), "checks": checks}
    if a.app_root and os.path.exists(os.path.join(a.app_root, "_extract_manifest.json")):
        rep["extracted_from_commit"] = json.load(open(os.path.join(a.app_root, "_extract_manifest.json")))["commit"]
    txt = json.dumps(rep, ensure_ascii=False, indent=1)
    if a.json:
        open(a.json, "w", encoding="utf-8").write(txt + "\n")
    for c in checks:
        print(f"{c['status']:4} {c['city']:9} {c['id']}")
    print(rep["summary"])
    return 1 if any(c["status"] == "FAIL" for c in checks) else 0


if __name__ == "__main__":
    sys.exit(main())
