"""K12 round 9, stage 2: resilience corpus for city-resilience-v1 (research/round-9/CORE_SPEC.txt @ 0ab1667).

    python make_resilience_fixtures.py --app-root <byte-exact copy of prototypes/city-evidence>

Writes fixtures_rs/*.json, FIXTURES_RS_INDEX.json and rs_oracle_problems.json. Source IDs are REAL record IDs of the
slice in <app-root>/web/data.js (its sha256 is stored in the index); everything else is SYNTHETIC (conditional cost
units, user weights; not tenge, not population, not a forecast). "__SNAPSHOT__" / "__SNAPSHOT_OTHER_CITY__" are replaced
by the implementation's own source_snapshot at test time (the r8 K12 convention).
Each negative fixture breaks exactly one rule of a valid envelope; "policy" marks rules CORE_SPEC leaves open
(an implementation that accepts them is ADVISORY, not FAIL).
"""
import argparse
import copy
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE / "fixtures_rs"
SNAP, SNAP_OTHER = "__SNAPSHOT__", "__SNAPSHOT_OTHER_CITY__"
CATS = ("school", "outpatient_clinic")


def load_data(app_root):
    p = Path(app_root) / "web" / "data.js"
    raw = p.read_bytes()
    t = raw.decode("utf-8")
    return json.loads(t[t.index("{"):t.rstrip().rindex(";")]), hashlib.sha256(raw).hexdigest()


def plan(data, city="shymkent", category="school", nc=6, np_=5, budget=500000, max_selected=3):
    bb = data["cities"][city]["bbox"]
    w, h = bb[2] - bb[0], bb[3] - bb[1]
    at = lambda fx, fy: [round(bb[0] + fx * w, 6), round(bb[1] + fy * h, 6)]
    pts = []
    for k in range(np_):
        lon, lat = at(0.1 + 0.8 * ((k * 37) % 100) / 100, 0.1 + 0.8 * ((k * 61) % 100) / 100)
        pts.append({"id": f"cp{k + 1}", "lon": lon, "lat": lat, "weight": [1, 2, 3, 1, 5, 4, 2][k % 7]})
    cands = []
    for k in range(nc):
        lon, lat = at(0.15 + 0.7 * ((k * 53) % 100) / 100, 0.2 + 0.6 * ((k * 29) % 100) / 100)
        cands.append({"id": f"c{k + 1}", "lon": lon, "lat": lat, "category": category, "kind": "hypothetical",
                      "cost": [100000, 250000, 300000, 150000, 50000, 400000, 120000, 80000, 60000, 220000, 90000, 70000,
                               110000, 130000, 140000, 160000, 170000][k]})
    return {"schema_version": "city-plan-v2", "city_id": city, "source_snapshot": SNAP, "category": category,
            "control_points": pts, "candidates": cands, "budget": budget, "max_selected": max_selected,
            "coverage_radius_m": 500, "required_ids": [], "excluded_ids": [], "selected_ids": ["c1"] if nc else []}


def sources(data, city, category):
    return sorted(p["id"] for p in data["cities"][city]["places"] if p["group"] == category)


def env(data, city="shymkent", category="school", ncases=2, **kw):
    p = plan(data, city, category, **kw)
    src = sources(data, city, category)
    cases = [{"id": f"case{k + 1}", "label": f"Случай {k + 1}: условно без записи {k + 1}",
              "disabled_source_ids": [src[k % len(src)]]} for k in range(ncases)]
    return {"schema_version": "city-resilience-v1", "plan": p, "cases": cases}


def dumps(o):
    return json.dumps(o, ensure_ascii=False, indent=1) + "\n"


FIX = []


