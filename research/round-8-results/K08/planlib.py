"""K08 R8: Python-движок city-plan-v2 для генератора отчёта (по research/round-8/CORE_SPEC.txt).

Независимая реализация на Python (не трансляция JS сборки). Только stdlib, без сети.
Контекст читается из --app-root (извлечённая prototypes/city-evidence): web/data.js, web/evidence.js, web/facts.js не нужен.

API:
  Context(app_root)                         — срез: города, bbox, записи, release, файлы, QA, атрибуция
  source_snapshot(ctx, city, schema)        — отпечаток среза (совместим со сборкой: JSON.stringify-эквивалент)
  loads_strict(text)                        — strict JSON (≤256 KiB, без дубликатов ключей, NaN/Infinity/1e999)
  validate_plan_scenario(obj, ctx)          — проверенный сценарий или PlanError(code, message)
  evaluate_plan(ctx, sc, selected_ids)      — rows + metrics + feasibility
  optimize_plans(ctx, sc, budget=None)      — status, objectives{mean,minimax,coverage}, pareto, evaluated, feasible_count, problem_digest
  sensitivity(ctx, sc)                      — бюджеты [0, floor(B/2), B] без дублей
  plan_result(ctx, sc)                      — всё вместе + provenance (вход генератора отчёта)
"""
import hashlib
import json
import math
import re
from pathlib import Path

SCHEMA = "city-plan-v2"
METRIC_VERSION = "haversine-mm-v1"
FORMULA = "haversine:R=6371008.8"
R_EARTH = 6371008.8
CATEGORIES = ("school", "outpatient_clinic")
CITIES = ("shymkent", "astana")
MAX_BYTES = 256 * 1024
TOP_KEYS = {"schema_version", "city_id", "source_snapshot", "category", "control_points", "candidates", "budget",
            "max_selected", "coverage_radius_m", "required_ids", "excluded_ids", "selected_ids"}
OPTIONAL_TOP = {"derived_results"}
CP_KEYS = {"id", "lon", "lat", "weight"}
CAND_KEYS = {"id", "lon", "lat", "category", "kind", "cost"}


class PlanError(ValueError):
    def __init__(self, code, message):
        super().__init__(f"{code}: {message}")
        self.code, self.message = code, message


# ---------------- JSON helpers ----------------
def js_json(v):
    """Эквивалент JSON.stringify для чисел/строк/массивов, используемых в отпечатках (целые float -> без .0)."""
    if isinstance(v, bool) or v is None:
        return json.dumps(v)
    if isinstance(v, float):
        if not math.isfinite(v):
            raise PlanError("non_finite", "в отпечатке нечисловое значение")
        if v == int(v) and abs(v) < 1e21:
            return str(int(v))
        return repr(v)
    if isinstance(v, int):
        return str(v)
    if isinstance(v, str):
        return json.dumps(v, ensure_ascii=False)
    if isinstance(v, (list, tuple)):
        return "[" + ",".join(js_json(x) for x in v) + "]"
    if isinstance(v, dict):
        return "{" + ",".join(json.dumps(k, ensure_ascii=False) + ":" + js_json(x) for k, x in v.items()) + "}"
    raise TypeError(type(v))


def sha256hex(s):
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def _reject_constant(tok):
    raise PlanError("bad_number", f"недопустимое число {tok}")


def _float(s):
    v = float(s)
    if not math.isfinite(v):
        raise PlanError("bad_number", f"недопустимое число {s}")
    return v


def _int(s):
    v = int(s)
    if abs(v) > 2 ** 53:
        raise PlanError("bad_number", f"слишком большое целое {s[:20]}")
    return v


def _pairs(pairs):
    keys = [k for k, _ in pairs]
    if len(keys) != len(set(keys)):
        raise PlanError("duplicate_key", "дубликат ключа в JSON")
    return dict(pairs)


