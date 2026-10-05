"""K12 round 5 REVIEW: negative inputs on the BUILD path of prototypes/city-evidence.

Two modes, both reusable on a fixed version:

  --app-root DIR   DIR = an extracted copy of prototypes/city-evidence (see extract_build.py).
                   Every case runs in its own temporary copy of DIR: one input file is mutated,
                   then the real rebuild path runs as subprocesses —
                       tools/build_data.py      (-> web/data.js)
                       tools/build_evidence.py  (-> web/evidence.js; needs shapely+pyproj)
                   and, for information only, inputs/k10/scripts/offline_check.py.
                   SEMANTIC cases are made hash-correct: package_manifest.json (sha256/bytes/features)
                   AND source_manifest.json (the file and package_manifest.json) are recomputed,
                   so an integrity refusal cannot hide a missing semantic check.
                   Requirement: every semantic/integrity case is refused by BOTH steps with a
                   diagnostic (non-zero exit, no traceback) and web/data.js + web/evidence.js stay
                   byte-identical (no partially written result). The clean control must rebuild
                   byte-identical outputs.

  --url URL        URL = served demo root (python serve.py -> http://127.0.0.1:8765/). Fetches
                   data.js and evidence.js and checks the delivered artifacts: strict JSON (no
                   NaN/Infinity/1e999, no duplicate keys), unique ids, points inside the city bbox,
                   finite numbers, consistent release, unique obs_id, place<->district coverage.

The real data are never changed: --app-root DIR itself is only read; mutations happen in temp copies.
All mutated values are SYNTHETIC test inputs.

Exit code: 0 if every case meets its requirement (or, with --expect-file, if outcomes equal the
expected baseline outcomes); 1 otherwise.

    python k12r5_negative_build.py --app-root /path/to/extracted --python /path/to/python-with-shapely
    python k12r5_negative_build.py --app-root ... --expect-file BASELINE_0bf27de_EXPECTED.json
    python k12r5_negative_build.py --url http://127.0.0.1:8765/
"""
import argparse
import copy
import hashlib
import json
import math
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.request
from pathlib import Path

SENT = "__K12R5_SENTINEL__"
DUPKEY = "__K12R5_DUPKEY__"
OUTPUTS = ("web/data.js", "web/evidence.js")
# Refusal classes. A fixed build may prefix messages with INTEGRITY: / SEMANTIC: to be explicit;
# otherwise the current wording of build_data.py is used ("sha256/размер ...", "нет файла ...").
INTEGRITY_MARKERS = ("INTEGRITY", "sha256", "размер не совпад", "нет файла", "целостност")


# ----------------------------------------------------------------- strict JSON
class StrictJSONError(ValueError):
    pass


def loads_strict(text):
    def no_const(name):
        raise StrictJSONError(f"JSON_NONFINITE: token {name}")

    def finite_float(tok):
        v = float(tok)
        if not math.isfinite(v):
            raise StrictJSONError(f"JSON_NONFINITE: {tok} -> {v}")
        return v

    def unique(pairs):
        out = {}
        for k, v in pairs:
            if k in out:
                raise StrictJSONError(f"JSON_DUPLICATE_KEY: {k!r}")
            out[k] = v
        return out

    return json.loads(text, parse_constant=no_const, parse_float=finite_float, object_pairs_hook=unique)


def js_payload(text):
    """'// comment\\nwindow.X = {...};' -> '{...}'"""
    start = text.index("{")
    end = text.rstrip().rindex(";")
    return text[start:end]


# ------------------------------------------------------------ artifact checks
def in_bbox(lon, lat, bb):
    return bb[0] <= lon <= bb[2] and bb[1] <= lat <= bb[3]


