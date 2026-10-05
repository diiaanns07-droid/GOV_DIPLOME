"""Independent Python oracle for city-plan-v2 (K01 round 8). Not a translation of planv2.js:
structure is checked by interpreting plan_v2.schema.json with a small JSON-Schema engine, semantics separately.

  python3 planv2_ref.py --app-root APP context CITY                 # print context (bbox, source_snapshot)
  python3 planv2_ref.py --app-root APP validate CITY FILE.json      # exit 0 valid / 1 rejected (JSON with code)
  python3 planv2_ref.py --app-root APP digest CITY FILE.json        # problem_digest + scenario_digest
"""
import hashlib, json, math, re, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCHEMA_DOC = json.loads((HERE / "plan_v2.schema.json").read_text(encoding="utf-8"))
SCHEMA = "city-plan-v2"
METRIC_VERSION = "haversine-mm-v1"
MAX_BYTES = 256 * 1024


class PlanError(ValueError):
    def __init__(self, code, detail=""):
        super().__init__(f"{code}: {detail}")
        self.code = code


# ---------- strict bytes -> object ----------
def _pairs(pairs):
    out = {}
    for k, v in pairs:
        if k in out:
            raise PlanError("duplicate_key", repr(k)[:48])
        out[k] = v
    return out


def _const(tok):
    raise PlanError("non_finite", tok)


def _float(tok):
    v = float(tok)
    if not math.isfinite(v):
        raise PlanError("non_finite", tok[:24])
    return v


def loads_strict(raw):
    if isinstance(raw, str):
        raw = raw.encode("utf-8")
    if len(raw) > MAX_BYTES:
        raise PlanError("too_large", f"{len(raw)} > {MAX_BYTES}")
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        raise PlanError("bad_encoding")
    if text.startswith("﻿"):
        text = text[1:]
    try:
        return json.loads(text, object_pairs_hook=_pairs, parse_constant=_const, parse_float=_float)
    except PlanError:
        raise
    except (ValueError, RecursionError) as e:
        raise PlanError("bad_json", str(e)[:80])


# ---------- tiny JSON-Schema interpreter (subset used by plan_v2.schema.json) ----------
FIELD_CODE = {"schema_version": "bad_version", "city_id": "bad_city", "source_snapshot": "foreign_snapshot",
              "category": "bad_category", "control_points": "bad_points", "candidates": "bad_candidates",
              "budget": "bad_budget", "max_selected": "bad_max_selected", "coverage_radius_m": "bad_radius",
              "required_ids": "bad_shape", "excluded_ids": "bad_shape", "selected_ids": "bad_shape",
              "id": "bad_id", "lon": "bad_coord", "lat": "bad_coord", "weight": "bad_weight", "cost": "bad_cost", "kind": "bad_kind"}


def _is_int(v):
    return not isinstance(v, bool) and (isinstance(v, int) or (isinstance(v, float) and v.is_integer()))


def _type_ok(v, t):
    return {"object": isinstance(v, dict), "array": isinstance(v, list), "string": isinstance(v, str),
            "integer": _is_int(v), "number": not isinstance(v, bool) and isinstance(v, (int, float))}[t]


def _code(path, kw):
    if kw == "additionalProperties":
        return "unknown_field"
    if kw == "required":
        return "missing_field"
    if kw == "uniqueItems":
        return "duplicate_id"
    last = next((p for p in reversed(path) if isinstance(p, str)), None)
    if kw == "type" and path and isinstance(path[-1], int):
        return "bad_shape"      # an array item of the wrong type (control point/candidate is not an object)
    if last in ("required_ids", "excluded_ids", "selected_ids") and isinstance(path[-1], int):
        return "bad_id"
    return FIELD_CODE.get(last, "bad_shape")