def loads_strict(text):
    if isinstance(text, bytes):
        if len(text) > MAX_BYTES:
            raise PlanError("too_large", "JSON больше 256 KiB")
        text = text.decode("utf-8")
    if len(text.encode("utf-8")) > MAX_BYTES:
        raise PlanError("too_large", "JSON больше 256 KiB")
    try:
        return json.loads(text, parse_constant=_reject_constant, parse_float=_float, parse_int=_int, object_pairs_hook=_pairs)
    except PlanError:
        raise
    except (ValueError, RecursionError) as e:
        raise PlanError("bad_json", str(e)[:120])


def _window_json(path, var):
    txt = Path(path).read_text(encoding="utf-8")
    m = re.search(r"window\.%s\s*=\s*(\{.*\})\s*;?\s*$" % var, txt, re.S)
    if not m:
        raise PlanError("bad_context", f"{path}: нет window.{var}")
    return json.loads(m.group(1))


# ---------------- context ----------------
class Context:
    def __init__(self, app_root):
        self.root = Path(app_root)
        self.data = _window_json(self.root / "web/data.js", "CITY_EVIDENCE")
        ev = self.root / "web/evidence.js"
        self.obs = _window_json(ev, "CITY_OBS") if ev.exists() else None
        self.data_js_sha256 = hashlib.sha256((self.root / "web/data.js").read_bytes()).hexdigest()
        self.evidence_js_sha256 = hashlib.sha256(ev.read_bytes()).hexdigest() if ev.exists() else None

    def city(self, city_id):
        if city_id not in self.data["cities"]:
            raise PlanError("bad_city", f"неизвестный город {city_id!r}")
        return self.data["cities"][city_id]

    def records(self, city_id, category):
        return [p for p in self.city(city_id)["places"] if p.get("group") == category]

    def qa(self, city_id, rec_id):
        if not self.obs:
            return {"available": False, "flags": []}
        q = self.obs["cities"][city_id]["qa"]
        flags = []
        if rec_id in q.get("category_doubt", {}):
            flags.append({"rule": q["category_doubt"][rec_id]["rule"], "reason": q["category_doubt"][rec_id]["reason"]})
        for d in q.get("possible_duplicates", []):
            if rec_id in (d.get("a"), d.get("b")):
                flags.append({"rule": "possible_duplicate:" + str(d.get("rule")), "other": d["b"] if d.get("a") == rec_id else d["a"]})
        for g in q.get("colocated", []):
            if rec_id in (g.get("ids") or []):
                flags.append({"rule": "colocated"})
        return {"available": True, "flags": flags}


def places_digest(ctx, city):
    r7 = lambda x: math.floor(x * 1e7 + 0.5) / 1e7  # noqa: E731  (= Math.round(x*1e7)/1e7)
    rows = sorted(([p["id"], r7(p["lon"]), r7(p["lat"])] for p in ctx.city(city)["places"]), key=lambda r: r[0])
    return sha256hex(js_json(rows))


def source_snapshot(ctx, city, schema=SCHEMA):
    """Тот же состав, что sourceSnapshot сборки (web/whatif.js), со schema данного контракта."""
    c = ctx.city(city)
    fsha = ((c.get("files") or {}).get("places_social") or {}).get("sha256")
    return "sha256:" + sha256hex(js_json([schema, city, c["release"], fsha, places_digest(ctx, city), FORMULA]))


# ---------------- geometry ----------------
def haversine_m(lon1, lat1, lon2, lat2):
    p1, p2 = math.radians(lat1), math.radians(lat2)
    h = math.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(math.radians(lon2 - lon1) / 2) ** 2
    h = min(1.0, max(0.0, h))
    return 2 * R_EARTH * math.asin(math.sqrt(h))


def to_mm(d_m):
    return math.floor(d_m * 1000 + 0.5)


# ---------------- validation ----------------
ID_MAX = 64


def _is_int(v):
    return isinstance(v, int) and not isinstance(v, bool)


def _is_num(v):
    return (isinstance(v, (int, float)) and not isinstance(v, bool)) and math.isfinite(v)


def _id(v, what):
    if not isinstance(v, str) or not (1 <= len(v) <= ID_MAX):
        raise PlanError("bad_id", f"{what}: id — строка 1..{ID_MAX}")
    return v


