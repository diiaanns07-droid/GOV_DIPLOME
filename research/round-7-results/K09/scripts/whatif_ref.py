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
        """Отпечаток K09 (не обязательно совпадает со схемой BUILD): хэши data.js/evidence.js, город, категория,
        кандидаты среза и правила расчёта. Любое изменение данных/QA или правил меняет отпечаток."""
        payload = {"data_js_sha256": self.data_sha256, "evidence_js_sha256": self.evid_sha256,
                   "city": city, "category": category, "bbox": self.bbox(city),
                   "records": [[p["id"], p["lon"], p["lat"]] for p in self.candidates(city, category)],
                   "rules": "haversine/R=6371008.8/clamp[0,1]/no-rounding; ties: smallest id; bbox closed; group field"}
        return "k09ref-sha256:" + hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


ID_RE = re.compile(r"[\w.:-]{1,64}")          # fullmatch; \w включает кириллицу; длина ≤ 64
MAX_IMPORT_BYTES = 256 * 1024
SCEN_KEYS = {"schema_version", "city_id", "source_snapshot", "category", "control_points", "proposed_object"}
EXPORT_EXTRA_KEYS = {"results", "rows", "comparison", "explanation"}   # выводимые значения при импорте игнорируются и пересчитываются
CP_KEYS = {"id", "lon", "lat"}
PO_KEYS = {"id", "lon", "lat", "category", "kind"}


class ImportRejected(ValueError):
    pass


def _no_dup_keys(pairs):
    keys = [k for k, _ in pairs]
    if len(keys) != len(set(keys)):
        raise ImportRejected("duplicate_json_key")
    return dict(pairs)


def _reject_constant(name):
    raise ImportRejected(f"non_finite_literal:{name}")


def _finite_float(text):
    v = float(text)
    if not math.isfinite(v):
        raise ImportRejected("non_finite_number")
    return v


def parse_import(raw):
    """Слой импорта: ≤ 256 KiB, строгий JSON без NaN/Infinity/1e999 и без дублирующихся ключей, корень — объект."""
    b = raw.encode("utf-8") if isinstance(raw, str) else raw
    if len(b) > MAX_IMPORT_BYTES:
        raise ImportRejected("import_too_large")
    try:
        obj = json.loads(b.decode("utf-8"), parse_constant=_reject_constant, parse_float=_finite_float,
                         object_pairs_hook=_no_dup_keys)
    except ImportRejected:
        raise
    except (ValueError, UnicodeDecodeError) as e:
        raise ImportRejected("invalid_json") from e
    if not isinstance(obj, dict):
        raise ImportRejected("root_not_object")
    return obj


def _num(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool) and (not isinstance(v, int) or abs(v) < 1e300) \
        and math.isfinite(float(v))


def validate(sl: Slice, sc, expected_snapshot="k09"):
    """Строгая проверка city-whatif-v1. expected_snapshot: "k09" — сверять с отпечатком K09; строка — с ней; None — не сверять.
    Возвращает список кодов ошибок (пустой = допустимо). Не бросает исключений на неверных типах."""
    if not isinstance(sc, dict):
        return ["scenario_not_object"]
    errs = []
    unknown = set(sc) - SCEN_KEYS - EXPORT_EXTRA_KEYS
    if unknown: errs.append("unknown_fields:" + ",".join(sorted(map(str, unknown))))
    missing = SCEN_KEYS - set(sc)
    if missing: errs.append("missing_fields:" + ",".join(sorted(missing)))
    if sc.get("schema_version") != "city-whatif-v1": errs.append("unknown_schema_version")
    city, cat = sc.get("city_id"), sc.get("category")
    if city not in CITIES: errs.append("unknown_city"); return errs
    if cat not in CATEGORIES: errs.append("unknown_category"); return errs
    if expected_snapshot is not None and "source_snapshot" in sc:
        want = sl.fingerprint(city, cat) if expected_snapshot == "k09" else expected_snapshot
        if sc.get("source_snapshot") != want: errs.append("foreign_or_stale_snapshot")
    cps = sc.get("control_points")
    ids = []
    if not isinstance(cps, list) or not (1 <= len(cps) <= 10):
        errs.append("control_points_count_not_1_10")
        cps = cps if isinstance(cps, list) else []
    for k, cp in enumerate(cps):
        if not isinstance(cp, dict): errs.append(f"control_point_not_object:{k}"); continue
        if set(cp) != CP_KEYS: errs.append(f"control_point_fields:{k}")
        ids.append(cp.get("id"))
        lon, lat = cp.get("lon"), cp.get("lat")
        if not (_num(lon) and _num(lat)): errs.append(f"non_finite_or_non_numeric_coord:{k}"); continue
        if not sl.in_bbox(city, lon, lat): errs.append(f"control_point_outside_bbox:{k}")
    po = sc.get("proposed_object")
    if isinstance(po, list):
        errs.append("more_than_one_proposed")
    elif po is not None:
        if not isinstance(po, dict):
            errs.append("proposed_not_object")
        else:
            if set(po) != PO_KEYS: errs.append("proposed_fields")
            ids.append(po.get("id"))
            if po.get("kind") != "hypothetical": errs.append("proposed_kind_not_hypothetical")
            if po.get("category") != cat: errs.append("proposed_category_mismatch")
            lon, lat = po.get("lon"), po.get("lat")
            if not (_num(lon) and _num(lat)): errs.append("proposed_non_finite_or_non_numeric_coord")
            elif not sl.in_bbox(city, lon, lat): errs.append("proposed_outside_bbox")
            if isinstance(po.get("id"), str) and po["id"] in {p["id"] for p in sl.data["cities"][city]["places"]}:
                errs.append("proposed_id_collides_with_record")
    if any(not isinstance(i, str) or not ID_RE.fullmatch(i) for i in ids): errs.append("bad_id")
    elif len(ids) != len(set(ids)): errs.append("duplicate_id")
    return errs


def _source(sl, city, pid):
    if pid is None: return None
    p = next(x for x in sl.data["cities"][city]["places"] if x["id"] == pid)
    return {"id": pid, "name": p.get("name"), "raw_category": p.get("category"), "confidence": p.get("confidence"),
            "sources": [{"dataset": s.get("dataset"), "record_id": s.get("record_id")} for s in p.get("sources") or []],
            "qa": sl.qa_codes(city, pid)}


STRICT_RAW = {"school": {"elementary_school", "middle_school", "high_school"}, "outpatient_clinic": {"outpatient_care_facility"}}


def compute(sl: Slice, sc, expected_snapshot="k09"):
    """before/after/delta по FEATURE_SPEC; ничьи — стабильно по ID; QA-записи участвуют и помечаются."""
    errs = validate(sl, sc, expected_snapshot)
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
                     "nearest_before_source": _source(sl, city, nb),
                     "nearest_after_source": None if (po and na == po["id"]) else _source(sl, city, na),
                     "ties_before_qa": {pid: sl.qa_codes(city, pid) for pid in ties_before} if len(ties_before) > 1 else {},
                     "diagnostic_before_strict_raw_category_m": min((haversine_m(lon, lat, p["lon"], p["lat"]) for p in cands
                                                                     if p.get("category") in STRICT_RAW[cat]), default=None),
                     "distance_to_slice_edge_m": edge,
                     "edge_confound": (before is None) or (edge < before),
                     "label_if_no_records": "В срезе нет исходных записей; улучшение не вычисляется" if before is None else None})
    return {"status": "ok", "source_snapshot_k09": sl.fingerprint(city, cat), "candidates_n": len(cands), "rows": rows}
