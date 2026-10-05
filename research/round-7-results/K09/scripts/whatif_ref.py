"""K09 round-7: независимая эталонная реализация расчёта «если добавить объект» по FEATURE_SPEC.txt.

Только stdlib. Входы читаются байтами из Git по закреплённому SHA прототипа (или из локальных файлов):
  prototypes/city-evidence/web/data.js     — window.CITY_EVIDENCE (места Overture в bbox города);
  prototypes/city-evidence/web/evidence.js — window.CITY_OBS (QA: colocated, possible_duplicates, category_doubt).
Это НЕ код прототипа и не замена ему; используется как оракул для сверки чисел интерфейса.
"""
import hashlib, json, math, re, subprocess
from pathlib import Path

BASE_SHA = "c58a3b2b175cf978ad785fef7f88d8fd9b1338f2"
DATA_PATH = "prototypes/city-evidence/web/data.js"
EVID_PATH = "prototypes/city-evidence/web/evidence.js"
R_EARTH = 6371008.8
CATEGORIES = ("school", "outpatient_clinic")
CITIES = ("shymkent", "astana")


def git_bytes(sha, path, repo=None):
    return subprocess.run(["git", "show", f"{sha}:{path}"], cwd=repo, capture_output=True, check=True).stdout


def parse_js_object(raw: bytes):
    s = raw.decode("utf-8")
    i = s.index("{")
    j = s.rstrip().rstrip(";").rstrip()
    return json.loads(s[i:len(j)])


def haversine_m(lon1, lat1, lon2, lat2):
    """Гаверсинус по спецификации: вход [lon, lat], R = 6371008.8 м, промежуточное a зажато в [0, 1], без округления."""
    r = math.pi / 180.0
    dphi = (lat2 - lat1) * r
    dlmb = (lon2 - lon1) * r
    a = math.sin(dphi / 2) ** 2 + math.cos(lat1 * r) * math.cos(lat2 * r) * math.sin(dlmb / 2) ** 2
    a = min(1.0, max(0.0, a))
    return 2 * R_EARTH * math.asin(math.sqrt(a))


class Slice:
    def __init__(self, data_bytes: bytes, evidence_bytes: bytes):
        self.data = parse_js_object(data_bytes)
        self.evid = parse_js_object(evidence_bytes)
        self.data_sha256 = hashlib.sha256(data_bytes).hexdigest()
        self.evid_sha256 = hashlib.sha256(evidence_bytes).hexdigest()

    @classmethod
    def from_git(cls, sha=BASE_SHA, repo=None):
        return cls(git_bytes(sha, DATA_PATH, repo), git_bytes(sha, EVID_PATH, repo))

    def bbox(self, city):
        return self.data["cities"][city]["bbox"]                     # [W, S, E, N]

    def in_bbox(self, city, lon, lat):
        w, s, e, n = self.bbox(city)
        return w <= lon <= e and s <= lat <= n

    def candidates(self, city, category):
        """Все записи выбранной категории внутри bbox среза; QA-записи НЕ удаляются."""
        return sorted((p for p in self.data["cities"][city]["places"]
                       if p.get("group") == category and self.in_bbox(city, p["lon"], p["lat"])), key=lambda p: p["id"])

    def qa_codes(self, city, pid):
        q = self.evid.get("cities", {}).get(city, {}).get("qa", {})
        out = []
        if any(pid in g.get("ids", []) for g in q.get("colocated", [])):
            out.append("COLOCATED")
        if any(pid in (d.get("a"), d.get("b")) for d in q.get("possible_duplicates", [])):
            out.append("POSSIBLE_DUPLICATE")
        if pid in q.get("category_doubt", {}):
            out.append("CATEGORY_DOUBT")
        return out

    def fingerprint(self, city, category):
        """Отпечаток K09 (не обязательно совпадает со схемой BUILD): кандидаты среза + параметры формулы."""
        payload = {"city": city, "category": category, "bbox": self.bbox(city),
                   "records": [[p["id"], p["lon"], p["lat"]] for p in self.candidates(city, category)],
                   "formula": "haversine/R=6371008.8/clamp[0,1]/no-rounding"}
        return "k09ref-sha256:" + hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


ID_RE = re.compile(r"^[A-Za-z0-9_.:-]{1,64}$")


