"""K12 round 4 REVIEW: runs FIXTURES.json (SYNTHETIC) against one implementation of the K05
data model and records expected vs actual for every case. No network; reads only local files.

Usage:
    python stress_runner.py --impl inputs/k05_d913554 --label current
    python stress_runner.py --impl patched --label patched
The --impl directory must contain round-3-results/K05/k05r3_contract.py (+ schema) and
next-round/K05/k05_validator.py, i.e. the K05 layout without the research/ prefix.
jsonschema is optional: without it the structural layer is reported as "skipped".
"""
import argparse
import copy
import importlib.util
import inspect
import json
import math
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
AS_OF = "2026-10-05"


def decode(x):
    if isinstance(x, dict):
        if set(x) == {"$float"}:
            return float(x["$float"])
        return {k: decode(v) for k, v in x.items()}
    if isinstance(x, list):
        return [decode(v) for v in x]
    return x


def load_impl(impl_dir):
    impl_dir = Path(impl_dir).resolve()
    path = impl_dir / "round-3-results/K05/k05r3_contract.py"
    name = f"k05r3_contract__{abs(hash(str(impl_dir)))}"
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules.pop("k05_validator", None)  # each impl imports its own v1 copy
    spec.loader.exec_module(mod)
    schema = json.loads((impl_dir / "round-3-results/K05/schema/k05-obs-v1.1.schema.json").read_text(encoding="utf-8"))
    try:
        import jsonschema
        validator = jsonschema.Draft202012Validator(schema)
    except ImportError:
        validator = None
    return mod, validator


def apply(base, set_=None, unset=()):
    o = copy.deepcopy(base)
    for k, v in (set_ or {}).items():
        target, *rest = k.split(".")
        if rest:
            o[target] = dict(o[target], **{rest[0]: copy.deepcopy(v)})
        else:
            o[k] = copy.deepcopy(v)
    for k in unset:
        o.pop(k, None)
    return o


def codes(msgs):
    return sorted({m.split(":")[0] for m in msgs})


def safe_json(x):
    """JSON-friendly copy: non-finite floats and huge ints become strings."""
    if isinstance(x, float) and not math.isfinite(x):
        return f"<{x}>"
    if isinstance(x, int) and not isinstance(x, bool) and abs(x) > 2 ** 63:
        return f"<int with {len(str(abs(x)))} digits>"
    if isinstance(x, dict):
        return {k: safe_json(v) for k, v in x.items()}
    if isinstance(x, list):
        return [safe_json(v) for v in x]
    return x


def run_records(C, schema, fx):
    out = []
    for case in fx["record_cases"]:
        obs = apply(fx["bases"][case["base"]], case["set"], case["unset"])
        s_err = None if schema is None else sorted(e.message[:80] for e in schema.iter_errors(obs))
        try:
            errors, warnings = C.validate(obs, as_of=AS_OF)
            crash = None
        except Exception as e:  # a crash is a finding, not a test-runner failure
            errors, warnings, crash = [], [], f"{type(e).__name__}: {e}"
        accepted = crash is None and not errors and not s_err
        got = codes(errors + warnings)
        exp = case["expect"]
        ok = accepted == exp["accept"] and set(exp["codes"]) <= set(got) and crash is None
        out.append({"id": case["id"], "category": case["category"], "new": case["new_vs_k05_tests"],
                    "expect": exp, "schema_errors": s_err, "contract_errors": codes(errors),
                    "contract_warnings": codes(warnings), "crash": crash, "accepted": accepted, "match": ok})
    return out


def run_json_text(C, fx):
    loader = getattr(C, "loads_strict", None)
    out = []
    for case in fx["json_text_cases"]:
        try:
            parsed = loader(case["text"]) if loader else json.loads(case["text"])
            accepted, code = True, []
        except ValueError as e:
            accepted, code, parsed = False, [str(e).split(":")[0]], None
        exp = case["expect"]
        ok = accepted == exp["accept"] and set(exp["codes"]) <= set(code)
        out.append({"id": case["id"], "loader": "loads_strict" if loader else "json.loads (no strict loader)",
                    "expect": exp, "accepted": accepted, "codes": code, "parsed": safe_json(parsed), "match": ok})
    return out


def run_aggregate(C, fx):
    base = fx["bases"][fx["aggregate_base"]]
    has_expected = "expected_units" in inspect.signature(C.aggregate_sum).parameters
    out = []
    for case in fx["aggregate_cases"]:
        recs = [apply(base, r) for r in case["records"]]
        kw = {}
        note = None
        if "expected_units" in case:
            if has_expected:
                kw["expected_units"] = case["expected_units"]
            else:
                note = "aggregate_sum не принимает expected_units: полноту географии проверить нельзя"
        try:
            res, raised = C.aggregate_sum(recs, **kw), None
        except ValueError as e:
            res, raised = None, str(e).split(":")[0]
        exp = case["expect"]
        if "raises" in exp:
            ok = raised == exp["raises"]
        else:
            ok = raised is None and all(
                (isinstance(v, float) and isinstance(res.get(k), float) and math.isnan(v) and math.isnan(res[k]))
                or res.get(k, "<absent>") == v for k, v in exp.items())
        out.append({"id": case["id"], "category": case["category"], "new": case.get("new_vs_k05_tests", False),
                    "expect": exp, "raised": raised, "result": safe_json(res), "note": note, "match": ok})
    return out


def run_datasets(C, fx):
    base = fx["bases"][fx["dataset_base"]]
    fn = getattr(C, "validate_dataset", None)
    out = []
    for case in fx["dataset_cases"]:
        recs = [apply(base, r) for r in case["records"]]
        if fn is None:
            accepted, got, note = True, [], "нет проверки набора: validate() видит записи поодиночке"
        else:
            errors, warnings = fn(recs)
            accepted, got, note = not errors, codes(errors + warnings), None
        exp = case["expect"]
        ok = accepted == exp["accept"] and set(exp["codes"]) <= set(got)
        out.append({"id": case["id"], "category": case["category"], "new": case["new_vs_k05_tests"],
                    "expect": exp, "accepted": accepted, "codes": got, "note": note, "match": ok})
    return out


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--impl", required=True)
    ap.add_argument("--label", required=True)
    ap.add_argument("--fixtures", default=str(HERE / "FIXTURES.json"))
    ap.add_argument("--out", default=None)
    a = ap.parse_args(argv)
    fx = decode(json.loads(Path(a.fixtures).read_text(encoding="utf-8")))
    C, schema = load_impl(a.impl)
    sections = {"record_cases": run_records(C, schema, fx), "json_text_cases": run_json_text(C, fx),
                "aggregate_cases": run_aggregate(C, fx), "dataset_cases": run_datasets(C, fx)}
    summary = {k: {"total": len(v), "match": sum(c["match"] for c in v),
                   "mismatch_ids": [c["id"] for c in v if not c["match"]]} for k, v in sections.items()}
    res = {"label": a.label, "impl": a.impl, "fixtures": fx["fixture_set"], "kind": "synthetic fixtures",
           "as_of": AS_OF, "jsonschema": schema is not None, "summary": summary, **sections}
    out = Path(a.out or HERE / "results" / f"{a.label}.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(res, indent=1, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps({a.label: summary}, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
