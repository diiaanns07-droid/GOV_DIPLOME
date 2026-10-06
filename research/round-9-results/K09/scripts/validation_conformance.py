#!/usr/bin/env python3
"""Сверка строгой валидации envelope: BUILD validateResilience против оракула K09 на наборе намеренно неверных входов.

  python3 scripts/validation_conformance.py make <invalid.jsonl>
  node adapter/build_resilience_adapter.cjs --web <web> --validate <invalid.jsonl> --out <codes.jsonl>
  python3 scripts/validation_conformance.py compare <invalid.jsonl> <codes.jsonl> <out.json>
Сравнивается решение (принять / отклонить) и смысл кода по карте. Известные различия политики помечаются отдельно.
"""
import copy, json, sys
from pathlib import Path

K = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(K))
from k09res import resilience as RS, t3 as T  # noqa: E402
from k09plan import data, suite  # noqa: E402

REPO = K.parents[2]
CFG = json.loads((K / "config/t3_config.json").read_text(encoding="utf-8"))
# K09 код -> допустимые коды BUILD (смысл совпадает)
CODE_MAP = {"unknown_field": {"unknown_field"}, "missing_field": {"missing_field"}, "bad_version": {"bad_version", "wrong_version"},
            "reserved_case_id": {"reserved_id"}, "duplicate_case_id": {"duplicate_id"}, "duplicate_exclusion": {"duplicate_id"},
            "candidate_not_source": {"candidate_not_source"}, "unknown_source": {"unknown_source"}, "bad_exclusions": {"bad_exclusions"},
            "bad_cases": {"bad_cases"}, "bad_label": {"bad_label"}, "bad_case_shape": {"bad_shape"}, "derived_not_accepted": {"derived_not_allowed"},
            "too_many_candidates": {"too_many_candidates"}, "bad_id": {"bad_id"}, "bad_shape": {"bad_shape"},
            "bad_plan": None}   # None: любой код v2-валидатора BUILD


def base_env(ctx):
    cases = T.exclusion_cases(ctx, CFG, "pair", 3, 0, [])
    return T.make_env(ctx, CFG, "M", 1.0, 3, 0, cases)


def variants(ctx):
    E = lambda: copy.deepcopy(base_env(ctx))
    src = [s["id"] for s in ctx["sources"]]
    V = []
    def add(name, env, note=""):
        V.append({"task_key": name, "city": ctx["city_id"], "envelope": env, "note": note})
    add("valid", E())
    e = E(); e["extra"] = 1; add("unknown_env_field", e)
    e = E(); del e["cases"]; add("missing_cases", e)
    e = E(); e["schema_version"] = "city-resilience-v2"; add("bad_version", e)
    e = E(); e["schema_version"] = "city-plan-v2"; add("v2_file_as_envelope", e)
    e = E(); e["plan"]["derived_results"] = {}; add("plan_derived_results", e)
    e = E(); e["plan"]["candidates"] = e["plan"]["candidates"] + [dict(c, id=c["id"] + "x") for c in e["plan"]["candidates"][:5]]; add("13_candidates", e)
    e = E(); e["cases"] = []; add("zero_cases", e)
    e = E(); e["cases"] = [dict(e["cases"][0], id=f"k{i}") for i in range(8)]; add("eight_cases", e)
    e = E(); e["cases"][0]["id"] = "base"; add("reserved_base", e)
    e = E(); e["cases"][1]["id"] = e["cases"][0]["id"]; add("duplicate_case_id", e)
    e = E(); e["cases"][0]["id"] = "a b"; add("case_id_space", e)
    e = E(); e["cases"][0]["id"] = "Қала-1"; add("case_id_kazakh_ok", e, "Unicode NFC ID допустим")
    e = E(); e["cases"][0]["label"] = ""; add("label_empty", e)
    e = E(); e["cases"][0]["label"] = "x" * 121; add("label_121", e)
    e = E(); e["cases"][0]["label"] = "ж" * 120; add("label_120_ok", e)
    e = E(); e["cases"][0]["label"] = "a\u0007b"; add("label_control", e)
    e = E(); e["cases"][0]["label"] = "   "; add("label_spaces_only", e, "политика: «непустая» — BUILD требует непробельный текст")
    e = E(); e["cases"][0]["label"] = "a b"; add("label_line_separator", e, "политика: U+2028 не Cc; BUILD отклоняет как разделитель строк")
    e = E(); e["cases"][0]["extra"] = 1; add("case_extra_field", e)
    e = E(); e["cases"][0]["disabled_source_ids"] = []; add("exclusions_empty", e)
    e = E(); e["cases"][0]["disabled_source_ids"] = [src[0], src[0]]; add("exclusions_duplicate", e)
    e = E(); e["cases"][0]["disabled_source_ids"] = ["c00"]; add("exclusions_candidate_id", e)
    e = E(); e["cases"][0]["disabled_source_ids"] = ["no-such-record"]; add("exclusions_unknown", e)
    e = E(); e["cases"][0]["disabled_source_ids"] = list(src); add("exclusions_all_ok", e)
    e = E(); e["cases"][0]["disabled_source_ids"] = [1]; add("exclusions_not_string", e)
    e = E(); e["plan"]["control_points"][0]["weight"] = 0; add("plan_bad_weight", e)
    e = E(); e["plan"]["candidates"][0]["kind"] = "source"; add("plan_bad_kind", e)
    e = E(); e["plan"]["max_selected"] = 6; add("plan_bad_max_selected", e)
    e = E(); e["plan"]["required_ids"] = ["c00"]; e["plan"]["excluded_ids"] = ["c00"]; add("plan_required_excluded_overlap", e)
    return V