def check_artifacts(data_text, ev_text):
    """Checks on delivered data.js/evidence.js. Returns list of problems (empty = clean)."""
    problems = []
    parsed = {}
    for name, text in (("data.js", data_text), ("evidence.js", ev_text)):
        try:
            parsed[name] = loads_strict(js_payload(text))
        except StrictJSONError as e:
            problems.append(f"{name}: {e}")
            parsed[name] = json.loads(js_payload(text))  # lenient, to continue the other checks
        except ValueError as e:
            problems.append(f"{name}: unparsable ({e})")
            return problems
    data, ev = parsed["data.js"], parsed["evidence.js"]
    for city, c in data.get("cities", {}).items():
        bb = c["bbox"]
        ids = [p["id"] for p in c["places"]]
        if len(ids) != len(set(ids)):
            problems.append(f"{city}: DUPLICATE_PLACE_ID x{len(ids) - len(set(ids))}")
        sids = [s["id"] for s in c["segments"]]
        if len(sids) != len(set(sids)):
            problems.append(f"{city}: DUPLICATE_SEGMENT_ID x{len(sids) - len(set(sids))}")
        nonfinite = [p["id"] for p in c["places"] if not all(
            isinstance(v, (int, float)) and math.isfinite(v) for v in (p["lon"], p["lat"]))]
        if nonfinite:
            problems.append(f"{city}: NONFINITE_COORD places {len(nonfinite)}")
        outside = [p["id"] for p in c["places"] if p["id"] not in nonfinite and not in_bbox(p["lon"], p["lat"], bb)]
        if outside:
            problems.append(f"{city}: PLACE_OUTSIDE_BBOX {len(outside)}")
        bad_conf = [p["id"] for p in c["places"] if p.get("confidence") is not None and not (
            isinstance(p["confidence"], (int, float)) and math.isfinite(p["confidence"]))]
        if bad_conf:
            problems.append(f"{city}: NONFINITE_CONFIDENCE {len(bad_conf)}")
        bad_len = [s["id"] for s in c["segments"] if not math.isfinite(s["length_m"])]
        if bad_len:
            problems.append(f"{city}: NONFINITE_LENGTH {len(bad_len)}")
        evc = ev.get("cities", {}).get(city)
        if evc is None:
            problems.append(f"{city}: no evidence for city")
            continue
        if set(evc["place_district"]) != set(ids):
            problems.append(f"{city}: PLACE_DISTRICT_MISMATCH data {len(set(ids))} ids vs evidence {len(evc['place_district'])}")
        oids = [o["obs_id"] for o in evc["observations"]]
        if len(oids) != len(set(oids)):
            problems.append(f"{city}: DUPLICATE_OBS_ID")
        rel = {o.get("release") for o in evc["observations"]}
        if rel != {c["release"]}:
            problems.append(f"{city}: RELEASE_MISMATCH data {c['release']} vs evidence {sorted(map(str, rel))}")
        total = next((o["value"] for o in evc["observations"] if o["indicator_id"] == "places.total"), None)
        if total is not None and total != len(set(ids)):
            problems.append(f"{city}: PLACES_TOTAL {total} != unique ids {len(set(ids))}")
        if evc.get("city_mismatch"):
            problems.append(f"{city}: CITY_MISMATCH {len(evc['city_mismatch'])} places assigned to another city")
    return problems


# --------------------------------------------------------------- mutations
def _fc(path):
    return json.loads(path.read_text(encoding="utf-8"))


def _write_with_token(path, fc, token):
    text = json.dumps(fc, ensure_ascii=False)
    assert text.count(json.dumps(SENT)) == 1
    path.write_text(text.replace(json.dumps(SENT), token), encoding="utf-8")


def m_token(layer, field, token, city="shymkent", coord=None):
    def mutate(app):
        p = app / f"inputs/k10/data/{city}/{layer}.geojson"
        fc = _fc(p)
        # build_data keeps only road segments: mutate a feature that reaches the output
        f = next(f for f in fc["features"] if layer != "segments" or f["properties"]["subtype"] == "road")
        if coord is not None:
            f["geometry"]["coordinates"][coord] = SENT
        else:
            f["properties"][field] = SENT
        _write_with_token(p, fc, token)
        return [p]
    return mutate


def m_duplicate_key(app):
    p = app / "inputs/k10/data/shymkent/places_social.geojson"
    fc = _fc(p)
    f = next(f for f in fc["features"] if f["properties"]["k10_group"] == "school")
    f["properties"][DUPKEY] = "x"
    text = json.dumps(fc, ensure_ascii=False)
    old = f'{json.dumps(DUPKEY)}: "x"'
    assert text.count(old) == 1
    p.write_text(text.replace(old, '"k10_group": "pharmacy"'), encoding="utf-8")  # 2nd k10_group, last wins
    return [p]