def check_schema(v, s, path=()):
    if "$ref" in s:
        s = SCHEMA_DOC["$defs"][s["$ref"].split("/")[-1]]
    if "const" in s and v != s["const"]:
        raise PlanError(_code(path, "const"), "/".join(map(str, path)))
    if "enum" in s and v not in s["enum"]:
        raise PlanError(_code(path, "enum"), "/".join(map(str, path)))
    if "type" in s and not _type_ok(v, s["type"]):
        raise PlanError(_code(path, "type"), "/".join(map(str, path)))
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        if ("minimum" in s and v < s["minimum"]) or ("maximum" in s and v > s["maximum"]):
            raise PlanError(_code(path, "range"), "/".join(map(str, path)))
    if isinstance(v, str) and "pattern" in s and not re.fullmatch(s["pattern"], v):
        raise PlanError(_code(path, "pattern"), "/".join(map(str, path)))
    if isinstance(v, dict):
        props = s.get("properties", {})
        if s.get("additionalProperties") is False:
            for k in v:
                if k not in props:
                    raise PlanError("unknown_field", "/".join(map(str, path + (k,))))
        for k in s.get("required", []):
            if k not in v:
                raise PlanError("missing_field", "/".join(map(str, path + (k,))))
        for k, sub in props.items():
            if k in v:
                check_schema(v[k], sub, path + (k,))
    if isinstance(v, list):
        if ("minItems" in s and len(v) < s["minItems"]) or ("maxItems" in s and len(v) > s["maxItems"]):
            raise PlanError(_code(path, "items"), "/".join(map(str, path)))
        for i, x in enumerate(v):
            check_schema(x, s.get("items", {}), path + (i,))
        if s.get("uniqueItems") and len(set(map(json.dumps, v))) != len(v):
            raise PlanError("duplicate_id", "/".join(map(str, path)))


# ---------- semantics ----------
def validate(obj, ctx):
    if not isinstance(obj, dict):
        raise PlanError("bad_shape", "root")
    check_schema(obj, SCHEMA_DOC)
    if obj["city_id"] != ctx["city_id"]:
        raise PlanError("foreign_city", obj["city_id"])
    if obj["source_snapshot"] != ctx["source_snapshot"]:
        raise PlanError("foreign_snapshot")
    w, s, e, n = ctx["bbox"]
    for arr in ("control_points", "candidates"):
        ids = [x["id"] for x in obj[arr]]
        if len(set(ids)) != len(ids):
            raise PlanError("duplicate_id", arr)
        for x in obj[arr]:
            if not (w <= x["lon"] <= e and s <= x["lat"] <= n):
                raise PlanError("outside_bbox", x["id"])
    for c in obj["candidates"]:
        if c["category"] != obj["category"]:
            raise PlanError("bad_category", c["id"])
    cand = {c["id"] for c in obj["candidates"]}
    for name in ("required_ids", "excluded_ids", "selected_ids"):
        missing = [x for x in obj[name] if x not in cand]
        if missing:
            raise PlanError("unknown_ref", f"{name}: {missing[0]}")
    if set(obj["required_ids"]) & set(obj["excluded_ids"]):
        raise PlanError("constraint_conflict")
    toint = lambda x: int(x) if isinstance(x, float) and x.is_integer() else x
    return {"schema_version": SCHEMA, "city_id": obj["city_id"], "source_snapshot": obj["source_snapshot"], "category": obj["category"],
            "control_points": [{"id": p["id"], "lon": p["lon"], "lat": p["lat"], "weight": int(p["weight"])} for p in obj["control_points"]],
            "candidates": [{"id": c["id"], "lon": c["lon"], "lat": c["lat"], "category": c["category"], "kind": "hypothetical",
                            "cost": int(c["cost"])} for c in obj["candidates"]],
            "budget": int(obj["budget"]), "max_selected": int(obj["max_selected"]), "coverage_radius_m": int(obj["coverage_radius_m"]),
            "required_ids": list(obj["required_ids"]), "excluded_ids": list(obj["excluded_ids"]), "selected_ids": list(obj["selected_ids"]),
            "_ignored_derived": "derived_results" in obj, "_toint": toint and None}


def import_plan(raw, ctx):
    sc = validate(loads_strict(raw), ctx)
    notes = ["derived_results dropped"] if sc.pop("_ignored_derived") else []
    sc.pop("_toint")
    return sc, notes