def main():
    mode = sys.argv[1]
    d, sha = data.load_slice(repo=str(REPO), sha=CFG["data_build_sha"])
    ctxs = {c: suite.make_context(d, sha, c, cat, "real_slice_records") for c, cat in (("shymkent", "school"), ("astana", "outpatient_clinic"))}
    if mode == "make":
        rows = variants(ctxs["astana"]) + [dict(v, task_key="shymkent:" + v["task_key"]) for v in variants(ctxs["shymkent"])]
        Path(sys.argv[2]).write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")
        print(len(rows), "variants"); return
    inv = [json.loads(l) for l in Path(sys.argv[2]).read_text(encoding="utf-8").split("\n") if l]
    bld = {json.loads(l)["task_key"]: json.loads(l)["result"] for l in Path(sys.argv[3]).read_text(encoding="utf-8").split("\n") if l}
    out = []
    for v in inv:
        try:
            RS.validate_resilience(v["envelope"], ctxs[v["city"]]); ours = "accepted"
        except RS.ResError as e:
            ours = e.code
        theirs = bld[v["task_key"]]
        both_reject = ours != "accepted" and theirs != "accepted"
        if not both_reject:
            kind = "agree" if ours == theirs else ("policy_difference" if v.get("note", "").startswith("политика") else "DISAGREE")
        else:
            allowed = CODE_MAP.get(ours)
            kind = "agree" if allowed is None or theirs in allowed else "same_decision_code_name"
        out.append({"variant": v["task_key"], "k09": ours, "build": theirs, "result": kind, "note": v.get("note", "")})
    cnt = {k: sum(1 for r in out if r["result"] == k) for k in ("agree", "same_decision_code_name", "policy_difference", "DISAGREE")}
    rep = {"variants": len(inv), **cnt, "rows": out,
           "legend": "agree — то же решение и код по карте; same_decision_code_name — оба отклоняют, имена кодов разные; policy_difference — заранее помеченное различие политики; DISAGREE — разные решения без объяснения"}
    Path(sys.argv[4]).write_text(json.dumps(rep, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(json.dumps({k: rep[k] for k in ("variants", *cnt)}, ensure_ascii=False))
    for r in out:
        if r["result"] != "agree":
            print(r)


if __name__ == "__main__":
    main()