def validate_plan_scenario(obj, ctx):
    if not isinstance(obj, dict):
        raise PlanError("bad_type", "сценарий должен быть объектом")
    extra = set(obj) - TOP_KEYS - OPTIONAL_TOP
    if extra:
        raise PlanError("unexpected_field", f"неожиданные поля: {sorted(extra)}")
    missing = TOP_KEYS - set(obj)
    if missing:
        raise PlanError("missing_field", f"нет полей: {sorted(missing)}")
    if obj["schema_version"] != SCHEMA:
        raise PlanError("bad_version", "неизвестная schema_version")
    city = obj["city_id"]
    if city not in CITIES:
        raise PlanError("bad_city", "неизвестный город")
    ctx.city(city)
    if obj["category"] not in CATEGORIES:
        raise PlanError("bad_category", "неизвестная категория")
    if obj["source_snapshot"] != source_snapshot(ctx, city):
        raise PlanError("foreign_snapshot", "source_snapshot не совпадает с текущим срезом")
    bb = ctx.city(city)["bbox"]

    def coords(o, what):
        if not (_is_num(o.get("lon")) and _is_num(o.get("lat"))):
            raise PlanError("bad_coords", f"{what}: координаты не конечные числа")
        if not (-180 <= o["lon"] <= 180 and -90 <= o["lat"] <= 90):
            raise PlanError("bad_coords", f"{what}: координаты вне диапазона")
        if not (bb[0] <= o["lon"] <= bb[2] and bb[1] <= o["lat"] <= bb[3]):
            raise PlanError("outside_bbox", f"{what}: вне квадрата среза")

    cps = obj["control_points"]
    if not isinstance(cps, list) or not 1 <= len(cps) <= 25:
        raise PlanError("bad_points", "контрольных точек 1..25")
    out_cps = []
    for p in cps:
        if not isinstance(p, dict) or set(p) != CP_KEYS:
            raise PlanError("bad_point", f"контрольная точка: поля ровно {sorted(CP_KEYS)}")
        _id(p["id"], "контрольная точка")
        coords(p, f"точка {p['id']}")
        if not _is_int(p["weight"]) or not 1 <= p["weight"] <= 100:
            raise PlanError("bad_weight", f"точка {p['id']}: weight — целое 1..100")
        out_cps.append({"id": p["id"], "lon": p["lon"], "lat": p["lat"], "weight": p["weight"]})
    if len({p["id"] for p in out_cps}) != len(out_cps):
        raise PlanError("duplicate_id", "дубликаты id контрольных точек")

    cands = obj["candidates"]
    if not isinstance(cands, list) or len(cands) > 16:
        raise PlanError("bad_candidates", "кандидатов 0..16")
    out_c = []
    for c in cands:
        if not isinstance(c, dict) or set(c) != CAND_KEYS:
            raise PlanError("bad_candidate", f"кандидат: поля ровно {sorted(CAND_KEYS)}")
        _id(c["id"], "кандидат")
        coords(c, f"кандидат {c['id']}")
        if c["category"] != obj["category"]:
            raise PlanError("bad_candidate", f"кандидат {c['id']}: категория не совпадает со сценарием")
        if c["kind"] != "hypothetical":
            raise PlanError("bad_candidate", f"кандидат {c['id']}: kind должен быть hypothetical")
        if not _is_int(c["cost"]) or not 1 <= c["cost"] <= 1_000_000:
            raise PlanError("bad_cost", f"кандидат {c['id']}: cost — целое 1..1000000")
        out_c.append(dict((k, c[k]) for k in ("id", "lon", "lat", "category", "kind", "cost")))
    cids = [c["id"] for c in out_c]
    if len(set(cids)) != len(cids):
        raise PlanError("duplicate_id", "дубликаты id кандидатов")
    for k, lo, hi in (("budget", 0, 1_000_000), ("max_selected", 0, 5), ("coverage_radius_m", 100, 5000)):
        if not _is_int(obj[k]) or not lo <= obj[k] <= hi:
            raise PlanError("bad_" + k, f"{k} — целое {lo}..{hi}")
    sets = {}
    for k in ("required_ids", "excluded_ids", "selected_ids"):
        v = obj[k]
        if not isinstance(v, list) or any(not isinstance(x, str) for x in v) or len(set(v)) != len(v):
            raise PlanError("bad_" + k, f"{k}: уникальные строки")
        unknown = [x for x in v if x not in cids]
        if unknown:
            raise PlanError("unknown_ref", f"{k}: нет кандидатов {unknown[:3]}")
        sets[k] = list(v)
    if set(sets["required_ids"]) & set(sets["excluded_ids"]):
        raise PlanError("conflict", "required_ids и excluded_ids пересекаются")
    return {"schema_version": SCHEMA, "city_id": city, "source_snapshot": obj["source_snapshot"], "category": obj["category"],
            "control_points": out_cps, "candidates": out_c, "budget": obj["budget"], "max_selected": obj["max_selected"],
            "coverage_radius_m": obj["coverage_radius_m"], **sets}