# ---------- digests (canonical JSON written here independently) ----------
def _canon(v):
    if v is None:
        return "null"
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, int):
        return str(v)
    if isinstance(v, float):
        if v.is_integer() and abs(v) < 1e15:
            return str(int(v))
        r = repr(v)
        if "e" in r:
            raise ValueError("exponent float in canonical form is not supported (coordinates are bbox-bounded)")
        return r
    if isinstance(v, str):
        return json.dumps(v, ensure_ascii=False)
    if isinstance(v, list):
        return "[" + ",".join(_canon(x) for x in v) + "]"
    raise TypeError(type(v))


def problem_canonical(sc):
    pts = sorted(sc["control_points"], key=lambda p: p["id"])
    cands = sorted(sc["candidates"], key=lambda c: c["id"])
    return [SCHEMA, METRIC_VERSION, sc["source_snapshot"], sc["city_id"], sc["category"],
            [[p["id"], p["lon"], p["lat"], p["weight"]] for p in pts],
            [[c["id"], c["lon"], c["lat"], c["category"], c["kind"], c["cost"]] for c in cands],
            sc["budget"], sc["max_selected"], sc["coverage_radius_m"], sorted(sc["required_ids"]), sorted(sc["excluded_ids"])]


def sha(s):
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def problem_digest(sc):
    return "pd1:" + sha(_canon(problem_canonical(sc)))


def scenario_digest(sc):
    return "sd1:" + sha(_canon([problem_canonical(sc), sorted(sc["selected_ids"])]))


# ---------- context from the prototype slice ----------
def load_data(app_root):
    t = (Path(app_root) / "web" / "data.js").read_text(encoding="utf-8")
    return json.loads(t[t.index("{"):t.rstrip().rindex(";")])


def _r7(x):
    return math.floor(x * 1e7 + 0.5) / 1e7   # = JS Math.round(x*1e7)/1e7 for these positive coordinates


def places_digest(data, city):
    rows = sorted(([p["id"], _r7(p["lon"]), _r7(p["lat"])] for p in data["cities"][city]["places"]), key=lambda r: r[0])
    return sha(json.dumps(rows, separators=(",", ":"), ensure_ascii=False))


def context(data, city):
    c = data["cities"][city]
    fsha = (c.get("files") or {}).get("places_social", {}).get("sha256")
    snap = "sha256:" + sha(json.dumps([SCHEMA, city, c["release"], fsha, places_digest(data, city), METRIC_VERSION],
                                      separators=(",", ":"), ensure_ascii=False))
    return {"city_id": city, "bbox": list(c["bbox"]), "source_snapshot": snap, "release": c["release"]}


def batch(fx_dir):
    """Verdicts + digests for every fixture in EXPECTED.json, using the committed real contexts (no app needed)."""
    fx = Path(fx_dir)
    exp = json.loads((fx / "EXPECTED.json").read_text(encoding="utf-8"))["fixtures"]
    ctxs = {c: json.loads((fx / "real" / f"context_{c}.json").read_text(encoding="utf-8")) for c in ("shymkent", "astana")}
    out = {}
    for name, e in exp.items():
        try:
            sc, notes = import_plan((fx / "synthetic" / name).read_bytes(), ctxs[e["context_city"]])
            out[name] = {"valid": True, "notes": len(notes), "problem_digest": problem_digest(sc), "scenario_digest": scenario_digest(sc)}
        except PlanError as err:
            out[name] = {"valid": False, "code": err.code}
    return out


def main(argv):
    if argv[:1] == ["batch"]:
        print(json.dumps(batch(argv[1] if len(argv) > 1 else HERE / "fixtures"), indent=1)); return 0
    if len(argv) < 4 or argv[0] != "--app-root":
        print(__doc__); return 2
    data = load_data(argv[1])
    cmd, city = argv[2], argv[3]
    ctx = context(data, city)
    if cmd == "context":
        print(json.dumps(ctx, indent=1)); return 0
    raw = Path(argv[4]).read_bytes()
    try:
        sc, notes = import_plan(raw, ctx)
    except PlanError as e:
        print(json.dumps({"valid": False, "code": e.code, "detail": str(e)}, ensure_ascii=False)); return 1
    out = {"valid": True, "notes": notes}
    if cmd == "digest":
        out.update(problem_digest=problem_digest(sc), scenario_digest=scenario_digest(sc))
    print(json.dumps(out, ensure_ascii=False)); return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
