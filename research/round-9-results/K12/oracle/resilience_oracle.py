"""K12 round 9: INDEPENDENT Python oracle for city-resilience-v1 (research/round-9/CORE_SPEC.txt @ 0ab1667).

Written from CORE_SPEC only, without reading or calling any BUILD resilience code. Strict JSON + envelope validation and an
exact brute-force computation (itertools.combinations over free candidates, <= 4096 subsets). Geometry helpers
(haversine, mm rounding, data.js loader) come from the K12 r8 oracle, so the metric equals haversine-mm-v1 of city-plan-v2.

    python resilience_oracle.py --app-root <copy> --index FIXTURES_RS_INDEX.json [--out corpus_check.json]
    python resilience_oracle.py --app-root <copy> --problems problems.json --out results.json

Placeholders: the envelope's plan.source_snapshot must be "__SNAPSHOT__" (the current slice); "__SNAPSHOT_OTHER_CITY__" or
anything else is foreign. Choices where CORE_SPEC is silent are named POLICY below (an implementation may differ).
ID order: plain JS string order (UTF-16 code units), as plan.js sorts IDs -- not Python code-point order.
"""
import argparse
import hashlib
import itertools
import json
import math
import sys
import unicodedata
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[2] / "round-8-results" / "K12" / "oracle"))
from plan_v2_oracle import haversine_m, to_mm  # noqa: E402  (K12 r8, haversine-mm-v1)

SCHEMA, PLAN_SCHEMA = "city-resilience-v1", "city-plan-v2"
SNAP = "__SNAPSHOT__"
MAX_BYTES, MAX_DEPTH = 262144, 32
LIM = {"points": (1, 25), "cands": 12, "cases": (1, 7), "label": 120, "weight": (1, 100), "cost": (1, 1000000),
       "budget": (0, 1000000), "max_selected": (0, 5), "radius": (100, 5000), "id": 64}
CATS = ("school", "outpatient_clinic")
PLAN_KEYS = {"schema_version", "city_id", "source_snapshot", "category", "control_points", "candidates", "budget",
             "max_selected", "coverage_radius_m", "required_ids", "excluded_ids", "selected_ids"}
INF = float("inf")
BIDI = set("‪‫‬‭‮⁦⁧⁨⁩")


class Refused(Exception):
    def __init__(self, code, detail=""):
        super().__init__(f"{code}: {detail}")
        self.code = code


def js_key(s):
    """JS default string order = UTF-16 code unit order."""
    return s.encode("utf-16-be")


def ids_key(ids):
    return [js_key(i) for i in ids]


# ------------------------------------------------------------------ strict JSON
def parse_strict(text):
    if text.startswith("﻿"):
        text = text[1:]
    if len(text.encode("utf-8", "surrogatepass")) > MAX_BYTES:
        raise Refused("too_large", "больше 256 KiB")

    def pairs(kv):
        seen = {}
        for k, v in kv:
            if k in seen:
                raise Refused("bad_json", f"повтор ключа {k}")
            seen[k] = v
        return seen

    def const(name):
        raise Refused("bad_json", name)

    def flt(s):
        v = float(s)
        if not math.isfinite(v):
            raise Refused("bad_json", s)
        return v

    try:
        obj = json.loads(text, object_pairs_hook=pairs, parse_constant=const, parse_float=flt)
    except Refused:
        raise
    except RecursionError:
        raise Refused("bad_json", "слишком глубокая вложенность")
    except ValueError as e:
        raise Refused("bad_json", str(e)[:80])

    def depth(v, d):
        if d > MAX_DEPTH:
            raise Refused("bad_json", "вложенность > 32")
        if isinstance(v, dict):
            for x in v.values():
                depth(x, d + 1)
        elif isinstance(v, list):
            for x in v:
                depth(x, d + 1)
    depth(obj, 0)
    return obj


# ------------------------------------------------------------------ validation
def is_int(v, lo, hi):
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        return False
    if isinstance(v, float) and not v.is_integer():
        return False
    return lo <= v <= hi


