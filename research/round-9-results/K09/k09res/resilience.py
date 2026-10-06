"""Независимый Python-оракул устойчивости city-resilience-v1 (CORE_SPEC раунда 9). Не трансляция JS сборки.

Геометрия и метрика v2 переиспользуются из проверенного r8-модуля (k09plan.metric: haversine-mm-v1, мм, null-семантика).
Случаи: base (пустое исключение, добавляется автоматически) + 1..7 пользовательских; в каждом случае baseline — только
исходные записи, не входящие в disabled_source_ids; кандидаты и ограничения одинаковы во всех случаях.
Потери плана в случае L = (unknown_count, weighted_sum_mm, max_mm), max=None → +inf только внутри сравнения.
W = lex-max L по всем случаям (включая base); worst_case_ids — все случаи с L == W, отсортированы.
Обычный план (nominal) = mean-оптимум v2 на base: ключ (L_base, cost, sorted ids).
Устойчивый план (robust) = минимум (W, L_base, cost, sorted ids).
Цена устойчивости = (mean_base(robust) − mean_base(nominal)) / 1000 м, только если оба optimal и base unknown = 0.
"""
import copy, hashlib, json, unicodedata
from . import r8  # noqa: F401  (подключает research/round-8-results/K09 в sys.path)
from k09plan.metric import Problem
from k09plan.exact import problem_digest as v2_problem_digest
from k09plan.validate import validate as v2_validate, parse_import

SCHEMA = "city-resilience-v1"
OBJECTIVE_VERSION = "worst-lex-v1"
METRIC_VERSION = "haversine-mm-v1"
MAX_CANDIDATES = 12
MAX_USER_CASES = 7
MAX_LABEL = 120
INF = float("inf")
ENV_KEYS = {"schema_version", "plan", "cases"}
CASE_KEYS = {"id", "label", "disabled_source_ids"}


class ResError(ValueError):
    def __init__(self, code, detail=""):
        super().__init__(f"{code}: {detail}")
        self.code, self.detail = code, detail


def _id_ok(v):
    """ID по правилам BUILD r8/r9: NFC, буквы любой письменности, цифры, _ . - ; 1..64 code points."""
    if not isinstance(v, str) or not 1 <= len(v) <= 64 or unicodedata.normalize("NFC", v) != v:
        return False
    return all(ch.isalnum() or ch in "_.-" for ch in v)


def _label_ok(v):
    """Непустая строка ≤120 code points без управляющих символов (Cc)."""
    return isinstance(v, str) and 1 <= len(v) <= MAX_LABEL and not any(unicodedata.category(ch) == "Cc" for ch in v)