def m_conflicting_id(app):
    p = app / "inputs/k10/data/shymkent/places_social.geojson"
    fc = _fc(p)
    twin = copy.deepcopy(fc["features"][0])
    twin["properties"]["name_primary"] = "K12R5 SYNTHETIC conflicting twin"
    twin["properties"]["k10_group"] = "hospital"
    fc["features"].append(twin)  # same id / overture_id, different content
    p.write_text(json.dumps(fc, ensure_ascii=False), encoding="utf-8")
    return [p]


def m_point_in_other_city(app):
    man = json.loads((app / "inputs/k10/package_manifest.json").read_text(encoding="utf-8"))
    ab = man["cities"]["astana"]["bbox"]
    p = app / "inputs/k10/data/shymkent/places_social.geojson"
    fc = _fc(p)
    fc["features"][0]["geometry"]["coordinates"] = [round((ab[0] + ab[2]) / 2, 6), round((ab[1] + ab[3]) / 2, 6)]
    p.write_text(json.dumps(fc, ensure_ascii=False), encoding="utf-8")
    return [p]


def m_header(field, value):
    def mutate(app):
        p = app / "inputs/k10/data/shymkent/places_social.geojson"
        fc = _fc(p)
        fc[field] = value
        p.write_text(json.dumps(fc, ensure_ascii=False), encoding="utf-8")
        return [p]
    return mutate


def m_benign_name(app):
    p = app / "inputs/k10/data/shymkent/places_social.geojson"
    fc = _fc(p)
    fc["features"][0]["properties"]["name_primary"] = "K12R5 SYNTHETIC renamed"
    p.write_text(json.dumps(fc, ensure_ascii=False), encoding="utf-8")
    return [p]


def m_flip_byte(app):
    p = app / "inputs/k10/data/astana/places_social.geojson"
    p.write_bytes(p.read_bytes().replace(b'"school"', b'"schoo1"', 1))
    return [p]


