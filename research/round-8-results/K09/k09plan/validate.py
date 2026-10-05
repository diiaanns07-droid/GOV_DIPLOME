"""Строгая проверка city-plan-v2 (CORE_SPEC «ФОРМАТ ВХОДА»), Python-аналог validatePlanScenario.

parse_import(text) -> dict | PlanError ; validate(scenario, context) -> список ошибок [{code, path}] (пусто = допустимо).
Не бросает исключений на неверных типах. derived_results разрешён, но игнорируется (пересчитывается).
"""
import json, math, re

MAX_BYTES = 256 * 1024
TOP = {"schema_version", "city_id", "source_snapshot", "category", "control_points", "candidates", "budget",
       "max_selected", "coverage_radius_m", "required_ids", "excluded_ids", "selected_ids"}
OPTIONAL = {"derived_results"}
CP = {"id", "lon", "lat", "weight"}
CAND = {"id", "lon", "lat", "category", "kind", "cost"}
ID_RE = re.compile(r"[\w.:-]{1,64}")


class PlanError(ValueError):
    def __init__(self, code, path=""):
        super().__init__(code)
        self.code, self.path = code, path


def _dupcheck(pairs):
    keys = [k for k, _ in pairs]
    if len(keys) != len(set(keys)):
        raise PlanError("duplicate_json_key")
    return dict(pairs)


def _const(name):
    raise PlanError("non_finite_literal", name)


def _flt(t):
    v = float(t)
    if not math.isfinite(v):
        raise PlanError("non_finite_number", t)
    return v


def parse_import(raw):
    b = raw.encode("utf-8") if isinstance(raw, str) else raw
    if len(b) > MAX_BYTES:
        raise PlanError("import_too_large")
    try:
        obj = json.loads(b.decode("utf-8"), parse_constant=_const, parse_float=_flt, object_pairs_hook=_dupcheck)
    except PlanError:
        raise
    except (ValueError, UnicodeDecodeError):
        raise PlanError("invalid_json")
    if not isinstance(obj, dict):
        raise PlanError("root_not_object")
    return obj


def _int(v, lo, hi):
    return isinstance(v, int) and not isinstance(v, bool) and lo <= v <= hi


def _num(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(float(v))


def validate(sc, ctx):
    if not isinstance(sc, dict):
        return [{"code": "scenario_not_object", "path": ""}]
    errs = []
    E = lambda code, path="": errs.append({"code": code, "path": path})
    extra = set(sc) - TOP - OPTIONAL
    if extra: E("unexpected_fields", ",".join(sorted(map(str, extra))))
    miss = TOP - set(sc)
    if miss: E("missing_fields", ",".join(sorted(miss)))
    if sc.get("schema_version") != "city-plan-v2": E("schema_version")
    if sc.get("city_id") != ctx["city_id"]: E("city_mismatch")
    if sc.get("category") != ctx["category"]: E("category_mismatch")
    if sc.get("source_snapshot") != ctx["source_snapshot"]: E("foreign_or_stale_snapshot")
    w, s, e, n = ctx["bbox"]

    def coords(o, path):
        lon, lat = o.get("lon"), o.get("lat")
        if not (_num(lon) and _num(lat)): E("bad_coordinates", path); return
        if not (w <= lon <= e and s <= lat <= n): E("outside_bbox", path)

    cps = sc.get("control_points")
    if not isinstance(cps, list) or not 1 <= len(cps) <= 25:
        E("control_points_count_1_25", "control_points"); cps = cps if isinstance(cps, list) else []
    ids = []
    for k, p in enumerate(cps):
        if not isinstance(p, dict): E("not_object", f"control_points[{k}]"); continue
        if set(p) != CP: E("fields", f"control_points[{k}]")
        if not _int(p.get("weight"), 1, 100): E("weight_int_1_100", f"control_points[{k}]")
        coords(p, f"control_points[{k}]"); ids.append(p.get("id"))
    if any(not isinstance(i, str) or not ID_RE.fullmatch(i) for i in ids): E("bad_id", "control_points")
    elif len(ids) != len(set(ids)): E("duplicate_id", "control_points")
    cands = sc.get("candidates")
    if not isinstance(cands, list) or len(cands) > 16:
        E("candidates_count_0_16", "candidates"); cands = cands if isinstance(cands, list) else []
    cids = []
    for k, c in enumerate(cands):
        if not isinstance(c, dict): E("not_object", f"candidates[{k}]"); continue
        if set(c) != CAND: E("fields", f"candidates[{k}]")
        if c.get("kind") != "hypothetical": E("kind_not_hypothetical", f"candidates[{k}]")
        if c.get("category") != ctx["category"]: E("candidate_category_mismatch", f"candidates[{k}]")
        if not _int(c.get("cost"), 1, 1_000_000): E("cost_int_1_1e6", f"candidates[{k}]")
        coords(c, f"candidates[{k}]"); cids.append(c.get("id"))
    if any(not isinstance(i, str) or not ID_RE.fullmatch(i) for i in cids): E("bad_id", "candidates")
    elif len(cids) != len(set(cids)): E("duplicate_id", "candidates")
    src_ids = {x["id"] for x in ctx["sources"]}
    if set(i for i in cids if isinstance(i, str)) & src_ids: E("candidate_id_collides_with_source", "candidates")
    if not _int(sc.get("budget"), 0, 1_000_000): E("budget_int_0_1e6", "budget")
    if not _int(sc.get("max_selected"), 0, 5): E("max_selected_int_0_5", "max_selected")
    if not _int(sc.get("coverage_radius_m"), 100, 5000): E("radius_int_100_5000", "coverage_radius_m")
    cset = set(i for i in cids if isinstance(i, str))
    lists = {}
    for name in ("required_ids", "excluded_ids", "selected_ids"):
        v = sc.get(name)
        if not isinstance(v, list) or any(not isinstance(i, str) for i in v): E("not_id_list", name); lists[name] = []; continue
        if len(v) != len(set(v)): E("duplicate_id", name)
        if set(v) - cset: E("unknown_candidate_ref", name)
        lists[name] = v
    if set(lists.get("required_ids", [])) & set(lists.get("excluded_ids", [])): E("required_excluded_overlap")
    return errs