def validate(sl: Slice, sc: dict):
    """Строгая проверка контракта city-whatif-v1 (минимум из FEATURE_SPEC). Возвращает список ошибок."""
    errs = []
    if sc.get("schema_version") != "city-whatif-v1": errs.append("unknown_schema_version")
    city, cat = sc.get("city_id"), sc.get("category")
    if city not in CITIES: errs.append("unknown_city"); return errs
    if cat not in CATEGORIES: errs.append("unknown_category")
    cps = sc.get("control_points")
    if not isinstance(cps, list) or not (1 <= len(cps) <= 10): errs.append("control_points_count_not_1_10")
    ids = []
    for cp in cps or []:
        ids.append(cp.get("id"))
        lon, lat = cp.get("lon"), cp.get("lat")
        if not (isinstance(lon, (int, float)) and isinstance(lat, (int, float)) and math.isfinite(lon) and math.isfinite(lat)):
            errs.append(f"non_finite_coord:{cp.get('id')}"); continue
        if not sl.in_bbox(city, lon, lat): errs.append(f"control_point_outside_bbox:{cp.get('id')}")
    po = sc.get("proposed_object")
    if isinstance(po, list): errs.append("more_than_one_proposed")
    elif po is not None:
        ids.append(po.get("id"))
        if po.get("kind") != "hypothetical": errs.append("proposed_kind_not_hypothetical")
        if po.get("category") != cat: errs.append("proposed_category_mismatch")
        lon, lat = po.get("lon"), po.get("lat")
        if not (isinstance(lon, (int, float)) and isinstance(lat, (int, float)) and math.isfinite(lon) and math.isfinite(lat)):
            errs.append("proposed_non_finite_coord")
        elif not sl.in_bbox(city, lon, lat): errs.append("proposed_outside_bbox")
    if any(not isinstance(i, str) or not ID_RE.match(i) for i in ids): errs.append("bad_id")
    if len(ids) != len(set(ids)): errs.append("duplicate_id")
    return errs


def compute(sl: Slice, sc: dict):
    """before/after/delta по FEATURE_SPEC; ничьи — стабильно по ID; QA-записи участвуют и помечаются."""
    errs = validate(sl, sc)
    if errs:
        return {"status": "rejected", "errors": errs}
    city, cat, po = sc["city_id"], sc["category"], sc.get("proposed_object")
    cands = sl.candidates(city, cat)
    w, s, e, n = sl.bbox(city)
    rows = []
    for cp in sc["control_points"]:
        lon, lat = cp["lon"], cp["lat"]
        dists = sorted(((haversine_m(lon, lat, p["lon"], p["lat"]), p["id"]) for p in cands))
        if dists:
            before, nb = dists[0]
            ties_before = [pid for d, pid in dists if d == before]
        else:
            before, nb, ties_before = None, None, []
        dp = haversine_m(lon, lat, po["lon"], po["lat"]) if po else None
        if before is None:
            after, delta, na = dp, None, (po["id"] if po else None)
        elif po is None:
            after, delta, na = before, 0.0, nb
        else:
            after = min(before, dp)
            delta = before - after
            na = min([(before, nb), (dp, po["id"])])[1]          # ничья -> меньший ID
        # расстояние до ближайшей стороны bbox по меридиану/параллели (оценка «объект вне среза может быть ближе»)
        edge = min(haversine_m(lon, lat, w, lat), haversine_m(lon, lat, e, lat),
                   haversine_m(lon, lat, lon, s), haversine_m(lon, lat, lon, n))
        rows.append({"control_point_id": cp["id"], "before_m": before, "after_m": after, "delta_m": delta,
                     "distance_to_proposed_m": dp,
                     "nearest_before_id": nb, "nearest_before_qa": sl.qa_codes(city, nb) if nb else [],
                     "ties_before_ids": ties_before if len(ties_before) > 1 else [],
                     "nearest_after_id": na, "nearest_after_is_hypothetical": bool(po) and na == po["id"],
                     "distance_to_slice_edge_m": edge,
                     "edge_confound": (before is None) or (edge < before),
                     "label_if_no_records": "В срезе нет исходных записей; улучшение не вычисляется" if before is None else None})
    return {"status": "ok", "source_snapshot_k09": sl.fingerprint(city, cat), "candidates_n": len(cands), "rows": rows}
