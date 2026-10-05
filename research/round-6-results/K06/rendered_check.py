"""K06 round 5: verify RENDERED numbers and labels of the city-evidence demo (what the user sees).

  python3 rendered_check.py --app-root <extracted prototypes/city-evidence> [--json out.json]
  python3 rendered_check.py --url http://127.0.0.1:8765/ [--json out.json]
Needs Node + Playwright (global; NODE_PATH=$(npm root -g)). Runs rendered_labels.cjs, then checks:
  R1 slice card: "Записей объектов N в срезе", "не реестр города", "Сегментов дорог S (из них M выходят за край)"
     with N, S, M recomputed from the arrays the page loaded (M from coordinates vs bbox);
  R2 road card of the longest edge-crossing segment shows the whole-line length + "(вся линия, выходит за квадрат)";
     inside-square length is recorded for comparison; the inner segment card has no such marker;
  R3 point card: "По прямой" column, lower-bound warning, distances vs WGS84 oracle (shown rounding + 0.5 %),
     rows sorted by distance;
  R4 whole rendered text: no walking minutes, no "в городе"/"всего в городе" claims for counts;
  R5 table count and banner speak of records of the slice.
Exit 1 if any FAIL.
"""
import argparse, json, os, re, subprocess, sys
from collections import Counter
from pathlib import Path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from geo_oracle import polyline_m, vincenty_m
from audit_numbers import clip_to_bbox, affirmative_claims, SCOPE_PHRASES

HERE = Path(__file__).resolve().parent


def parse_len(s):
    """'1,23 км' / '456 м' -> metres, and the rounding step of that display."""
    m = re.search(r"([\d ,]+)\s*(км|м)\b", s)
    v = float(m.group(1).replace(" ", "").replace(",", "."))
    return (v * 1000, 5.0) if m.group(2) == "км" else (v, 0.5)


def fmt_m(m):
    return f"{m / 1000:.2f}".replace(".", ",") + " км" if m >= 1000 else f"{round(m)} м"


def run(target):
    env = dict(os.environ)
    if "NODE_PATH" not in env:
        env["NODE_PATH"] = subprocess.check_output(["npm", "root", "-g"], text=True).strip()
    out = subprocess.run(["node", str(HERE / "rendered_labels.cjs"), target], capture_output=True, text=True, env=env, timeout=180)
    if out.returncode:
        raise RuntimeError(out.stderr[-2000:])
    return json.loads(out.stdout)