# ---------------------------------------------------------------- validation
def validate_resilience(env, ctx):
    """env: разобранный объект (dict) или текст; ctx: контекст v2 (city_id, category, bbox, source_snapshot, sources).
    Возвращает чистую копию {schema_version, plan, cases} или бросает ResError. Лимит кандидатов проверяется ДО предвычислений."""
    if isinstance(env, (str, bytes)):
        try:
            env = parse_import(env)
        except Exception as e:            # PlanError r8 (размер, дубликаты ключей, NaN/Infinity/1e999, не объект)
            raise ResError(getattr(e, "code", "bad_json"), str(e))
    if not isinstance(env, dict):
        raise ResError("bad_shape", "ожидается объект")
    extra = set(env) - ENV_KEYS
    if extra:
        raise ResError("unknown_field", ",".join(sorted(map(str, extra))))
    if set(env) != ENV_KEYS:
        raise ResError("missing_field", ",".join(sorted(ENV_KEYS - set(env))))
    if env["schema_version"] != SCHEMA:
        raise ResError("bad_version", str(env["schema_version"])[:40])
    plan = env["plan"]
    if not isinstance(plan, dict):
        raise ResError("bad_shape", "plan — объект")
    if "derived_results" in plan:
        raise ResError("derived_not_accepted", "в r9 envelope производные поля не принимаются")
    cands = plan.get("candidates")
    if isinstance(cands, list) and len(cands) > MAX_CANDIDATES:
        raise ResError("too_many_candidates", f"устойчивость: кандидатов не больше {MAX_CANDIDATES}, получено {len(cands)}")
    errs = v2_validate(plan, ctx)
    if errs:
        raise ResError("bad_plan", ";".join(f"{e['code']}@{e['path']}" for e in errs[:5]))
    for k, lst in (("control_points", plan["control_points"]), ("candidates", plan["candidates"])):
        for o in lst:
            if not _id_ok(o["id"]):
                raise ResError("bad_id", f"{k}: {str(o['id'])[:40]}")
    cases = env["cases"]
    if not isinstance(cases, list) or not 1 <= len(cases) <= MAX_USER_CASES:
        raise ResError("bad_cases", f"пользовательских случаев 1..{MAX_USER_CASES}")
    src_ids = {s["id"] for s in ctx["sources"]}
    cand_ids = {c["id"] for c in plan["candidates"]}
    seen, clean = set(), []
    for k, c in enumerate(cases):
        if not isinstance(c, dict) or set(c) != CASE_KEYS:
            raise ResError("bad_case_shape", f"cases[{k}]")
        cid = c["id"]
        if not _id_ok(cid):
            raise ResError("bad_id", f"cases[{k}].id")
        if cid == "base":
            raise ResError("reserved_case_id", "id «base» зарезервирован")
        if cid in seen:
            raise ResError("duplicate_case_id", cid)
        seen.add(cid)
        if not _label_ok(c["label"]):
            raise ResError("bad_label", f"cases[{k}].label")
        ds = c["disabled_source_ids"]
        if not isinstance(ds, list) or not ds:
            raise ResError("bad_exclusions", f"cases[{k}]: хотя бы одна запись")
        if len(ds) != len(set(map(str, ds))):
            raise ResError("duplicate_exclusion", f"cases[{k}]")
        for s in ds:
            if not isinstance(s, str):
                raise ResError("bad_exclusions", f"cases[{k}]")
            if s in cand_ids and s not in src_ids:
                raise ResError("candidate_not_source", f"cases[{k}]: {s[:40]} — кандидат, а не исходная запись")
            if s not in src_ids:
                raise ResError("unknown_source", f"cases[{k}]: {s[:40]}")
        if len(ds) > len(src_ids):
            raise ResError("bad_exclusions", f"cases[{k}]: больше, чем записей")
        clean.append({"id": cid, "label": c["label"], "disabled_source_ids": sorted(ds)})
    return {"schema_version": SCHEMA, "plan": copy.deepcopy(plan), "cases": clean}