def add(fid, name, text, expect, rule, spec, *, city="shymkent", check=None, policy=None, obj=None, recipe=None):
    if recipe is None:
        (OUT / f"{fid}_{name}.json").write_bytes(text.encode("utf-8"))
        sha = hashlib.sha256(text.encode("utf-8")).hexdigest()
        entry = {"id": fid, "file": f"fixtures_rs/{fid}_{name}.json", "sha256": sha}
    else:
        entry = {"id": fid, "file": None, "recipe": recipe, "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest()}
    entry.update({"name": name, "expect": expect, "rule": rule, "spec": spec, "city": city, "bytes": len(text.encode("utf-8"))})
    if check:
        entry["check"] = check
    if policy:
        entry["policy"] = policy
    FIX.append(entry)
    if expect == "accept" and obj is not None:
        PROBLEMS.append({"name": fid, "envelope": obj})


PROBLEMS = []


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--app-root", required=True)
    a = ap.parse_args()
    data, data_sha = load_data(a.app_root)
    OUT.mkdir(exist_ok=True)
    for f in OUT.glob("*.json"):
        f.unlink()
    S = lambda c, g: sources(data, c, g)

    # ------------------------------------------------------------------ accepted
    base = env(data)
    add("A01", "base_shymkent_school", dumps(base), "accept", "valid", "2 случая, по одной условно исключённой записи", obj=base)
    a02 = env(data, "astana", "outpatient_clinic", ncases=3)
    add("A02", "astana_clinic", dumps(a02), "accept", "valid", "Астана, поликлиника, 3 случая", city="astana", obj=a02)
    a03 = env(data, ncases=7)
    add("A03", "seven_user_cases", dumps(a03), "accept", "cases_max", "7 пользовательских случаев + base = 8", obj=a03)
    a04 = env(data, nc=12, np_=25, ncases=7, max_selected=5, budget=1000000)
    add("A04", "twelve_candidates_25_points", dumps(a04), "accept", "candidates_max", "12 кандидатов, 25 точек, 7 случаев (4096 наборов)", obj=a04)
    a05 = copy.deepcopy(base)
    a05["cases"].append({"id": "case3", "label": "Повтор случая 1", "disabled_source_ids": list(base["cases"][0]["disabled_source_ids"])})
    add("A05", "duplicate_case_sets", dumps(a05), "accept", "duplicate_sets_allowed",
        "одинаковые наборы допустимы; результат не зависит от дубля", obj=a05, check={"same_plans_as": "A01"})
    a06 = copy.deepcopy(base)
    a06["cases"][1]["disabled_source_ids"] = S("shymkent", "school")
    add("A06", "all_sources_disabled", dumps(a06), "accept", "unknown_baseline",
        "все записи категории исключены: baseline неизвестен, null вместо 0", obj=a06, check={"case_unknown_baseline": "case2"})
    a07 = copy.deepcopy(base)
    a07["cases"][0].update({"id": "жағдай_1", "label": "<b>Мектеп</b> «жабық» деп есептелмейді & <script>alert(1)</script>"})
    add("A07", "unicode_id_html_label", dumps(a07), "accept", "label_text",
        "Unicode NFC id по правилам BUILD; HTML в label — только текст", obj=a07, check={"label_is_text": True})
    a08 = copy.deepcopy(base)
    a08["cases"][0]["label"] = "Ж" * 100 + "😀" * 20          # 120 code points, 140 UTF-16 units
    add("A08", "label_120_codepoints", dumps(a08), "accept", "label_max", "label ровно 120 code points (эмодзи = 1)", obj=a08)
    a09 = copy.deepcopy(base)
    a09["cases"] = list(reversed(a09["cases"]))
    a09["plan"]["control_points"] = list(reversed(a09["plan"]["control_points"]))
    a09["plan"]["candidates"] = list(reversed(a09["plan"]["candidates"]))
    add("A09", "permuted_order", dumps(a09), "accept", "order_independent", "перестановка случаев/точек/кандидатов",
        obj=a09, check={"same_plans_as": "A01"})
    a10 = env(data, nc=0)
    add("A10", "zero_candidates", dumps(a10), "accept", "candidates_min", "0 кандидатов: только ручной/пустой план", obj=a10)
    a11 = env(data)
    a11["plan"]["required_ids"] = ["c6", "c3"]                 # 400000 + 300000 > 500000
    add("A11", "required_infeasible", dumps(a11), "accept", "infeasible_reported",
        "required невыполнимы по бюджету → infeasible с причиной, не снимаются", obj=a11, check={"status": "infeasible"})
    a12 = copy.deepcopy(base)
    a12["cases"][0]["disabled_source_ids"] = S("shymkent", "school")[:1]
    a12["cases"][1]["disabled_source_ids"] = S("shymkent", "school")[1:4]
    add("A12", "multi_exclusion", dumps(a12), "accept", "valid", "случай с 3 исключёнными записями", obj=a12)
    t13 = dumps(base)
    pad = 262144 - len(t13.encode("utf-8"))
    add("A13", "exactly_256KiB", t13[:-2] + " " * pad + t13[-2:], "accept", "size_max", "ровно 262144 байта UTF-8", obj=base,
        recipe={"op": "pad", "from": "A01", "total_bytes": 262144})

    # ------------------------------------------------------------------ rejected: cases
    def neg(fid, name, mutate, rule, spec, policy=None, city="shymkent", src=None):
        o = copy.deepcopy(src or base)
        mutate(o)
        add(fid, name, dumps(o), "reject", rule, spec, policy=policy, city=city)

    neg("N01", "candidate_id_as_source", lambda o: o["cases"][0].update(disabled_source_ids=["c1"]), "unknown_source",
        "ID кандидата вместо source ID (namespace)")
    neg("N02", "fake_source_id", lambda o: o["cases"][0].update(disabled_source_ids=["00000000-0000-0000-0000-000000000000"]),
        "unknown_source", "несуществующий source ID")
    neg("N03", "other_category_source", lambda o: o["cases"][0].update(disabled_source_ids=[S("shymkent", "outpatient_clinic")[0]]),
        "unknown_source", "source ID поликлиники в сценарии школ")
    neg("N04", "other_city_source", lambda o: o["cases"][0].update(disabled_source_ids=[S("astana", "school")[0]]),
        "unknown_source", "source ID Астаны в сценарии Шымкента")
    neg("N05", "reserved_base_id", lambda o: o["cases"][0].update(id="base"), "reserved_id", "id \"base\" зарезервирован")
    neg("N06", "duplicate_case_id", lambda o: o["cases"][1].update(id="case1"), "duplicate_id", "повтор id случая")
    neg("N07", "eight_user_cases", lambda o: o.update(cases=env(data, ncases=8)["cases"]), "too_many_cases", "8 пользовательских + base = 9")
    neg("N08", "zero_cases", lambda o: o.update(cases=[]), "too_few_cases", "нет ни одного пользовательского случая")
    neg("N09", "thirteen_candidates", lambda o: o.update(plan=env(data, nc=13)["plan"]), "too_many_candidates",
        "13 кандидатов: typed too_many_candidates до предвычислений")
    neg("N10", "seventeen_candidates", lambda o: o.update(plan=env(data, nc=17, max_selected=5)["plan"]), "too_many_candidates",
        "17 кандидатов (больше и предела v2)")
    neg("N11", "empty_exclusion", lambda o: o["cases"][0].update(disabled_source_ids=[]), "bad_exclusion", "хотя бы одна запись")
    neg("N12", "duplicate_source_in_case", lambda o: o["cases"][0].update(disabled_source_ids=[S("shymkent", "school")[0]] * 2),
        "duplicate_id", "повтор source ID внутри случая")
    neg("N13", "empty_label", lambda o: o["cases"][0].update(label=""), "bad_label", "label непустой")
    neg("N14", "label_121_codepoints", lambda o: o["cases"][0].update(label="Ж" * 101 + "😀" * 20), "bad_label", "121 code point")
    neg("N15", "label_control_char", lambda o: o["cases"][0].update(label="строка\nвторая"), "bad_label", "управляющий символ \\n")
    neg("N16", "label_bell_char", lambda o: o["cases"][0].update(label="звонок\u0007"), "bad_label", "управляющий символ U+0007")
    neg("N17", "label_number", lambda o: o["cases"][0].update(label=5), "bad_label", "label не строка")
    neg("N18", "case_extra_field", lambda o: o["cases"][0].update(probability=0.5), "unknown_field",
        "лишнее поле случая (вероятность запрещена)")
    neg("N19", "case_missing_label", lambda o: o["cases"][0].pop("label"), "missing_field", "нет label")
    neg("N20", "envelope_derived_results", lambda o: o.update(derived_results={"robust": {"ids": ["c1"]}, "worst": 0}),
        "unknown_field", "r9 envelope не принимает производные поля")
    neg("N21", "plan_derived_results", lambda o: o["plan"].update(derived_results={"note": "x"}), "derived_in_plan",
        "производные поля внутри plan конверта", policy="CORE_SPEC: envelope без производных полей; политика v2 для plan внутри конверта не названа")
    neg("N22", "schema_v2_tag", lambda o: o.update(schema_version="city-resilience-v2"), "bad_version", "неизвестная версия")
    neg("N23", "plan_is_v1", lambda o: o.update(plan={"schema_version": "city-whatif-v1", "city_id": "shymkent", "source_snapshot": SNAP,
                                                     "category": "school", "control_points": [{"id": "cp1", "lon": o["plan"]["control_points"][0]["lon"], "lat": o["plan"]["control_points"][0]["lat"]}],
                                                     "proposed_object": {"id": "p1", "lon": o["plan"]["candidates"][0]["lon"], "lat": o["plan"]["candidates"][0]["lat"], "category": "school", "kind": "hypothetical"}}),
        "bad_plan", "plan в формате city-whatif-v1")
    neg("N24", "foreign_snapshot", lambda o: o["plan"].update(source_snapshot=SNAP_OTHER), "foreign_snapshot", "snapshot другого среза/города")
    neg("N25", "plan_weight_zero", lambda o: o["plan"]["control_points"][0].update(weight=0), "bad_plan", "ошибка внутри plan (вес 0)")
    neg("N26", "plan_cost_string", lambda o: o["plan"]["candidates"][0].update(cost="100000"), "bad_plan", "стоимость строкой")
    neg("N27", "case_id_html", lambda o: o["cases"][0].update(id="<b>x</b>"), "bad_id", "HTML в id")
    neg("N28", "case_id_65", lambda o: o["cases"][0].update(id="k" * 65), "bad_id", "id 65 символов")
    neg("N29", "case_id_not_nfc", lambda o: o["cases"][0].update(id="café"), "bad_id", "id не в NFC")
    neg("N30", "exclusion_not_array", lambda o: o["cases"][0].update(disabled_source_ids=S("shymkent", "school")[0]), "bad_shape",
        "disabled_source_ids строкой")
    neg("N31", "cases_not_array", lambda o: o.update(cases=o["cases"][0]), "bad_shape", "cases объектом")
    neg("N32", "proto_key_in_case", lambda o: o["cases"][0].update({"__proto__": {"polluted": 1}}), "unknown_field", "__proto__ в случае")
    neg("N33", "missing_plan", lambda o: o.pop("plan"), "missing_field", "нет plan")
    neg("N34", "whitespace_label", lambda o: o["cases"][0].update(label="   "), "bad_label", "label из одних пробелов",
        policy="CORE_SPEC: «непустая строка» — пробельная строка формально непустая")
    neg("N35", "bidi_override_label", lambda o: o["cases"][0].update(label="abc‮dcba"), "bad_label",
        "U+202E (формат, не управляющий Cc)", policy="CORE_SPEC запрещает управляющие символы; U+202E — категория Cf")
    neg("N36", "astana_plan_shymkent_sources", lambda o: o["cases"][0].update(disabled_source_ids=[S("shymkent", "outpatient_clinic")[0]]),
        "unknown_source", "Астана: source ID Шымкента", city="astana", src=a02)

    # ------------------------------------------------------------------ rejected: JSON text level
    t = dumps(base)
    add("N40", "duplicate_key_cases", t.replace('"cases": [', '"cases": [], "cases": [', 1), "reject", "bad_json", "повтор ключа cases")
    add("N41", "nan_budget", t.replace('"budget": 500000', '"budget": NaN', 1), "reject", "bad_json", "NaN")
    add("N42", "infinity_weight", t.replace('"weight": 1', '"weight": Infinity', 1), "reject", "bad_json", "Infinity")
    add("N43", "overflow_1e999", t.replace('"budget": 500000', '"budget": 1e999', 1), "reject", "bad_json", "1e999")
    add("N44", "deep_in_exclusion", t.replace('"disabled_source_ids": [', '"disabled_source_ids": [' + "[" * 40 + "]" * 40 + ", ", 1),
        "reject", "bad_json", "вложенность 40 внутри disabled_source_ids (предел глубины)")
    deep = "[" * 20000 + "]" * 20000
    add("N45", "deep_20000", t.replace('"cases": [', '"pad": ' + deep + ', "cases": [', 1), "reject", "bad_json", "вложенность 20000",
        recipe={"op": "deep_field", "from": "A01", "depth": 20000})
    add("N46", "over_256KiB", t[:-2] + " " * (262145 - len(t.encode("utf-8"))) + t[-2:], "reject", "too_large", "262145 байт",
        recipe={"op": "pad", "from": "A01", "total_bytes": 262145})
    add("N47", "truncated", t[: len(t) // 2], "reject", "bad_json", "обрезанный JSON")
    add("N48", "top_level_array", "[" + t.strip() + "]\n", "reject", "bad_shape", "корень — массив")
    add("N49", "lone_surrogate_label", t.replace('"label": "Случай 1', '"label": "\\ud800Случай 1', 1), "reject", "bad_label",
        "одиночный суррогат в label", policy="CORE_SPEC: JSON UTF-8; одиночный суррогат — не символ Unicode")

    for f in FIX:
        if f.get("recipe") is None:
            assert hashlib.sha256((HERE / f["file"]).read_bytes()).hexdigest() == f["sha256"]
    idx = {"fixture_set": "k12r9-city-resilience-v1-corpus-v1", "spec": "research/round-9/CORE_SPEC.txt @ 0ab1667",
           "data_js_sha256": data_sha, "placeholders": [SNAP, SNAP_OTHER],
           "note": "SYNTHETIC plans/costs/weights; source IDs are real record IDs of the slice; not city statistics",
           "fixtures": FIX}
    (HERE / "FIXTURES_RS_INDEX.json").write_text(json.dumps(idx, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    (HERE / "rs_oracle_problems.json").write_text(json.dumps({"data_js_sha256": data_sha, "problems": PROBLEMS}, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print({"fixtures": len(FIX), "accept": sum(f["expect"] == "accept" for f in FIX), "reject": sum(f["expect"] == "reject" for f in FIX),
           "policy": sum("policy" in f for f in FIX), "oracle_problems": len(PROBLEMS)})


if __name__ == "__main__":
    main()