# ---------------- precompute ----------------
class Problem:
    """Предвычисленные расстояния (мм): точка × исходная запись и точка × кандидат."""

    def __init__(self, ctx, sc):
        self.sc = sc
        recs = sorted(ctx.records(sc["city_id"], sc["category"]), key=lambda r: r["id"])
        self.recs = recs
        self.cands = sorted(sc["candidates"], key=lambda c: c["id"])
        self.cand_index = {c["id"]: i for i, c in enumerate(self.cands)}
        self.points = sorted(sc["control_points"], key=lambda p: p["id"])
        self.base = []      # (mm, key) ближайшей исходной записи или None
        self.cmm = []       # [mm до кандидата i]
        for p in self.points:
            best = None
            for r in recs:
                mm = to_mm(haversine_m(p["lon"], p["lat"], r["lon"], r["lat"]))
                k = (mm, "source:" + r["id"])
                if best is None or k < best:
                    best = k
            self.base.append(best)
            self.cmm.append([to_mm(haversine_m(p["lon"], p["lat"], c["lon"], c["lat"])) for c in self.cands])
        self.total_weight = sum(p["weight"] for p in self.points)


def _metrics(prob, idx):
    """idx — индексы выбранных кандидатов (в prob.cands). Возвращает метрики и after по точкам."""
    radius_mm = prob.sc["coverage_radius_m"] * 1000
    unknown = wsum = covered = 0
    mx = None
    afters = []
    for j, p in enumerate(prob.points):
        best = prob.base[j]
        for i in idx:
            k = (prob.cmm[j][i], "hypothetical:" + prob.cands[i]["id"])
            if best is None or k < best:
                best = k
        afters.append(best)
        if best is None:
            unknown += 1
            continue
        wsum += p["weight"] * best[0]
        if best[0] <= radius_mm:
            covered += p["weight"]
        mx = best[0] if mx is None else max(mx, best[0])
    cost = sum(prob.cands[i]["cost"] for i in idx)
    m = {"unknown_count": unknown, "weighted_sum_mm": wsum,
         "weighted_mean_mm": (wsum / prob.total_weight) if unknown == 0 else None,
         "max_mm": mx if unknown == 0 else None, "covered_weight": covered,
         "coverage_fraction": covered / prob.total_weight, "cost": cost}
    return m, afters


def _feasibility(prob, ids):
    sc = prob.sc
    reasons = []
    cost = sum(prob.cands[prob.cand_index[i]]["cost"] for i in ids)
    if cost > sc["budget"]:
        reasons.append(f"стоимость {cost} > бюджета {sc['budget']}")
    if len(ids) > sc["max_selected"]:
        reasons.append(f"выбрано {len(ids)} > max_selected {sc['max_selected']}")
    miss = sorted(set(sc["required_ids"]) - set(ids))
    if miss:
        reasons.append(f"не выбраны обязательные {miss}")
    exc = sorted(set(sc["excluded_ids"]) & set(ids))
    if exc:
        reasons.append(f"выбраны исключённые {exc}")
    return {"feasible": not reasons, "reasons": reasons}


