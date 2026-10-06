"""K10 round 9: independent Python oracle for city-resilience-v1 (research/round-9/CORE_SPEC.txt), stdlib only.

Re-uses the K10 r8 city-plan-v2 oracle (research/round-8-results/K10/k10plan/oracle.py) for strict JSON, plan
validation, haversine-mm-v1 and the v2 problem digest; only the resilience layer is new and is written from the
r9 spec, not translated from any BUILD code.

    validate_resilience(obj, context)            -> clean envelope (cases incl. automatic "base") | ResError(code)
    evaluate_resilience(context, env, ids)       -> per_case, worst_vector, worst_case_ids, feasibility
    optimize_resilience(context, env)            -> status, nominal, robust, manual, price_of_robustness_m, ...
    resilience_problem_digest(env) / resilience_scenario_digest(env)

Loss of a plan in a case: L = (unknown_count, weighted_sum_mm, max_mm), max null = +inf inside comparisons only.
Worst vector W = lexicographic max of L over all cases incl. base; worst_case_ids = every case with L == W, sorted.
Nominal = v2 mean optimum on base: min (L_base, cost, ids).  Robust = min (W, L_base, cost, ids).
"""
import hashlib
import itertools
import json
import sys
import unicodedata
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "round-8-results/K10"))
from k10plan import oracle as O  # noqa: E402

SCHEMA = "city-resilience-v1"
OBJECTIVE = "worst-lex-v1"
METRIC = O.METRIC_VERSION
MAX_CANDIDATES = 12
MAX_USER_CASES = 7
LABEL_MAX = 120
INF = float("inf")


class ResError(ValueError):
    def __init__(self, code, detail=""):
        super().__init__(f"{code}: {detail}")
        self.code, self.detail = code, detail


def build_id_ok(v):
    """ID rule of BUILD d865dd4 plan.js: NFC, 1..64 code points, letters of any script, digits, _ . -"""
    return (isinstance(v, str) and 1 <= len(v) <= 64 and unicodedata.normalize("NFC", v) == v
            and all(unicodedata.category(ch)[0] in "LN" or ch in "_.-" for ch in v))


# ---------------------------------------------------------------- validation
def validate_resilience(obj, context):
    """obj: parsed JSON (use O.parse_strict for text). context: r8 oracle context of the plan's city."""
    if not isinstance(obj, dict):
        raise ResError("bad_shape", "object expected")
    keys = set(obj)
    want = {"schema_version", "plan", "cases"}
    if want - keys:
        raise ResError("missing_field", ",".join(sorted(want - keys)))
    if keys - want:
        raise ResError("unexpected_field", ",".join(sorted(keys - want)))
    if obj["schema_version"] != SCHEMA:
        raise ResError("bad_schema_version", str(obj["schema_version"])[:40])
    plan = obj["plan"]
    if isinstance(plan, dict) and "derived_results" in plan:
        raise ResError("derived_not_allowed", "derived fields are neither exported nor accepted in city-resilience-v1")
    try:
        sc = O.validate_plan_scenario(plan, context)
    except O.PlanError as e:
        raise ResError(e.code, e.detail) from None
    for what, arr in (("control_points", sc["control_points"]), ("candidates", sc["candidates"])):
        for p in arr:
            if not build_id_ok(p["id"]):
                raise ResError("bad_id", f"{what}: {p['id'][:40]!r}")
    if len(sc["candidates"]) > MAX_CANDIDATES:
        raise ResError("too_many_candidates", f"resilience analysis: at most {MAX_CANDIDATES} candidates, got {len(sc['candidates'])}")
    cases = obj["cases"]
    if not isinstance(cases, list) or not 1 <= len(cases) <= MAX_USER_CASES:
        raise ResError("bad_case_count", f"cases: 1..{MAX_USER_CASES} user cases (base is added automatically)")
    sources = {r["id"] for r in context["records"] if r["group"] == sc["category"]}
    cand_ids = {c["id"] for c in sc["candidates"]}
    out, seen = [], set()
    for i, c in enumerate(cases):
        what = f"cases[{i}]"
        if not isinstance(c, dict) or set(c) != {"id", "label", "disabled_source_ids"}:
            raise ResError("bad_shape", f"{what}: fields id, label, disabled_source_ids")
        if not build_id_ok(c["id"]):
            raise ResError("bad_id", f"{what}.id")
        if c["id"] == "base":
            raise ResError("reserved_case_id", "base is added automatically")
        if c["id"] in seen:
            raise ResError("duplicate_case_id", c["id"])
        seen.add(c["id"])
        lab = c["label"]
        if (not isinstance(lab, str) or not lab.strip() or len(lab) > LABEL_MAX
                or any(unicodedata.category(ch) == "Cc" for ch in lab)):
            raise ResError("bad_label", f"{what}.label: non-empty text, <= {LABEL_MAX} code points, no control characters")
        ds = c["disabled_source_ids"]
        if not isinstance(ds, list) or not ds:
            raise ResError("bad_disabled", f"{what}.disabled_source_ids: at least one source id")
        if not all(isinstance(x, str) for x in ds):
            raise ResError("bad_id", f"{what}.disabled_source_ids: strings expected")
        if len(set(ds)) != len(ds):
            raise ResError("duplicate_id", f"{what}.disabled_source_ids")
        for x in ds:
            if x not in sources:
                code = "candidate_id_not_source" if x in cand_ids else "unknown_source_id"
                raise ResError(code, f"{what}: {x[:40]}")
        out.append({"id": c["id"], "label": lab, "disabled_source_ids": sorted(ds)})
    return {"schema_version": SCHEMA, "plan": sc,
            "cases": [{"id": "base", "label": "base", "disabled_source_ids": []}] + sorted(out, key=lambda c: c["id"])}