def rehash(app, changed, anchor_source_manifest=True):
    """Make the mutated copy hash-correct in package_manifest.json (+ source_manifest.json)."""
    pm_path = app / "inputs/k10/package_manifest.json"
    pm = json.loads(pm_path.read_text(encoding="utf-8"))
    for c in pm["cities"].values():
        for fm in c["files"].values():
            fp = app / "inputs/k10" / fm["path"]
            if fp in changed:
                b = fp.read_bytes()
                fm["sha256"], fm["bytes"] = hashlib.sha256(b).hexdigest(), len(b)
                fm["features"] = len(json.loads(b.decode("utf-8"))["features"])
    pm_path.write_text(json.dumps(pm, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    if anchor_source_manifest:
        sm_path = app / "source_manifest.json"
        sm = json.loads(sm_path.read_text(encoding="utf-8"))
        for e in sm["files"]:
            fp = app / e["copied_to"]
            if fp in changed or fp == pm_path:
                b = fp.read_bytes()
                e["sha256"], e["bytes"] = hashlib.sha256(b).hexdigest(), len(b)
        sm_path.write_text(json.dumps(sm, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


CASES = [
    {"id": "C01", "kind": "control_clean", "title": "неизменённая копия: пересборка побайтно равна закоммиченной", "mutate": None},
    {"id": "C02", "kind": "integrity", "title": "изменён байт без пересчёта hash (как test_corrupted_file_is_rejected)",
     "mutate": m_flip_byte, "rehash": None},
    {"id": "I01", "kind": "integrity", "title": "данные и package_manifest согласованно изменены, source_manifest — нет (якорь целостности)",
     "mutate": m_benign_name, "rehash": "package_only"},
    {"id": "N01", "kind": "semantic", "title": "NaN в confidence объекта (токен NaN)", "mutate": m_token("places_social", "confidence", "NaN")},
    {"id": "N02", "kind": "semantic", "title": "NaN в координате объекта", "mutate": m_token("places_social", None, "NaN", coord=0)},
    {"id": "N03", "kind": "semantic", "title": "Infinity в k10_length_m сегмента", "mutate": m_token("segments", "k10_length_m", "Infinity")},
    {"id": "N04", "kind": "semantic", "title": "1e999 (строго валидный JSON → inf) в k10_length_m сегмента",
     "mutate": m_token("segments", "k10_length_m", "1e999")},
    {"id": "N05", "kind": "semantic", "title": "повтор ключа k10_group (school, затем pharmacy) — последний молча побеждает",
     "mutate": m_duplicate_key},
    {"id": "N06", "kind": "semantic", "title": "конфликт ID: второй объект с тем же id/overture_id и другим содержимым",
     "mutate": m_conflicting_id},
    {"id": "N07", "kind": "semantic", "title": "bbox mix: объект файла Шымкента с координатами в квадрате Астаны",
     "mutate": m_point_in_other_city},
    {"id": "N08", "kind": "semantic", "title": "bbox mix: заголовок слоя с bbox, отличным от манифеста",
     "mutate": m_header("bbox", [69.0, 42.0, 69.1, 42.1])},
    {"id": "N09", "kind": "semantic", "title": "period mix: слой объектов из выпуска 2026-08-20.0 при манифесте 2026-09-23.1",
     "mutate": m_header("release", "2026-08-20.0")},
]


# ----------------------------------------------------------------- running
def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest() if p.exists() else None


def run_step(py, app, script, args=()):
    r = subprocess.run([py, script, *args], cwd=app, capture_output=True, text=True, timeout=900)
    err = (r.stderr or "").strip()
    if r.returncode == 0:
        outcome = "accepted"
    elif "Traceback (most recent call last)" in err:
        outcome = "crash"
    elif "SEMANTIC" in err:
        outcome = "rejected_semantic"
    elif any(m in err for m in INTEGRITY_MARKERS):
        outcome = "rejected_integrity"
    else:
        outcome = "rejected_semantic"
    last = err.splitlines()[-1] if err else ""
    return {"exit": r.returncode, "outcome": outcome, "stderr_last": last[:300]}


def run_case(case, app_root, py, keep):
    tmp = Path(tempfile.mkdtemp(prefix=f"k12r5_{case['id']}_"))
    app = tmp / "app"
    shutil.copytree(app_root, app, ignore=shutil.ignore_patterns("__pycache__"))
    before = {o: sha(app / o) for o in OUTPUTS}
    if case["mutate"]:
        changed = case["mutate"](app)
        mode = case.get("rehash", "both")
        if case["kind"] == "semantic" or mode == "package_only":
            rehash(app, changed, anchor_source_manifest=(mode != "package_only"))
    steps = {"build_data": run_step(py, app, "tools/build_data.py"),
             "build_evidence": run_step(py, app, "tools/build_evidence.py")}
    oc = subprocess.run([py, "inputs/k10/scripts/offline_check.py", "--json", str(tmp / "oc.json")],
                        cwd=app, capture_output=True, text=True, timeout=900)
    try:
        oc_errors = json.loads((tmp / "oc.json").read_text(encoding="utf-8")).get("errors", [])
    except (OSError, ValueError):
        oc_errors = [(oc.stderr or "").strip().splitlines()[-1:]]
    after = {o: sha(app / o) for o in OUTPUTS}
    changed_out = [o for o in OUTPUTS if before[o] != after[o]]
    artifact_problems = check_artifacts((app / OUTPUTS[0]).read_text(encoding="utf-8"),
                                        (app / OUTPUTS[1]).read_text(encoding="utf-8"))
    outcomes = {s["outcome"] for s in steps.values()}
    if case["kind"] == "control_clean":
        ok = outcomes == {"accepted"} and not changed_out and not artifact_problems
    elif case["kind"] == "integrity":
        ok = outcomes == {"rejected_integrity"} and not changed_out
    else:
        ok = outcomes == {"rejected_semantic"} and not changed_out
    res = {"id": case["id"], "kind": case["kind"], "title": case["title"], "steps": steps,
           "offline_check": {"exit": oc.returncode, "errors": oc_errors[:5]},
           "outputs_changed": changed_out, "artifact_problems_after": artifact_problems,
           "requirement_met": ok, "tmp": str(app) if keep else None}
    if not keep:
        shutil.rmtree(tmp, ignore_errors=True)
    return res


def run_app_root(app_root, py, keep, only):
    app_root = Path(app_root).resolve()
    if not (app_root / "tools/build_data.py").exists():
        raise SystemExit(f"{app_root}: not a prototypes/city-evidence copy (no tools/build_data.py)")
    cases = [c for c in CASES if not only or c["id"] in only]
    ver = subprocess.run([py, "-c", "import sys\ntry:\n import shapely, pyproj; g=f'shapely {shapely.__version__}, pyproj {pyproj.__version__}'\n"
                          "except ImportError: g='shapely/pyproj missing'\nprint(sys.version.split()[0], g)"],
                         capture_output=True, text=True).stdout.strip()
    head = {"mode": "app-root", "app_root": app_root.name, "build_python": ver,
            "outputs_sha256": {o: sha(app_root / o) for o in OUTPUTS}}
    return head, [run_case(c, app_root, py, keep) for c in cases]


def run_url(url):
    base = url if url.endswith("/") else url + "/"
    texts = {}
    for name in ("data.js", "evidence.js"):
        with urllib.request.urlopen(base + name, timeout=30) as r:
            texts[name] = r.read().decode("utf-8")
    problems = check_artifacts(texts["data.js"], texts["evidence.js"])
    head = {"mode": "url", "url": base,
            "sha256": {n: hashlib.sha256(t.encode("utf-8")).hexdigest() for n, t in texts.items()}}
    return head, [{"id": "U01", "kind": "artifact", "title": "доставленные data.js/evidence.js",
                   "problems": problems, "requirement_met": not problems}]


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--app-root")
    g.add_argument("--url")
    ap.add_argument("--python", default=sys.executable, help="python with shapely+pyproj for build_evidence.py")
    ap.add_argument("--expect-file", help="JSON {case_id: true|false} expected requirement_met (e.g. baseline)")
    ap.add_argument("--only", nargs="*", help="run only these case ids")
    ap.add_argument("--keep-tmp", action="store_true")
    ap.add_argument("--out")
    a = ap.parse_args(argv)
    head, results = run_url(a.url) if a.url else run_app_root(a.app_root, a.python, a.keep_tmp, a.only)
    expect = json.loads(Path(a.expect_file).read_text(encoding="utf-8"))["requirement_met"] if a.expect_file else None
    for r in results:
        if expect is not None and r["id"] in expect:
            r["expected_requirement_met"] = expect[r["id"]]
            r["matches_expectation"] = expect[r["id"]] == r["requirement_met"]
    out = {**head, "results": results,
           "summary": {"requirement_met": sum(r["requirement_met"] for r in results), "total": len(results),
                       "failed": [r["id"] for r in results if not r["requirement_met"]]}}
    if expect is not None:
        out["summary"]["unexpected"] = [r["id"] for r in results if r.get("matches_expectation") is False]
    text = json.dumps(out, indent=1, ensure_ascii=False, allow_nan=False) + "\n"
    if a.out:
        Path(a.out).write_text(text, encoding="utf-8")
    for r in results:
        steps = r.get("steps")
        line = (" ".join(f"{k}={v['outcome']}" for k, v in steps.items()) if steps else "; ".join(r["problems"]) or "clean")
        mark = "OK  " if r["requirement_met"] else ("XFAIL" if r.get("matches_expectation") else "FAIL")
        print(f"{mark} {r['id']:4} {r['title'][:70]:70} | {line}"
              + (f" | outputs changed: {','.join(r['outputs_changed'])}" if r.get("outputs_changed") else ""))
    print(json.dumps(out["summary"], ensure_ascii=False))
    if expect is not None:
        return 0 if not out["summary"]["unexpected"] else 1
    return 0 if not out["summary"]["failed"] else 1


if __name__ == "__main__":
    sys.exit(main())