def evaluate_plan(ctx, sc, selected_ids, prob=None):
    prob = prob or Problem(ctx, sc)
    ids = sorted(set(selected_ids))
    unknown_ids = [i for i in ids if i not in prob.cand_index]
    if unknown_ids:
        raise PlanError("unknown_ref", f"нет кандидатов {unknown_ids[:3]}")
    idx = [prob.cand_index[i] for i in ids]
    m, afters = _metrics(prob, idx)
    rows = []
    for j, p in enumerate(prob.points):
        b, a = prob.base[j], afters[j]
        rows.append({"id": p["id"], "weight": p["weight"],
                     "before_mm": b[0] if b else None, "after_mm": a[0] if a else None,
                     "delta_mm": (b[0] - a[0]) if (b and a) else None,
                     "nearest_before": _ref(b), "nearest_after": _ref(a)})
    return {"selected_ids": ids, "rows": rows, "metrics": m, "feasibility": _feasibility(prob, ids)}


def _ref(k):
    if k is None:
        return None
    kind, rid = k[1].split(":", 1)
    return {"kind": kind, "id": rid}


def _canon_problem(sc, budget=None):
    return {"schema_version": SCHEMA, "metric_version": METRIC_VERSION, "formula": FORMULA,
            "source_snapshot": sc["source_snapshot"], "city_id": sc["city_id"], "category": sc["category"],
            "control_points": sorted(([p["id"], p["lon"], p["lat"], p["weight"]] for p in sc["control_points"]), key=lambda r: r[0]),
            "candidates": sorted(([c["id"], c["lon"], c["lat"], c["cost"]] for c in sc["candidates"]), key=lambda r: r[0]),
            "budget": sc["budget"] if budget is None else budget, "max_selected": sc["max_selected"],
            "coverage_radius_m": sc["coverage_radius_m"],
            "required_ids": sorted(sc["required_ids"]), "excluded_ids": sorted(sc["excluded_ids"])}


def problem_digest(sc, budget=None):
    """Не зависит от порядка массивов; selected_ids не входит."""
    return "sha256:" + sha256hex(js_json(_canon_problem(sc, budget)))


def scenario_digest(sc):
    """Ручной сценарий: problem + selected_ids."""
    return "sha256:" + sha256hex(js_json([_canon_problem(sc), sorted(sc["selected_ids"])]))


INF = float("inf")
KEYS = {
    "mean": lambda m, ids: (m["unknown_count"], m["weighted_sum_mm"], INF if m["max_mm"] is None else m["max_mm"], m["cost"], ids),
    "minimax": lambda m, ids: (m["unknown_count"], INF if m["max_mm"] is None else m["max_mm"], m["weighted_sum_mm"], m["cost"], ids),
    "coverage": lambda m, ids: (-m["covered_weight"], m["unknown_count"], m["weighted_sum_mm"], INF if m["max_mm"] is None else m["max_mm"], m["cost"], ids),
}


def optimize_plans(ctx, sc, budget=None, prob=None):
    prob = prob or Problem(ctx, sc)
    B = sc["budget"] if budget is None else budget
    n = len(prob.cands)
    if n > 16:
        raise PlanError("too_many_candidates", "точный перебор ограничен 16 кандидатами")
    req = {prob.cand_index[i] for i in sc["required_ids"]}
    exc = {prob.cand_index[i] for i in sc["excluded_ids"]}
    best = {k: None for k in KEYS}
    pareto = {}
    evaluated = feasible = 0
    for mask in range(1 << n):
        evaluated += 1
        idx = [i for i in range(n) if mask >> i & 1]
        s = set(idx)
        if not req <= s or s & exc or len(idx) > sc["max_selected"]:
            continue
        cost = sum(prob.cands[i]["cost"] for i in idx)
        if cost > B:
            continue
        feasible += 1
        m, _ = _metrics(prob, idx)
        ids = sorted(prob.cands[i]["id"] for i in idx)
        for k, f in KEYS.items():
            key = f(m, ids)
            if best[k] is None or key < best[k][0]:
                best[k] = (key, ids, m)
        if m["unknown_count"] == 0:
            pair = (m["cost"], m["weighted_sum_mm"])
            if pair not in pareto or ids < pareto[pair]:
                pareto[pair] = ids
    out = {"status": "optimal" if feasible else "infeasible", "budget": B, "metric_version": METRIC_VERSION,
           "evaluated": evaluated, "feasible_count": feasible, "problem_digest": problem_digest(sc, B),
           "search": "exhaustive", "objectives": {}, "pareto": []}
    if not feasible:
        reasons = []
        rc = sum(prob.cands[i]["cost"] for i in req)
        if rc > B:
            reasons.append(f"стоимость обязательных {rc} > бюджета {B}")
        if len(req) > sc["max_selected"]:
            reasons.append(f"обязательных {len(req)} > max_selected {sc['max_selected']}")
        out["infeasible_reasons"] = reasons or ["нет допустимых наборов при заданных ограничениях"]
        out["objectives"] = {k: None for k in KEYS}
        return out
    for k, (key, ids, m) in best.items():
        out["objectives"][k] = {"selected_ids": ids, "metrics": m}
    pts = sorted(pareto.items())
    front, best_sum = [], None
    for (cost, wsum), ids in pts:  # по возрастанию cost; оставить строго улучшающие weighted_sum
        if best_sum is None or wsum < best_sum:
            front.append({"cost": cost, "weighted_sum_mm": wsum, "selected_ids": ids})
            best_sum = wsum
    out["pareto"] = front
    return out