# ---------------------------------------------------------------- digests
def _sha(obj):
    return "sha256:" + hashlib.sha256(json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()


def exclusions_digest(env):
    return _sha(sorted([c["id"], sorted(c["disabled_source_ids"])] for c in env["cases"]))


def resilience_problem_digest(ctx, env):
    """Не зависит от порядка cases и ID; selected_ids не входит."""
    return _sha({"v2_problem_digest": v2_problem_digest(ctx, env["plan"]), "schema": SCHEMA, "metric": METRIC_VERSION,
                 "objective": OBJECTIVE_VERSION,
                 "cases": sorted([c["id"], c["label"], sorted(c["disabled_source_ids"])] for c in env["cases"])})


def resilience_scenario_digest(ctx, env):
    return _sha({"problem": resilience_problem_digest(ctx, env), "selected": sorted(env["plan"]["selected_ids"])})


# ---------------------------------------------------------------- precomputation
class CaseModel:
    """Расстояния считаются один раз: кандидаты (общие для всех случаев) и baseline каждого случая."""

    def __init__(self, ctx, env):
        plan = env["plan"]
        self.cases = [{"id": "base", "label": "base", "disabled_source_ids": []}] + list(env["cases"])
        self.pr = Problem(plan["control_points"], ctx["sources"], plan["candidates"], plan["coverage_radius_m"])
        pts = self.pr.points
        self.n = len(pts)
        self.weights = self.pr.weights
        self.total_weight = self.pr.total_weight
        self.radius_mm = self.pr.radius_mm
        src = sorted(ctx["sources"], key=lambda s: s["id"])
        from k09plan.metric import dist_mm
        src_mm = {s["id"]: [dist_mm(p["lon"], p["lat"], s["lon"], s["lat"]) for p in pts] for s in src}
        self.case_base = []
        for c in self.cases:
            off = set(c["disabled_source_ids"])
            on = [s["id"] for s in src if s["id"] not in off]
            self.case_base.append([min((src_mm[i][j] for i in on), default=None) for j in range(self.n)])

    def losses(self, candmin):
        """candmin: минимум по выбранным кандидатам (None — нет кандидатов). Возвращает [(L, metrics)] по случаям."""
        out = []
        for base in self.case_base:
            unknown = wsum = covered = 0
            mx = -1
            for w, b, c in zip(self.weights, base, candmin):
                a = b if c is None else (c if b is None or c < b else b)
                if a is None:
                    unknown += 1
                else:
                    wsum += w * a
                    if a > mx: mx = a
                    if a <= self.radius_mm: covered += w
            max_mm = mx if unknown == 0 and self.n else None
            out.append(((unknown, wsum, INF if max_mm is None else max_mm),
                        {"unknown_count": unknown, "weighted_sum_mm": wsum, "max_mm": max_mm, "covered_weight": covered,
                         "weighted_mean_mm": (wsum / self.total_weight) if unknown == 0 else None}))
        return out


def _worst(model, per):
    W = max(L for L, _ in per)
    ids = sorted(model.cases[k]["id"] for k, (L, _) in enumerate(per) if L == W)
    return W, ids


def _vec_out(L):
    return {"unknown_count": L[0], "weighted_sum_mm": L[1], "max_mm": None if L[2] == INF else L[2]}


def _plan_view(model, ids, cost, per, feasible=True):
    W, wids = _worst(model, per)
    return {"selected_ids": ids, "cost": cost, "feasible": feasible,
            "per_case": [{"case_id": model.cases[k]["id"], "label": model.cases[k]["label"], **m, "cost": cost} for k, (L, m) in enumerate(per)],
            "worst_vector": _vec_out(W), "worst_case_ids": wids, "base_vector": _vec_out(per[0][0])}


# ---------------------------------------------------------------- evaluate / optimize
def evaluate_resilience(ctx, env, selected_ids, model=None, validated=False):
    """Непроверенный env валидируется (лимит до предвычислений); validated=True — внутренний уже проверенный путь."""
    if not validated:
        env = validate_resilience(env, ctx)
    model = model or CaseModel(ctx, env)
    pr, plan = model.pr, env["plan"]
    ids = sorted(set(selected_ids))
    for c in ids:
        if c not in pr.cand_index:
            raise ResError("unknown_ref", c)
    idx = [pr.cand_index[c] for c in ids]
    candmin = [min((pr.cand_mm[i][j] for i in idx), default=None) for j in range(model.n)]
    cost = sum(pr.cost[i] for i in idx)
    reasons = []
    if cost > plan["budget"]: reasons.append("over_budget")
    if len(ids) > plan["max_selected"]: reasons.append("too_many")
    if set(plan["required_ids"]) - set(ids): reasons.append("missing_required")
    if set(plan["excluded_ids"]) & set(ids): reasons.append("has_excluded")
    v = _plan_view(model, ids, cost, model.losses(candmin), feasible=not reasons)
    v["infeasible_reasons"] = reasons
    return v


def optimize_resilience(ctx, env, validated=False):
    """Полный перебор ≤ 2^12 подмножеств; синхронно (Node/Python путь оракула).
    Непроверенный env валидируется: >12 кандидатов → ResError(too_many_candidates) до любых предвычислений."""
    if not validated:
        env = validate_resilience(env, ctx)
    if len(env["plan"]["candidates"]) > MAX_CANDIDATES:
        raise ResError("too_many_candidates", str(len(env["plan"]["candidates"])))
    model = CaseModel(ctx, env)
    pr, plan = model.pr, env["plan"]
    req = sorted(pr.cand_index[c] for c in plan["required_ids"])
    exc = {pr.cand_index[c] for c in plan["excluded_ids"]}
    free = [i for i in range(len(pr.cand_ids)) if i not in exc and i not in req]
    head = {"metric_version": METRIC_VERSION, "objective_version": OBJECTIVE_VERSION, "schema_version": SCHEMA,
            "resilience_problem_digest": resilience_problem_digest(ctx, env), "exclusions_digest": exclusions_digest(env),
            "source_snapshot": plan["source_snapshot"], "cases": [c["id"] for c in model.cases]}
    reasons = []
    if len(req) > plan["max_selected"]: reasons.append("required_exceeds_max_selected")
    if sum(pr.cost[i] for i in req) > plan["budget"]: reasons.append("required_cost_exceeds_budget")
    if reasons:
        return {**head, "status": "infeasible", "reasons": reasons, "nominal": None, "robust": None, "evaluated": 0, "feasible_count": 0,
                "price_of_robustness_m": None, "price_null_reason": "infeasible"}
    nf = len(free)
    room = plan["max_selected"] - len(req)
    base_cost = sum(pr.cost[i] for i in req)
    req_min = [min((pr.cand_mm[i][j] for i in req), default=None) for j in range(model.n)]
    cm, cost_of, cnt_of = {0: req_min}, {0: base_cost}, {0: 0}
    best_nom = best_rob = None
    evaluated = 0
    for mask in range(1 << nf):
        if mask:
            low = mask & -mask
            parent = mask ^ low
            if parent not in cm:
                continue
            c = free[low.bit_length() - 1]
            cnt, cost = cnt_of[parent] + 1, cost_of[parent] + pr.cost[c]
            if cnt > room or cost > plan["budget"]:
                continue
            row = pr.cand_mm[c]
            cm[mask] = [d if (v is None or d < v) else v for v, d in zip(cm[parent], row)]
            cost_of[mask], cnt_of[mask] = cost, cnt
        evaluated += 1
        per = model.losses(cm[mask])
        ids = sorted(pr.cand_ids[i] for i in req + [free[b] for b in range(nf) if mask >> b & 1])
        Lb = per[0][0]
        W = max(L for L, _ in per)
        knom = (Lb, cost_of[mask], ids)
        krob = (W, Lb, cost_of[mask], ids)
        if best_nom is None or knom < best_nom[0]:
            best_nom = (knom, mask, per)
        if best_rob is None or krob < best_rob[0]:
            best_rob = (krob, mask, per)
    nom = _plan_view(model, best_nom[0][2], best_nom[0][1], best_nom[2])
    rob = _plan_view(model, best_rob[0][3], best_rob[0][2], best_rob[2])
    nb, rb = best_nom[2][0][1], best_rob[2][0][1]
    if nb["weighted_mean_mm"] is None or rb["weighted_mean_mm"] is None:
        price, why = None, "base_unknown"
    else:
        price, why = (rb["weighted_mean_mm"] - nb["weighted_mean_mm"]) / 1000.0, None
    return {**head, "status": "optimal", "reasons": [], "nominal": nom, "robust": rob, "same_plan": nom["selected_ids"] == rob["selected_ids"],
            "evaluated": evaluated, "feasible_count": evaluated, "subsets_total": 1 << nf,
            "price_of_robustness_m": price, "price_null_reason": why}