def is_num(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


def valid_id(v):
    if not isinstance(v, str) or not (1 <= len(v) <= LIM["id"]) or unicodedata.normalize("NFC", v) != v:
        return False
    return all(unicodedata.category(ch)[0] in "LN" or ch in "_.-" for ch in v)


def keys_exact(o, want, what):
    if not isinstance(o, dict):
        raise Refused("bad_shape", f"{what}: объект")
    extra = set(o) - set(want)
    if extra:
        raise Refused("unknown_field", f"{what}: {sorted(extra)[0]}")
    missing = set(want) - set(o)
    if missing:
        raise Refused("missing_field", f"{what}: {sorted(missing)[0]}")


def id_list(v, what, known):
    if not isinstance(v, list):
        raise Refused("bad_shape", what)
    if any(not valid_id(x) for x in v):
        raise Refused("bad_id", what)
    if len(set(v)) != len(v):
        raise Refused("duplicate_id", what)
    if any(x not in known for x in v):
        raise Refused("unknown_ref", what)
    return v


def validate_plan(p, data):
    if not isinstance(p, dict):
        raise Refused("bad_plan", "plan: объект")
    if p.get("schema_version") != PLAN_SCHEMA:
        raise Refused("bad_plan", "plan не city-plan-v2")
    if "derived_results" in p:
        raise Refused("derived_in_plan", "POLICY: производные поля в plan конверта не принимаются")
    keys_exact(p, PLAN_KEYS, "plan")
    city = p["city_id"]
    if city not in data["cities"]:
        raise Refused("bad_city", str(city))
    if p["source_snapshot"] != SNAP:
        raise Refused("foreign_snapshot", "snapshot")
    if p["category"] not in CATS:
        raise Refused("bad_category", str(p["category"]))
    bb = data["cities"][city]["bbox"]
    pts, cands = p["control_points"], p["candidates"]
    if not isinstance(pts, list) or not isinstance(cands, list):
        raise Refused("bad_shape", "массивы")
    if len(cands) > LIM["cands"]:                       # before any per-item work or precomputation
        raise Refused("too_many_candidates", f"{len(cands)} > {LIM['cands']}")
    if not (LIM["points"][0] <= len(pts) <= LIM["points"][1]):
        raise Refused("bad_plan", "число точек")

    def coord(o, what):
        if not is_num(o["lon"]) or not is_num(o["lat"]):
            raise Refused("bad_plan", f"{what}: координаты")
        if not (bb[0] <= o["lon"] <= bb[2] and bb[1] <= o["lat"] <= bb[3]):
            raise Refused("bad_plan", f"{what}: вне bbox")

    for k, q in enumerate(pts):
        keys_exact(q, {"id", "lon", "lat", "weight"}, f"control_points[{k}]")
        if not valid_id(q["id"]):
            raise Refused("bad_plan", "id точки")
        coord(q, q["id"])
        if not is_int(q["weight"], *LIM["weight"]):
            raise Refused("bad_plan", "вес")
    for k, c in enumerate(cands):
        keys_exact(c, {"id", "lon", "lat", "category", "kind", "cost"}, f"candidates[{k}]")
        if not valid_id(c["id"]) or c["kind"] != "hypothetical" or c["category"] != p["category"]:
            raise Refused("bad_plan", "кандидат")
        coord(c, c["id"])
        if not is_int(c["cost"], *LIM["cost"]):
            raise Refused("bad_plan", "стоимость")
    for arr, what in ((pts, "points"), (cands, "candidates")):
        if len({x["id"] for x in arr}) != len(arr):
            raise Refused("bad_plan", f"повтор id {what}")
    if not is_int(p["budget"], *LIM["budget"]) or not is_int(p["max_selected"], *LIM["max_selected"]) \
            or not is_int(p["coverage_radius_m"], *LIM["radius"]):
        raise Refused("bad_plan", "budget/max_selected/radius")
    known = {c["id"] for c in cands}
    try:
        req = id_list(p["required_ids"], "required_ids", known)
        exc = id_list(p["excluded_ids"], "excluded_ids", known)
        id_list(p["selected_ids"], "selected_ids", known)
    except Refused as e:
        raise Refused("bad_plan", str(e))
    if set(req) & set(exc):
        raise Refused("bad_plan", "required ∩ excluded")
    return p


def valid_label(v):
    if not isinstance(v, str) or not (1 <= len(v) <= LIM["label"]):
        return False
    if any(unicodedata.category(ch) == "Cc" for ch in v):
        return False
    if any(0xD800 <= ord(ch) <= 0xDFFF for ch in v):    # POLICY: lone surrogate is not a Unicode character
        return False
    if any(ch in BIDI for ch in v):                     # POLICY: bidi overrides (Cf) hide the displayed order
        return False
    if not v.strip():                                   # POLICY: whitespace-only label is treated as empty
        return False
    return True


def validate_envelope(obj, data):
    if not isinstance(obj, dict):
        raise Refused("bad_shape", "корень — объект")
    extra = set(obj) - {"schema_version", "plan", "cases"}
    if extra:
        raise Refused("unknown_field", sorted(extra)[0])
    for k in ("schema_version", "plan", "cases"):
        if k not in obj:
            raise Refused("missing_field", k)
    if obj["schema_version"] != SCHEMA:
        raise Refused("bad_version", str(obj["schema_version"])[:40])
    p = validate_plan(obj["plan"], data)
    cases = obj["cases"]
    if not isinstance(cases, list):
        raise Refused("bad_shape", "cases — массив")
    if len(cases) < LIM["cases"][0]:
        raise Refused("too_few_cases", "нужен хотя бы один случай")
    if len(cases) > LIM["cases"][1]:
        raise Refused("too_many_cases", f"{len(cases)} > 7")
    src = {s["id"] for s in data["cities"][p["city_id"]]["places"] if s["group"] == p["category"]}
    seen = set()
    for k, c in enumerate(cases):
        keys_exact(c, {"id", "label", "disabled_source_ids"}, f"cases[{k}]")
        if not valid_id(c["id"]):
            raise Refused("bad_id", f"cases[{k}].id")
        if c["id"] == "base":
            raise Refused("reserved_id", "base")
        if c["id"] in seen:
            raise Refused("duplicate_id", c["id"])
        seen.add(c["id"])
        if not valid_label(c["label"]):
            raise Refused("bad_label", f"cases[{k}].label")
        ds = c["disabled_source_ids"]
        if not isinstance(ds, list):
            raise Refused("bad_shape", "disabled_source_ids — массив")
        if not ds:
            raise Refused("bad_exclusion", "пустое исключение")
        if any(not isinstance(x, str) for x in ds):
            raise Refused("bad_shape", "source id — строка")
        if len(set(ds)) != len(ds):
            raise Refused("duplicate_id", "повтор source id")
        if any(x not in src for x in ds):
            raise Refused("unknown_source", "не source ID этого города/категории")
    return obj


# ------------------------------------------------------------------ computation
def solve(env, data):
    p = env["plan"]
    places = data["cities"][p["city_id"]]["places"]
    src = [s for s in places if s["group"] == p["category"]]
    pts = sorted(p["control_points"], key=lambda q: js_key(q["id"]))
    w = [q["weight"] for q in pts]
    tw = sum(w)
    rmm = p["coverage_radius_m"] * 1000
    cases = [("base", "base", frozenset())] + [(c["id"], c["label"], frozenset(c["disabled_source_ids"])) for c in env["cases"]]
    src_mm = {s["id"]: [to_mm(haversine_m(q["lon"], q["lat"], s["lon"], s["lat"])) for q in pts] for s in src}
    before = {}
    for cid, _, dis in cases:
        row = []
        for j in range(len(pts)):
            vals = [src_mm[s["id"]][j] for s in src if s["id"] not in dis]
            row.append(min(vals) if vals else None)
        before[cid] = row
    cand = {c["id"]: c for c in p["candidates"]}
    cmm = {cid: [to_mm(haversine_m(q["lon"], q["lat"], c["lon"], c["lat"])) for q in pts] for cid, c in cand.items()}

    def in_case(ids, cid):
        unknown = wsum = cov = 0
        mx = 0
        for j in range(len(pts)):
            opts = ([before[cid][j]] if before[cid][j] is not None else []) + [cmm[i][j] for i in ids]
            if not opts:
                unknown += 1
                continue
            a = min(opts)
            wsum += w[j] * a
            mx = max(mx, a)
            if a <= rmm:
                cov += w[j]
        return {"case_id": cid, "unknown_count": unknown, "weighted_sum_mm": wsum,
                "weighted_mean_mm": (wsum / tw) if unknown == 0 else None, "max_mm": mx if unknown == 0 else None,
                "covered_weight": cov, "cost": sum(cand[i]["cost"] for i in ids)}

    def L(m):
        return (m["unknown_count"], m["weighted_sum_mm"], INF if m["max_mm"] is None else m["max_mm"])

    def profile(ids):
        rows = [in_case(ids, cid) for cid, _, _ in cases]
        Ws = max(L(r) for r in rows)
        worst = sorted({r["case_id"] for r in rows if L(r) == Ws}, key=js_key)
        return rows, Ws, worst

    req = sorted(p["required_ids"], key=js_key)
    exc = set(p["excluded_ids"])
    free = sorted([i for i in cand if i not in req and i not in exc], key=js_key)
    req_cost = sum(cand[i]["cost"] for i in req)
    reasons = []
    if len(req) > p["max_selected"]:
        reasons.append("required_exceeds_max_selected")
    if req_cost > p["budget"]:
        reasons.append("required_cost_exceeds_budget")
    manual_ids = sorted(p["selected_ids"], key=js_key)
    m_rows, m_W, m_worst = profile(manual_ids)
    m_cost = sum(cand[i]["cost"] for i in manual_ids)
    m_reasons = [r for r, bad in (("over_budget", m_cost > p["budget"]), ("too_many", len(manual_ids) > p["max_selected"]),
                                  ("missing_required", any(i not in manual_ids for i in req)),
                                  ("has_excluded", any(i in exc for i in manual_ids))) if bad]
    out = {"status": None, "reasons": reasons, "case_ids": [c[0] for c in cases],
           "manual": {"ids": manual_ids, "feasible": not m_reasons, "reasons": m_reasons, "per_case": m_rows,
                      "worst_vector": jsonable(m_W), "worst_case_ids": m_worst}}
    if reasons:
        out.update(status="infeasible", evaluated=0, feasible_count=0, nominal=None, robust=None,
                   price_of_robustness_m=None, price_null_reason="infeasible")
        return out
    slots = p["max_selected"] - len(req)
    best_nom = best_rob = None
    feasible = evaluated = 0
    for r in range(len(free) + 1):
        for combo in itertools.combinations(free, r):
            evaluated += 1
            if r > slots:
                continue
            ids = sorted(req + list(combo), key=js_key)
            cost = sum(cand[i]["cost"] for i in ids)
            if cost > p["budget"]:
                continue
            feasible += 1
            rows, Wv, worst = profile(ids)
            Lb = L(rows[0])
            nk = (Lb, cost, ids_key(ids))
            rk = (Wv, Lb, cost, ids_key(ids))
            if best_nom is None or nk < best_nom[0]:
                best_nom = (nk, ids, rows, Wv, worst)
            if best_rob is None or rk < best_rob[0]:
                best_rob = (rk, ids, rows, Wv, worst)

    def pack(b):
        _, ids, rows, Wv, worst = b
        return {"ids": ids, "cost": rows[0]["cost"], "per_case": rows, "worst_vector": jsonable(Wv), "worst_case_ids": worst}

    nom, rob = pack(best_nom), pack(best_rob)
    mn, mr = nom["per_case"][0]["weighted_mean_mm"], rob["per_case"][0]["weighted_mean_mm"]
    price = None if mn is None or mr is None else (mr - mn) / 1000
    out.update(status="optimal", evaluated=evaluated, feasible_count=feasible, nominal=nom, robust=rob,
               price_of_robustness_m=price, price_null_reason=None if price is not None else "unknown_base_mean")
    return out


def jsonable(Wv):
    return [Wv[0], Wv[1], None if Wv[2] == INF else Wv[2]]


def load_data(app_root):
    raw = (Path(app_root) / "web" / "data.js").read_bytes()
    t = raw.decode("utf-8")
    return json.loads(t[t.index("{"):t.rstrip().rindex(";")]), hashlib.sha256(raw).hexdigest()


def fixture_text(here, f, by_id):
    if not f.get("recipe"):
        return (here / f["file"]).read_bytes().decode("utf-8")
    r = f["recipe"]
    base = (here / by_id[r["from"]]["file"]).read_bytes().decode("utf-8")
    if r["op"] == "pad":
        return base[:-2] + " " * (r["total_bytes"] - len(base.encode("utf-8"))) + base[-2:]
    if r["op"] == "deep_field":
        return base.replace('"cases": [', '"pad": ' + "[" * r["depth"] + "]" * r["depth"] + ', "cases": [', 1)
    raise ValueError(r["op"])


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--app-root", required=True)
    ap.add_argument("--index")
    ap.add_argument("--problems")
    ap.add_argument("--out")
    ap.add_argument("--stdin", choices=["validate", "solve"], help="one envelope text on stdin -> one JSON line (harness self-test)")
    a = ap.parse_args(argv)
    data, data_sha = load_data(a.app_root)
    sys.setrecursionlimit(5000)
    if a.stdin:
        text = sys.stdin.buffer.read().decode("utf-8", "surrogatepass")
        try:
            env = validate_envelope(parse_strict(text), data)
        except Refused as e:
            print(json.dumps({"ok": False, "code": e.code}))
            return 0
        print(json.dumps({"ok": True, "result": solve(env, data) if a.stdin == "solve" else None}, ensure_ascii=False))
        return 0
    if a.index:
        idx_path = Path(a.index).resolve()
        idx = json.loads(idx_path.read_text(encoding="utf-8"))
        by_id = {f["id"]: f for f in idx["fixtures"]}
        rows, mism = [], []
        for f in idx["fixtures"]:
            text = fixture_text(idx_path.parent, f, by_id)
            if hashlib.sha256(text.encode("utf-8")).hexdigest() != f["sha256"]:
                raise SystemExit(f"{f['id']}: sha256 differs from index")
            try:
                validate_envelope(parse_strict(text), data)
                got, code = "accept", None
            except Refused as e:
                got, code = "reject", e.code
            ok = got == f["expect"] and (got == "accept" or code == f["rule"] or f["rule"] in ("bad_json",) and code in ("bad_json", "too_large"))
            rows.append({"id": f["id"], "expect": f["expect"], "rule": f["rule"], "oracle": got, "code": code, "match": ok})
            if not ok:
                mism.append(f"{f['id']}: expect {f['expect']}/{f['rule']}, oracle {got}/{code}")
        summary = {"data_js_sha256": data_sha, "index_data_js_sha256": idx["data_js_sha256"], "fixtures": len(rows),
                   "match": sum(r["match"] for r in rows), "mismatch": mism}
        print(json.dumps(summary, ensure_ascii=False))
        if a.out:
            Path(a.out).write_text(json.dumps({"summary": summary, "rows": rows}, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        return 1 if mism or data_sha != idx["data_js_sha256"] else 0
    probs = json.loads(Path(a.problems).read_text(encoding="utf-8"))["problems"]
    results = []
    for pr in probs:
        env = validate_envelope(json.loads(json.dumps(pr["envelope"])), data)
        r = solve(env, data)
        r["name"] = pr["name"]
        results.append(r)
    out = {"oracle": "k12-r9-resilience-oracle", "objective_version": "worst-lex-v1", "metric_version": "haversine-mm-v1",
           "data_js_sha256": data_sha, "results": results}
    text = json.dumps(out, ensure_ascii=False, indent=1) + "\n"
    if a.out:
        Path(a.out).write_text(text, encoding="utf-8")
    else:
        sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
