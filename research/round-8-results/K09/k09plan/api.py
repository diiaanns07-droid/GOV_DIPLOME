"""JSON-совместимый адаптер к интерфейсу CORE_SPEC (Python-оракул; не трансляция JS сборщика).

validate_plan_scenario(input, context) -> (scenario, []) | (None, [ошибки])
evaluate_plan(context, scenario, selected_ids) -> {rows, metrics, feasibility}
optimize_plans(context, scenario) -> {status, objectives, pareto, evaluated, feasible_count, problem_digest, metric_version, ...}
context: {city_id, category, bbox, source_snapshot, sources:[{id,lon,lat}], metric_version}.
"""
import hashlib, json
from . import METRIC_VERSION
from .metric import Problem
from .exact import optimize, problem_digest, budget_sensitivity
from .validate import parse_import, validate, PlanError


def problem_of(context, scenario):
    return Problem(scenario["control_points"], context["sources"], scenario["candidates"], scenario["coverage_radius_m"])


def scenario_digest(context, scenario):
    """Digest ручного сценария: problem_digest + отсортированный selected_ids."""
    payload = {"problem_digest": problem_digest(context, scenario), "selected": sorted(scenario["selected_ids"])}
    return "sha256:" + hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def validate_plan_scenario(inp, context):
    try:
        sc = parse_import(inp) if isinstance(inp, (str, bytes)) else inp
    except PlanError as e:
        return None, [{"code": e.code, "path": e.path}]
    errs = validate(sc, context)
    return (None, errs) if errs else (sc, [])


def evaluate_plan(context, scenario, selected_ids):
    pr = problem_of(context, scenario)
    unknown_ids = sorted(set(selected_ids) - set(pr.cand_index))
    if unknown_ids:
        return {"feasibility": {"feasible": False, "reasons": ["unknown_candidate_ref"]}, "rows": None, "metrics": None}
    sel = sorted(pr.cand_index[c] for c in set(selected_ids))
    reasons = []
    if len(sel) > scenario["max_selected"]: reasons.append("count_exceeds_max_selected")
    if sum(pr.cost[i] for i in sel) > scenario["budget"]: reasons.append("cost_exceeds_budget")
    if set(scenario["required_ids"]) - set(selected_ids): reasons.append("missing_required")
    if set(scenario["excluded_ids"]) & set(selected_ids): reasons.append("contains_excluded")
    return {"feasibility": {"feasible": not reasons, "reasons": reasons}, "rows": pr.rows(sel), "metrics": pr.evaluate(sel)}


def optimize_plans(context, scenario, with_pareto=True, with_sensitivity=True):
    pr = problem_of(context, scenario)
    args = (scenario["budget"], scenario["max_selected"], scenario["required_ids"], scenario["excluded_ids"])
    r = optimize(pr, *args, with_pareto=with_pareto)
    r["problem_digest"] = problem_digest(context, scenario)
    r["metric_version"] = METRIC_VERSION
    if with_sensitivity:
        r["budget_sensitivity"] = budget_sensitivity(pr, *args)
    return r