def sensitivity(ctx, sc, prob=None):
    prob = prob or Problem(ctx, sc)
    B = sc["budget"]
    out = []
    for b in sorted({0, B // 2, B}):
        r = optimize_plans(ctx, sc, b, prob)
        out.append({"budget": b, "status": r["status"],
                    "objectives": {k: (v["selected_ids"] if v else None) for k, v in r["objectives"].items()},
                    "mean_metrics": r["objectives"]["mean"]["metrics"] if r["objectives"].get("mean") else None,
                    "infeasible_reasons": r.get("infeasible_reasons")})
    return out


def record_provenance(ctx, city, rec_id):
    r = next((p for p in ctx.city(city)["places"] if p["id"] == rec_id), None)
    if r is None:
        return None
    return {"id": r["id"], "name": r.get("name"), "category_overture": r.get("category"), "group": r.get("group"),
            "lon": r["lon"], "lat": r["lat"], "confidence": r.get("confidence"), "overture_version": r.get("overture_version"),
            "sources": r.get("sources"), "qa": ctx.qa(city, r["id"]), "kind": "observed_secondary"}


def plan_result(ctx, sc):
    prob = Problem(ctx, sc)
    c = ctx.city(sc["city_id"])
    manual = evaluate_plan(ctx, sc, sc["selected_ids"], prob)
    opt = optimize_plans(ctx, sc, None, prob)
    plans = {"manual": manual}
    for k, v in opt["objectives"].items():
        plans[k] = evaluate_plan(ctx, sc, v["selected_ids"], prob) if v else None
    used = sorted({r["nearest_before"]["id"] for p in plans.values() if p for r in p["rows"] if r["nearest_before"]} |
                  {r["nearest_after"]["id"] for p in plans.values() if p for r in p["rows"]
                   if r["nearest_after"] and r["nearest_after"]["kind"] == "source"})
    return {
        "result_schema": "k08-plan-result/v1",
        "scenario": sc,
        "scenario_digest": scenario_digest(sc),
        "problem_digest": opt["problem_digest"],
        "metric_version": METRIC_VERSION, "formula": FORMULA,
        "context": {"city_id": sc["city_id"], "label": c.get("label"), "bbox": c["bbox"], "release": c["release"],
                    "retrieved_utc": c.get("retrieved_utc"), "source_snapshot": source_snapshot(ctx, sc["city_id"]),
                    "places_file": (c.get("files") or {}).get("places_social"), "inputs": ctx.data.get("inputs"),
                    "data_js_sha256": ctx.data_js_sha256, "evidence_js_sha256": ctx.evidence_js_sha256,
                    "attribution": c.get("attribution"), "records_in_slice": len(prob.recs)},
        "plans": plans,
        "optimization": opt,
        "sensitivity": sensitivity(ctx, sc, prob),
        "source_records": [record_provenance(ctx, sc["city_id"], i) for i in used],
    }
