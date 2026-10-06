"""K06 round 9 stage 2: independent Python reference for city-resilience-v1 (round-9 CORE_SPEC), stdlib only.

Builds on K06's own city-plan-v2 oracle (r8/plan_oracle.py, byte copy) for geometry and v2 constraints; nothing is
translated from the BUILD's JS. Distances: haversine-mm-v1. Objective: "worst-lex-v1".

API
  validate_envelope(envelope_or_text, ctx) -> clean envelope {schema_version, plan, cases(with auto "base" first)}
  evaluate_resilience(ctx, envelope, selected_ids) -> {per_case, worst_vector, worst_case_ids, feasible, reasons}
  optimize_resilience(ctx, envelope) -> {status, reasons, nominal, robust, price_of_robustness_m, price_reason,
                                         evaluated, feasible_count, resilience_problem_digest, metric_version, objective_version}
Definitions (CORE_SPEC r9):
  case baseline   = source records of the plan's category minus that case's disabled_source_ids (context not mutated)
  L(case)         = (unknown_count, weighted_sum_mm, max_mm), max None -> +inf inside comparisons only
  W               = lexicographic max of L over all cases incl. "base"; worst_case_ids = all cases with L == W, sorted
  nominal         = v2 mean optimum on base
  robust          = feasible set minimising (W, L_base, cost, sorted candidate IDs)
  price           = (robust base weighted_mean_mm - nominal base weighted_mean_mm) / 1000, only if both known & optimal
External JSON never contains infinity: worst_vector max is null when unknown.
"""
import hashlib, json, math, os, sys, unicodedata
from itertools import combinations
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "r8"))
import plan_oracle as O

SCHEMA = "city-resilience-v1"
OBJECTIVE = "worst-lex-v1"
MAX_CANDIDATES = 12
MAX_USER_CASES = 7
MAX_LABEL = 120
INF = float("inf")


class ResilienceError(O.PlanError):
    pass


def fail(code, detail=""):
    raise ResilienceError(code, detail)


def _label_ok(s):
    return isinstance(s, str) and 1 <= len(s) <= MAX_LABEL and s.strip() != "" and \
        not any(unicodedata.category(ch) == "Cc" for ch in s)


def validate_envelope(env, ctx):
    if isinstance(env, (str, bytes)):
        env = O.parse_strict(env)                  # <=256 KiB, duplicate keys, NaN/Infinity/1e999 rejected
    if not isinstance(env, dict):
        fail("bad_shape", "envelope must be an object")
    keys = set(env)
    if keys - {"schema_version", "plan", "cases"}:
        fail("unexpected_field", ",".join(sorted(keys - {"schema_version", "plan", "cases"})))   # incl. derived fields
    if keys != {"schema_version", "plan", "cases"}:
        fail("missing_field", ",".join(sorted({"schema_version", "plan", "cases"} - keys)))
    if env["schema_version"] != SCHEMA:
        fail("bad_version", str(env["schema_version"])[:40])
    plan = O.validate(env["plan"], ctx)            # full v2 validation (<= 16 candidates)
    if len(plan["candidates"]) > MAX_CANDIDATES:
        fail("too_many_candidates", f"{len(plan['candidates'])} > {MAX_CANDIDATES}")      # before any precomputation
    cases = env["cases"]
    if not isinstance(cases, list) or not 1 <= len(cases) <= MAX_USER_CASES:
        fail("bad_cases", "1..7 user cases")
    src_ids = {str(r["id"]) for r in ctx["records"] if r.get("group") == plan["category"]}
    cand_ids = {c["id"] for c in plan["candidates"]}
    seen, clean = set(), [{"id": "base", "label": "base", "disabled_source_ids": []}]
    for c in cases:
        if not isinstance(c, dict) or set(c) != {"id", "label", "disabled_source_ids"}:
            fail("bad_case", "case keys must be exactly id, label, disabled_source_ids")
        cid = c["id"]
        if not isinstance(cid, str) or not cid or len(cid) > O.MAX_ID:
            fail("bad_id", "case id")
        if cid == "base":
            fail("reserved_id", "base")
        if cid in seen:
            fail("duplicate_id", cid)
        seen.add(cid)
        if not _label_ok(c["label"]):
            fail("bad_label", cid)
        d = c["disabled_source_ids"]
        if not isinstance(d, list) or not d or len(d) > len(src_ids):
            fail("bad_disabled", f"{cid}: 1..{len(src_ids)} source ids")
        if len(set(d)) != len(d):
            fail("duplicate_id", f"{cid}: disabled_source_ids")
        for x in d:
            if x in cand_ids and x not in src_ids:
                fail("candidate_not_source", f"{cid}: {x}")
            if x not in src_ids:
                fail("unknown_source", f"{cid}: {x}")
        clean.append({"id": cid, "label": c["label"], "disabled_source_ids": sorted(d)})
    return {"schema_version": SCHEMA, "plan": plan, "cases": clean}