def check(obs):
    checks = []

    def add(cid, city, ok, observed, warn=False):
        checks.append({"id": cid, "city": city, "status": "PASS" if ok else ("WARN" if warn else "FAIL"), "observed": observed})

    for city, r in obs["cities"].items():
        d, sl = r["data"], r["slice"]
        # round-6 adapter: the count label may be "N в срезе" (0bf27de) or "N в полном ответе запроса по квадрату" (064ed25);
        # either way it must carry a slice scope phrase
        m1 = re.search(r"Записей объектов\s*(\d+) ([^\n]*?)(?:не реестр города|$)", sl)
        if m1 and not any(x in m1.group(2) for x in SCOPE_PHRASES):
            m1 = None
        m2 = re.search(r"Сегментов дорог\s*(\d+) \(из них (\d+) выходят за край\)", sl)
        ok = bool(m1 and m2) and int(m1.group(1)) == d["places"] and int(m2.group(1)) == d["segments"] \
            and int(m2.group(2)) == d["crossing"] and "не реестр города" in sl
        add("R1_slice_card", city, ok, {"places_shown": m1 and int(m1.group(1)), "places_data": d["places"],
                                        "segments_shown": m2 and int(m2.group(1)), "segments_data": d["segments"],
                                        "crossing_shown": m2 and int(m2.group(2)), "crossing_recomputed": d["crossing"],
                                        "not_registry_label": "не реестр города" in sl, "km_shown_in_slice": bool(re.search(r"\d\s*км", sl))})

        cs, card = d["cross_seg"], r["cross_seg_card"] or ""
        inside_m = sum(polyline_m(p) for p in clip_to_bbox(cs["coords"], d["bbox"]))
        shown_len = re.search(r"Длина\s*([\d ,]+\s*(?:км|м))", card)
        ok = r["cross_seg_selected"] == cs["id"] and "(вся линия, выходит за квадрат)" in card and shown_len \
            and shown_len.group(1).strip() == fmt_m(cs["length_m"])
        add("R2_cross_segment_card", city, ok, {"segment": cs["id"], "shown": shown_len and shown_len.group(1),
                                                "length_m_full_line": cs["length_m"], "inside_square_m": round(inside_m, 1),
                                                "outside_share": round(1 - inside_m / polyline_m(cs["coords"]), 3),
                                                "marker_present": "(вся линия, выходит за квадрат)" in card,
                                                "length_basis_label": "геодезическая, K10" if "геодезическая, K10" in card else None})
        ins, icard = d["inner_seg"], r["inner_seg_card"] or ""
        add("R2b_inner_segment_card", city, r["inner_seg_selected"] == ins["id"] and "выходит за квадрат" not in icard
            and fmt_m(ins["length_m"]) in icard, {"segment": ins["id"], "length_m": ins["length_m"], "marker_present": "выходит за квадрат" in icard})

        if r.get("point_card"):
            lon, lat = r["point"]
            pl = {p["name"]: p for p in r["point_places"]}
            errs, order = [], []
            for name, _cat, dist in r["point_rows"]:
                v, step = parse_len(dist)
                cands = [p for p in r["point_places"] if p["name"] == name]
                true = min(vincenty_m(lon, lat, p["lon"], p["lat"]) for p in cands)
                errs.append(abs(v - true) - step - 0.005 * true)
                order.append(v)
            hdr_ok = r["point_header"][-1] == "По прямой"
            warn = "нижняя граница пешего пути" in r["point_card"] and "не время в пути" in r["point_card"]
            ok = hdr_ok and warn and max(errs) <= 0 and order == sorted(order) and len(r["point_rows"]) > 0
            add("R3_point_distances", city, ok, {"point": [round(lon, 6), round(lat, 6)], "rows": r["point_rows"][:3],
                                                "rows_n": len(r["point_rows"]), "max_excess_over_tolerance_m": round(max(errs), 3),
                                                "sorted": order == sorted(order), "header": r["point_header"], "lower_bound_warning": warn})
        else:
            add("R3_point_distances", city, False, {"error": "no empty map spot produced a point card"}, warn=True)

        txt = r["body_text"] + (r["cross_seg_card"] or "") + (r["point_card"] or "")
        mins = re.findall(r"\d+\s*(?:мин\b|минут)", txt)
        claims = affirmative_claims(r"(?:всего в городе|школ[а-я]* в городе|объектов в городе)", txt)
        add("R4_no_walk_time_no_city_total", city, not mins and not claims, {"minutes": mins, "city_total_claims": claims})

        tc, bn = r["table_count"], r["banner"]
        add("R5_table_and_banner", city, "записей среза" in tc and "не число всех школ города" in bn
            and str(d["places"]) in tc, {"table_count": tc.strip(), "banner_mentions_not_city_total": "не число всех школ города" in bn})
    if obs["errors"]:
        checks.append({"id": "R0_page_errors", "city": "-", "status": "FAIL", "observed": obs["errors"]})
    return checks


def main(argv=None):
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--app-root"); g.add_argument("--url")
    ap.add_argument("--json")
    a = ap.parse_args(argv)
    target = a.url or Path(a.app_root, "web", "index.html").resolve().as_uri()
    obs = run(target)
    checks = check(obs)
    rep = {"target": target, "summary": dict(Counter(c["status"] for c in checks)), "checks": checks}
    if a.app_root and Path(a.app_root, "_extract_manifest.json").exists():
        rep["extracted_from_commit"] = json.load(open(Path(a.app_root, "_extract_manifest.json")))["commit"]
    if a.json:
        Path(a.json).write_text(json.dumps(rep, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    for c in checks:
        print(f"{c['status']:4} {c['city']:9} {c['id']}")
    print(rep["summary"])
    return 1 if any(c["status"] == "FAIL" for c in checks) else 0


if __name__ == "__main__":
    sys.exit(main())