# ---------------------------------------------------------------- digests
def _canon(o):
    return json.dumps(o, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _payload(env):
    return {"schema": SCHEMA, "metric_version": METRIC, "objective_version": OBJECTIVE,
            "plan_problem_digest": O.problem_digest(env["plan"]),
            "cases": sorted([c["id"], c["label"], sorted(c["disabled_source_ids"])] for c in env["cases"])}


def resilience_problem_digest(env):
    return "sha256:" + hashlib.sha256(_canon(_payload(env)).encode("utf-8")).hexdigest()


def resilience_scenario_digest(env):
    p = _payload(env)
    p["selected_ids"] = sorted(env["plan"]["selected_ids"])
    return "sha256:" + hashlib.sha256(_canon(p).encode("utf-8")).hexdigest()


def exclusions_digest(env):
    return "sha256:" + hashlib.sha256(_canon(sorted([c["id"], sorted(c["disabled_source_ids"])] for c in env["cases"])).encode()).hexdigest()


# ---------------------------------------------------------------- precomputation (haversine once per pair)
class CaseMatrix:
    def __init__(self, context, env):
        sc = env["plan"]
        self.sc = sc
        pool = sorted((r for r in context["records"] if r["group"] == sc["category"]), key=lambda r: r["id"])
        self.cps, self.cands = sc["control_points"], sc["candidates"]
        self.cand_index = {c["id"]: j for j, c in enumerate(self.cands)}
        self.weights = [p["weight"] for p in self.cps]
        self.total_weight = sum(self.weights)
        src = [[(O.to_mm(O.haversine_m(p["lon"], p["lat"], r["lon"], r["lat"])), 0, r["id"]) for r in pool] for p in self.cps]
        self.cand = [[O.to_mm(O.haversine_m(p["lon"], p["lat"], c["lon"], c["lat"])) for c in self.cands] for p in self.cps]
        self.cases = env["cases"]
        self.pool_ids = [r["id"] for r in pool]
        self.base = []      # base[k][i]: nearest allowed source key in case k, or None
        self.records = []   # number of source records left in case k
        for c in self.cases:
            off = set(c["disabled_source_ids"])
            self.base.append([min((k for k in row if k[2] not in off), default=None) for row in src])
            self.records.append(sum(1 for x in self.pool_ids if x not in off))

    def after(self, k, i, sel):
        best = self.base[k][i]
        for j in sel:
            key = (self.cand[i][j], 1, self.cands[j]["id"])
            if best is None or key < best:
                best = key
        return best

    def case_metrics(self, k, sel):
        unknown = wsum = covered = 0
        mx = None
        rad = self.sc["coverage_radius_m"] * 1000
        for i, w in enumerate(self.weights):
            a = self.after(k, i, sel)
            if a is None:
                unknown += 1
                continue
            wsum += w * a[0]
            mx = a[0] if mx is None else max(mx, a[0])
            covered += w if a[0] <= rad else 0
        return {"unknown_count": unknown, "weighted_sum_mm": wsum,
                "weighted_mean_mm": wsum / self.total_weight if unknown == 0 else None,
                "max_mm": mx if unknown == 0 else None, "covered_weight": covered,
                "coverage_fraction": covered / self.total_weight, "cost": sum(self.cands[j]["cost"] for j in sel)}


def loss(met):
    return (met["unknown_count"], met["weighted_sum_mm"], INF if met["max_mm"] is None else met["max_mm"])


def loss_json(lv):
    return [lv[0], lv[1], None if lv[2] == INF else lv[2]]


def _worst(per_case_losses, case_ids):
    w = max(per_case_losses)
    return w, sorted(cid for cid, lv in zip(case_ids, per_case_losses) if lv == w)


def _feasibility(sc, ids, cost):
    reasons = []
    if len(ids) > sc["max_selected"]:
        reasons.append("count_exceeds_max_selected")
    if cost > sc["budget"]:
        reasons.append("cost_exceeds_budget")
    if set(sc["required_ids"]) - set(ids):
        reasons.append("required_missing")
    if set(ids) & set(sc["excluded_ids"]):
        reasons.append("excluded_selected")
    return {"feasible": not reasons, "reasons": reasons}


def _summary(m, sel, with_rows=False):
    ids = sorted(m.cands[j]["id"] for j in sel)
    per, losses = [], []
    for k, c in enumerate(m.cases):
        met = m.case_metrics(k, sel)
        losses.append(loss(met))
        row = {"case_id": c["id"], "label": c["label"], "disabled_source_ids": c["disabled_source_ids"],
               "baseline_records": m.records[k], "metrics": met, "loss": loss_json(losses[-1])}
        if with_rows:
            rr = []
            for i, p in enumerate(m.cps):
                b, a = m.base[k][i], m.after(k, i, sel)
                rr.append({"control_point_id": p["id"], "before_mm": b[0] if b else None,
                           "nearest_before": {"kind": "source", "id": b[2]} if b else None,
                           "after_mm": a[0] if a else None,
                           "nearest_after": ({"kind": "source" if a[1] == 0 else "hypothetical", "id": a[2]} if a else None),
                           "delta_mm": b[0] - a[0] if (b and a) else None})
            row["rows"] = rr
        per.append(row)
    w, worst_ids = _worst(losses, [c["id"] for c in m.cases])
    cost = sum(m.cands[j]["cost"] for j in sel)
    return {"selected_ids": ids, "cost": cost, "per_case": per, "worst_vector": loss_json(w), "worst_case_ids": worst_ids,
            "feasibility": _feasibility(m.sc, ids, cost)}


def evaluate_resilience(context, env, selected_ids, with_rows=True):
    m = CaseMatrix(context, env)
    bad = [x for x in selected_ids if x not in m.cand_index]
    if bad:
        raise ResError("unknown_candidate", bad[0])
    return _summary(m, sorted(m.cand_index[x] for x in set(selected_ids)), with_rows)


def optimize_resilience(context, env, with_rows=False):
    m = CaseMatrix(context, env)
    sc = m.sc
    req = sorted(m.cand_index[x] for x in sc["required_ids"])
    free = [j for j in range(len(m.cands)) if j not in req and m.cands[j]["id"] not in set(sc["excluded_ids"])]
    evaluated = feasible = 0
    best_nom = best_rob = None
    for k in range(0, max(0, sc["max_selected"] - len(req)) + 1):
        if len(req) + k > sc["max_selected"]:
            break
        for extra in itertools.combinations(free, k):
            sel = sorted(req + list(extra))
            evaluated += 1
            cost = sum(m.cands[j]["cost"] for j in sel)
            if cost > sc["budget"]:
                continue
            feasible += 1
            losses = [loss(m.case_metrics(c, sel)) for c in range(len(m.cases))]
            ids = sorted(m.cands[j]["id"] for j in sel)
            nom_key = (losses[0], cost, ids)
            rob_key = (max(losses), losses[0], cost, ids)
            if best_nom is None or nom_key < best_nom[0]:
                best_nom = (nom_key, sel)
            if best_rob is None or rob_key < best_rob[0]:
                best_rob = (rob_key, sel)
    out = {"schema_version": SCHEMA, "metric_version": METRIC, "objective_version": OBJECTIVE,
           "resilience_problem_digest": resilience_problem_digest(env), "resilience_scenario_digest": resilience_scenario_digest(env),
           "exclusions_digest": exclusions_digest(env), "source_snapshot": sc["source_snapshot"],
           "case_ids": [c["id"] for c in m.cases], "evaluated": evaluated, "feasible_count": feasible,
           "candidate_count": len(m.cands)}
    out["manual"] = _summary(m, sorted(m.cand_index[x] for x in sc["selected_ids"]), with_rows)
    if not feasible:
        reasons = []
        if len(req) > sc["max_selected"]:
            reasons.append("required_count_exceeds_max_selected")
        if sum(m.cands[j]["cost"] for j in req) > sc["budget"]:
            reasons.append("required_cost_exceeds_budget")
        out.update(status="infeasible", infeasible_reasons=reasons or ["no_subset_satisfies_constraints"], nominal=None,
                   robust=None, plans_identical=None, price_of_robustness_m=None, price_reason="no feasible plan")
        return out
    nom, rob = _summary(m, best_nom[1], with_rows), _summary(m, best_rob[1], with_rows)
    out.update(status="optimal", infeasible_reasons=None, nominal=nom, robust=rob,
               plans_identical=nom["selected_ids"] == rob["selected_ids"])
    a, b = rob["per_case"][0]["metrics"]["weighted_mean_mm"], nom["per_case"][0]["metrics"]["weighted_mean_mm"]
    if a is None or b is None:
        out.update(price_of_robustness_m=None, price_reason="base weighted mean unknown for the nominal or robust plan")
    else:
        out.update(price_of_robustness_m=(a - b) / 1000, price_reason=None)
    return out