def _case_ctx(ctx, plan, case):
    off = set(case["disabled_source_ids"])
    return dict(ctx, records=[r for r in ctx["records"] if not (r.get("group") == plan["category"] and str(r["id"]) in off)])


def _L(m):
    return (m["unknown_count"], m["weighted_sum_mm"], INF if m["max_mm"] is None else m["max_mm"])


def _ext(L):
    return [L[0], L[1], None if L[2] == INF else L[2]]


def _summary(m):
    return {k: m[k] for k in ("unknown_count", "weighted_sum_mm", "weighted_mean_mm", "max_mm", "covered_weight",
                              "coverage_fraction", "cost")}


def _per_case(problems, env, ids):
    per, Ls = [], []
    for case, pr in zip(env["cases"], problems):
        _, m = pr.rows_metrics(ids)
        L = _L(m)
        Ls.append((L, case["id"]))
        per.append({"case_id": case["id"], "label": case["label"], "disabled_source_ids": case["disabled_source_ids"],
                    "metrics": _summary(m), "loss_vector": _ext(L)})
    W = max(L for L, _ in Ls)
    return per, W, sorted(cid for L, cid in Ls if L == W)


def _problems(ctx, env):
    return [O.Problem(_case_ctx(ctx, env["plan"], c), env["plan"]) for c in env["cases"]]


def evaluate_resilience(ctx, envelope, selected_ids):
    env = validate_envelope(envelope, ctx)
    plan = env["plan"]
    if len(set(selected_ids)) != len(selected_ids) or set(selected_ids) - {c["id"] for c in plan["candidates"]}:
        fail("bad_selection", "")
    probs = _problems(ctx, env)
    per, W, worst = _per_case(probs, env, sorted(selected_ids))
    reasons = probs[0].feasibility(sorted(selected_ids))
    return {"selected_ids": sorted(selected_ids), "per_case": per, "worst_vector": _ext(W), "worst_case_ids": worst,
            "feasible": not reasons, "reasons": reasons}


def resilience_problem_digest(ctx, env):
    body = {"schema": SCHEMA, "objective_version": OBJECTIVE, "metric_version": O.METRIC_VERSION,
            "plan_problem_digest": O.problem_digest(ctx, env["plan"]),
            "cases": sorted([c["id"], c["label"], sorted(c["disabled_source_ids"])] for c in env["cases"])}
    return "sha256:" + hashlib.sha256(json.dumps(body, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()


def optimize_resilience(ctx, envelope):
    env = validate_envelope(envelope, ctx)
    plan = env["plan"]
    out = {"metric_version": O.METRIC_VERSION, "objective_version": OBJECTIVE, "resilience_problem_digest":
           resilience_problem_digest(ctx, env), "nominal": None, "robust": None, "price_of_robustness_m": None,
           "price_reason": None, "evaluated": 0, "feasible_count": 0, "reasons": []}
    nom = O.optimize(ctx, plan)                    # v2 mean optimum on base (records unfiltered)
    if nom["status"] != "optimal":
        return dict(out, status="infeasible", reasons=nom.get("reasons", []), price_reason="no feasible plan")
    probs = _problems(ctx, env)
    req = sorted(plan["required_ids"])
    free = sorted({c["id"] for c in plan["candidates"]} - set(req) - set(plan["excluded_ids"]))
    cost = {c["id"]: c["cost"] for c in plan["candidates"]}
    best = None
    for k in range(len(free) + 1):
        for extra in combinations(free, k):
            out["evaluated"] += 1
            ids = sorted(req + list(extra))
            if len(ids) > plan["max_selected"] or sum(cost[i] for i in ids) > plan["budget"]:
                continue
            out["feasible_count"] += 1
            per, W, worst = _per_case(probs, env, ids)
            key = (W, _L(per[0]["metrics"]), sum(cost[i] for i in ids), ids)
            if best is None or key < best[0]:
                best = (key, ids, per, W, worst)

    def plan_view(ids):
        per, W, worst = _per_case(probs, env, ids)
        return {"selected_ids": ids, "worst_vector": _ext(W), "worst_case_ids": worst, "per_case": per}

    out["nominal"] = plan_view(nom["objectives"]["mean"]["selected_ids"])
    out["robust"] = plan_view(best[1])
    nb, rb = out["nominal"]["per_case"][0]["metrics"]["weighted_mean_mm"], out["robust"]["per_case"][0]["metrics"]["weighted_mean_mm"]
    if nb is None or rb is None:
        out["price_reason"] = "base weighted_mean unknown for nominal or robust plan"
    else:
        out["price_of_robustness_m"] = (rb - nb) / 1000
    out["status"] = "optimal"
    return out
