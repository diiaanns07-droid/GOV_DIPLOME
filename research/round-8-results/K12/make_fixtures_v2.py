"""K12 round 8, stage 1: negative/positive fixtures for the city-plan-v2 importer (CORE_SPEC.txt @ c3f6c00).

Writes fixtures_v2/*.json (raw import TEXTS), FIXTURES_V2_INDEX.json and oracle_problems.json (clean positive
scenarios for the independent Python oracle). Stdlib only. Fixture texts are never executed; URLs/HTML are inert.

All points, candidates, weights, costs and budgets are SYNTHETIC ("условные единицы"), not tenge, not population.
"__SNAPSHOT__" / "__SNAPSHOT_OTHER_CITY__" are substituted by the test module with the importer's own snapshot().
"""
import copy
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE / "fixtures_v2"
MAX_BYTES = 256 * 1024
BBOX = {"shymkent": [69.593365, 42.306645, 69.617658, 42.324611], "astana": [71.418372, 51.163033, 71.447, 51.181]}


def pt(i, lon, lat, w=1):
    return {"id": f"cp{i}", "lon": lon, "lat": lat, "weight": w}


def cand(i, lon, lat, cost, category="school"):
    return {"id": f"c{i}", "lon": lon, "lat": lat, "category": category, "kind": "hypothetical", "cost": cost}


BASE = {
    "schema_version": "city-plan-v2", "city_id": "shymkent", "source_snapshot": "__SNAPSHOT__", "category": "school",
    "control_points": [pt(1, 69.597, 42.309, 1), pt(2, 69.603, 42.313, 2), pt(3, 69.609, 42.318, 3), pt(4, 69.614, 42.322, 1),
                       pt(5, 69.600, 42.321, 5)],
    "candidates": [cand(1, 69.598, 42.310, 100000), cand(2, 69.604, 42.316, 250000), cand(3, 69.612, 42.320, 300000),
                   cand(4, 69.601, 42.322, 150000), cand(5, 69.596, 42.317, 50000), cand(6, 69.615, 42.309, 400000)],
    "budget": 500000, "max_selected": 3, "coverage_radius_m": 500, "required_ids": [], "excluded_ids": [], "selected_ids": ["c1"],
}


def sc(**over):
    s = copy.deepcopy(BASE)
    s.update(copy.deepcopy(over))
    return s


def grid(city, n, k0=0.001):
    bb = BBOX[city]
    cols = 5
    return [(round(bb[0] + k0 + (i % cols) * (bb[2] - bb[0] - 2 * k0) / (cols - 1), 6),
             round(bb[1] + k0 + (i // cols) * (bb[3] - bb[1] - 2 * k0) / max(1, (n - 1) // cols), 6)) for i in range(n)]


def dumps(o):
    return json.dumps(o, ensure_ascii=False, indent=1)


def with_token(o, path, token):
    o = json.loads(json.dumps(o))
    t = o
    for k in path[:-1]:
        t = t[k]
    t[path[-1]] = "__K12_RAW__"
    text = dumps(o)
    assert text.count('"__K12_RAW__"') == 1
    return text.replace('"__K12_RAW__"', token)


def dup_key(o, path, key, first, second):
    o = json.loads(json.dumps(o))
    t = o
    for k in path:
        t = t[k]
    t.pop(key, None)
    t["__K12_DUP__"] = 0
    text = dumps(o)
    assert text.count('"__K12_DUP__": 0') == 1
    return text.replace('"__K12_DUP__": 0', f'{json.dumps(key)}: {json.dumps(first)}, {json.dumps(key)}: {json.dumps(second)}')


def recipe_text(base_text, r):
    """Large fixtures: rebuilt by the test module from V01 with the same string operations (sha256 checked)."""
    if r["op"] == "pad":
        pad = r["total_bytes"] - len(base_text.encode("utf-8"))
        assert pad >= 0
        return base_text[:-1] + " " * pad + base_text[-1]
    if r["op"] == "insert_derived":
        anchor = '"selected_ids": ['
        assert base_text.count(anchor) == 1
        return base_text.replace(anchor, '"derived_results": {"note": "' + r["char"] * r["count"] + '"},\n ' + anchor, 1)
    if r["op"] == "deep_derived":
        anchor = '"selected_ids": ['
        return base_text.replace(anchor, '"derived_results": ' + "[" * r["depth"] + "]" * r["depth"] + ",\n " + anchor, 1)
    raise ValueError(r)


F = []


def add(fid, slug, text, expect, codes=(), spec="", why="", city="shymkent", recipe=None, obj=None, check=None):
    F.append({"id": fid, "file": f"fixtures_v2/{'generated/' if recipe else ''}{fid}_{slug}.json", "text": text, "expect": expect,
              "expected_codes": list(codes), "spec": spec, "rationale": why, "city": city, "recipe": recipe,
              "oracle": obj is not None, "obj": obj, "check": check or {}})


# ------------------------------------------------------------------ positives (accept; values recomputed)
add("V01", "valid_base", dumps(BASE), "accept", spec="формат входа city-plan-v2", why="5 точек, 6 кандидатов, бюджет 500000 у.е.",
    obj=BASE, check={"optimize": "optimal"})
astana = sc(city_id="astana", category="outpatient_clinic", candidates=[], required_ids=[], excluded_ids=[], selected_ids=[],
            control_points=[pt(1, 71.430, 51.170, 2), pt(2, 71.440, 51.175, 1)], budget=0, max_selected=0)
add("V02", "astana_clinic_no_candidates", dumps(astana), "accept", spec="кандидатов 0..16", city="astana",
    why="только пустой план; оба города", obj=astana, check={"optimize": "optimal"})
poison = sc(derived_results={"objectives": {"mean": {"selected_ids": ["c6"], "metrics": {"weighted_sum_mm": 1}}},
                             "rows": [{"id": "cp1", "after_mm": 0, "delta_mm": 999999999}],
                             "note": "<script>window.__K12_PWNED__=1</script>", "url": "https://example.invalid/x.js"})
add("V03", "poisoned_derived_results", dumps(poison), "accept", spec="derived_results не доверять, пересчитать",
    why="подделанные цели/расстояния, HTML и URL внутри derived_results должны быть проигнорированы", obj=BASE,
    check={"optimize": "optimal", "must_not_contain": [999999999],
           "reject_allowed": "CORE_SPEC: импорт не доверяет derived_results — отказ поддельного файла тоже допустим"})
g_pts, g_c = grid("shymkent", 25), grid("shymkent", 16, 0.002)
maxi = sc(control_points=[pt(i + 1, lon, lat, 100) for i, (lon, lat) in enumerate(g_pts)],
          candidates=[cand(i + 1, lon, lat, 1000 * (i + 1)) for i, (lon, lat) in enumerate(g_c)],
          budget=1000000, max_selected=5, coverage_radius_m=5000, selected_ids=["c1", "c2", "c3", "c4", "c5"])
add("V04", "max_bounds_25x16", dumps(maxi), "accept", spec="точек 25, кандидатов 16, max_selected 5, вес 100, радиус 5000",
    why="верхние границы; худший случай перебора", obj=maxi, check={"optimize": "optimal"})
mini = sc(control_points=[pt(1, 69.60, 42.31, 1)], candidates=[], budget=0, max_selected=0, coverage_radius_m=100, selected_ids=[])
add("V05", "min_bounds", dumps(mini), "accept", spec="нижние границы", why="1 точка, 0 кандидатов, бюджет 0, радиус 100",
    obj=mini, check={"optimize": "optimal"})
top_cost = sc(candidates=BASE["candidates"][:5] + [cand(6, 69.615, 42.309, 1000000)], budget=1000000, selected_ids=["c6"])
add("V06", "cost_and_budget_max", dumps(top_cost), "accept", spec="cost 1..1000000, budget 0..1000000", obj=top_cost,
    check={"optimize": "optimal"})
inf_budget = sc(required_ids=["c6"], budget=300000, selected_ids=["c6"])
add("V07", "infeasible_required_cost", dumps(inf_budget), "accept", spec="required невыполнимы по бюджету → infeasible с причиной",
    why="валиден как сценарий, но точный поиск обязан вернуть infeasible, не убирая ограничения", obj=inf_budget,
    check={"optimize": "infeasible", "reason": "required_cost_exceeds_budget", "reason_pattern": "budget"})
inf_count = sc(required_ids=["c1", "c4", "c5"], max_selected=2, selected_ids=[])
add("V08", "infeasible_required_count", dumps(inf_count), "accept", spec="required невыполнимы по max_selected",
    obj=inf_count, check={"optimize": "infeasible", "reason": "required_count_exceeds_max_selected", "reason_pattern": "max_selected"})
ns = sc(control_points=[dict(p, id=f"c{i + 1}") for i, p in enumerate(BASE["control_points"])])
add("V09", "same_ids_points_candidates", dumps(ns), "accept", spec="ID уникальны внутри каждого массива; source/proposed по namespace",
    why="ID точки равен ID кандидата — разные массивы", obj=ns, check={"optimize": "optimal"})
perm = sc(control_points=list(reversed(BASE["control_points"])), candidates=list(reversed(BASE["candidates"])))
add("V10", "permuted_arrays", dumps(perm), "accept", spec="порядок входных массивов не меняет план и digest", obj=perm,
    check={"optimize": "optimal", "same_as": "V01"})
cons = sc(required_ids=["c5"], excluded_ids=["c2", "c3"], selected_ids=["c5", "c2"])
add("V11", "constraints_and_infeasible_manual", dumps(cons), "accept", spec="required/excluded; ручной план нарушает excluded",
    why="ручной план показывается как недопустимый, а не исправляется молча", obj=cons,
    check={"optimize": "optimal", "manual_feasible": False})
R_V12 = {"op": "pad", "from": "V01", "total_bytes": MAX_BYTES}
add("V12", "exactly_256_KiB", recipe_text(dumps(BASE), R_V12), "accept", spec="strict JSON ≤256 KiB", recipe=R_V12)

# ------------------------------------------------------------------ negatives (reject; state unchanged)
B = BASE
cases = [
    ("N01", "zero_points", sc(control_points=[]), ["bad_count"], "точек 1..25"),
    ("N02", "26_points", sc(control_points=[pt(i + 1, lon, lat) for i, (lon, lat) in enumerate(grid("shymkent", 26))]), ["bad_count"], "точек 1..25"),
    ("N03", "17_candidates", sc(candidates=[cand(i + 1, lon, lat, 1000) for i, (lon, lat) in enumerate(grid("shymkent", 17, 0.002))]), ["bad_count"],
     "кандидатов 0..16; отказ до перебора"),
    ("N04", "max_selected_6", sc(max_selected=6), ["bad_max_selected"], "max_selected 0..5"),
    ("N05", "max_selected_negative", sc(max_selected=-1), ["bad_max_selected"], "max_selected 0..5"),
    ("N06", "max_selected_fraction", sc(max_selected=2.5), ["bad_max_selected"], "целое"),
    ("N07", "max_selected_string", sc(max_selected="3"), ["bad_max_selected"], "целое"),
    ("N08", "max_selected_bool", sc(max_selected=True), ["bad_max_selected"], "целое"),
    ("N09", "weight_0", sc(control_points=[dict(B["control_points"][0], weight=0)] + B["control_points"][1:]), ["bad_weight"], "вес 1..100"),
    ("N10", "weight_101", sc(control_points=[dict(B["control_points"][0], weight=101)] + B["control_points"][1:]), ["bad_weight"], "вес 1..100"),
    ("N11", "weight_fraction", sc(control_points=[dict(B["control_points"][0], weight=1.5)] + B["control_points"][1:]), ["bad_weight"], "целое"),
    ("N12", "weight_negative", sc(control_points=[dict(B["control_points"][0], weight=-1)] + B["control_points"][1:]), ["bad_weight"], "вес 1..100"),
    ("N13", "weight_missing", sc(control_points=[{k: v for k, v in B["control_points"][0].items() if k != "weight"}] + B["control_points"][1:]),
     ["missing_field"], "поля точки"),
    ("N14", "cost_0", sc(candidates=[dict(B["candidates"][0], cost=0)] + B["candidates"][1:]), ["bad_cost"], "cost 1..1000000"),
    ("N15", "cost_1000001", sc(candidates=[dict(B["candidates"][0], cost=1000001)] + B["candidates"][1:]), ["bad_cost"], "cost 1..1000000"),
    ("N16", "cost_fraction", sc(candidates=[dict(B["candidates"][0], cost=2.5)] + B["candidates"][1:]), ["bad_cost"], "целое"),
    ("N17", "cost_negative", sc(candidates=[dict(B["candidates"][0], cost=-5)] + B["candidates"][1:]), ["bad_cost"], "cost 1..1000000"),
    ("N18", "cost_string", sc(candidates=[dict(B["candidates"][0], cost="100000")] + B["candidates"][1:]), ["bad_cost"], "целое"),
    ("N19", "budget_negative", sc(budget=-1), ["bad_budget"], "бюджет 0..1000000"),
    ("N20", "budget_over", sc(budget=1000001), ["bad_budget"], "бюджет 0..1000000"),
    ("N21", "budget_fraction", sc(budget=0.5), ["bad_budget"], "целое"),
    ("N22", "radius_99", sc(coverage_radius_m=99), ["bad_radius"], "радиус 100..5000"),
    ("N23", "radius_5001", sc(coverage_radius_m=5001), ["bad_radius"], "радиус 100..5000"),
    ("N24", "radius_fraction", sc(coverage_radius_m=150.5), ["bad_radius"], "целое"),
    ("N25", "required_unknown_id", sc(required_ids=["c99"]), ["unknown_id"], "ссылки только на существующих кандидатов"),
    ("N26", "excluded_unknown_id", sc(excluded_ids=["cp1"]), ["unknown_id"], "ID точки — не кандидат"),
    ("N27", "selected_unknown_id", sc(selected_ids=["c1", "ghost"]), ["unknown_id"], "ссылки только на существующих кандидатов"),
    ("N28", "required_and_excluded", sc(required_ids=["c2"], excluded_ids=["c2", "c3"]), ["conflicting_constraints"], "required∩excluded"),
    ("N29", "required_duplicate", sc(required_ids=["c2", "c2"]), ["duplicate_id"], "уникальны внутри массива"),
    ("N30", "candidate_duplicate_id", sc(candidates=B["candidates"] + [dict(B["candidates"][0], lon=69.611)]), ["duplicate_id"], "уникальные ID"),
    ("N31", "point_duplicate_id", sc(control_points=B["control_points"] + [dict(B["control_points"][0], lon=69.611)]), ["duplicate_id"], "уникальные ID"),
    ("N32", "id_65_chars", sc(candidates=[dict(B["candidates"][0], id="c" * 65)] + B["candidates"][1:], selected_ids=[]), ["bad_id"], "ID ≤ 64"),
    ("N33", "id_html", sc(control_points=[dict(B["control_points"][0], id="<img src=x onerror=alert(1)>")] + B["control_points"][1:]),
     ["bad_id"], "строки только как текст"),
    ("N34", "candidate_kind_observed", sc(candidates=[dict(B["candidates"][0], kind="observed")] + B["candidates"][1:]), ["bad_kind"], "кандидат hypothetical"),
    ("N35", "candidate_category_mismatch", sc(candidates=[dict(B["candidates"][0], category="outpatient_clinic")] + B["candidates"][1:]),
     ["bad_category"], "одна категория на сценарий"),
    ("N36", "candidate_outside_bbox", sc(candidates=[dict(B["candidates"][0], lon=69.70)] + B["candidates"][1:]), ["outside_bbox"], "исходный bbox"),
    ("N37", "point_outside_bbox", sc(control_points=[dict(B["control_points"][0], lat=42.40)] + B["control_points"][1:]), ["outside_bbox"], "исходный bbox"),
    ("N38", "lat_lon_swapped", sc(control_points=[dict(B["control_points"][0], lon=42.309, lat=69.597)] + B["control_points"][1:]),
     ["outside_bbox", "bad_coord"], "вход [lon, lat]"),
    ("N39", "coordinate_string", sc(candidates=[dict(B["candidates"][0], lon="69.598")] + B["candidates"][1:]), ["bad_coord"], "координаты числа"),
    ("N40", "unknown_field_population", sc(population={"cp1": 5000}), ["unknown_field"], "неожиданные поля, кроме derived_results"),
    ("N41", "unknown_field_in_candidate", sc(candidates=[dict(B["candidates"][0], capacity=800)] + B["candidates"][1:]), ["unknown_field"],
     "нет мощности/вместимости"),
    ("N42", "missing_radius", {k: v for k, v in B.items() if k != "coverage_radius_m"}, ["missing_field"], "обязательные поля"),
    ("N43", "v1_schema_into_v2", sc(schema_version="city-whatif-v1"), ["bad_version"], "v1 и v2 раздельно"),
    ("N44", "foreign_snapshot_city", sc(source_snapshot="__SNAPSHOT_OTHER_CITY__"), ["foreign_snapshot"], "чужой snapshot"),
    ("N45", "snapshot_file_name", sc(source_snapshot="web/data.js"), ["foreign_snapshot"], "имя файла не версия"),
    ("N46", "bad_city", sc(city_id="almaty"), ["bad_city"], "город shymkent|astana"),
    ("N47", "category_hospital", sc(category="hospital", candidates=[]), ["bad_category"], "school/outpatient_clinic"),
    ("N48", "top_level_array", [B], ["bad_shape"], "объект"),
    ("N49", "selected_ids_not_array", sc(selected_ids="c1,c2"), ["bad_shape"], "массив ID"),
]
for fid, slug, obj, codes, spec in cases:
    add(fid, slug, dumps(obj), "reject", codes, spec)
add("N50", "dupkey_budget", dup_key(B, [], "budget", 0, 1000000), "reject", ["duplicate_key"], "запрет дубликатов ключей",
    "второе значение увеличило бы бюджет (last-wins)")
add("N51", "dupkey_cost", dup_key(B, ["candidates", 5], "cost", 400000, 1), "reject", ["duplicate_key"], "запрет дубликатов ключей",
    "стоимость c6 подменилась бы на 1")
add("N52", "dupkey_required", dup_key(B, [], "required_ids", [], ["c6"]), "reject", ["duplicate_key"], "запрет дубликатов ключей")
add("N53", "nan_cost", with_token(B, ["candidates", 0, "cost"], "NaN"), "reject", ["bad_json", "nonfinite_number"], "NaN запрещён")
add("N54", "infinity_weight", with_token(B, ["control_points", 1, "weight"], "Infinity"), "reject", ["bad_json", "nonfinite_number"], "Infinity запрещён")
add("N55", "1e999_budget", with_token(B, ["budget"], "1e999"), "reject", ["nonfinite_number"], "1e999 запрещён", "строгий JSON → Infinity")
add("N56", "neg_infinity_lon", with_token(B, ["candidates", 1, "lon"], "-Infinity"), "reject", ["bad_json", "nonfinite_number"], "Infinity запрещён")
add("N57", "proto_key", dumps(B).replace('{\n "schema_version"', '{\n "__proto__": {"k12_polluted": true},\n "schema_version"', 1),
    "reject", ["unknown_field"], "строгая валидация", "__proto__ не должен менять прототипы")
add("N58", "constructor_key_in_candidate", dumps(B).replace('"id": "c1",', '"id": "c1", "constructor": {"prototype": {"k12_polluted": true}},', 1),
    "reject", ["unknown_field"], "строгая валидация")
add("N59", "truncated", dumps(B)[:-30], "reject", ["bad_json"], "strict JSON")
R_N60 = {"op": "pad", "from": "V01", "total_bytes": MAX_BYTES + 1}
add("N60", "over_256_KiB", recipe_text(dumps(B), R_N60), "reject", ["too_large"], "≤256 KiB", "на 1 байт больше", recipe=R_N60)
R_N61 = {"op": "insert_derived", "from": "V01", "char": "Ж", "count": 140000}
add("N61", "over_256_KiB_multibyte_derived", recipe_text(dumps(B), R_N61), "reject", ["too_large"], "≤256 KiB в байтах",
    "≈140 тыс. символов, >256 KiB UTF-8 внутри разрешённого derived_results", recipe=R_N61)
R_N62 = {"op": "deep_derived", "from": "V01", "depth": 20000}
add("N62", "deep_json_20000", recipe_text(dumps(B), R_N62), "reject", ["too_deep", "bad_json"], "strict JSON",
    "20000 уровней вложенности (40 KB): отказ без переполнения стека и без зависания", recipe=R_N62)
add("N63", "deep_json_33_in_derived", dumps(B).replace('"selected_ids": [', '"derived_results": ' + "[" * 33 + "]" * 33 + ',\n "selected_ids": [', 1),
    "reject", ["too_deep"], "strict JSON", "чуть больше предела 32 эталона; advisory для реализаций с другим пределом")

if __name__ == "__main__":
    (OUT / "generated").mkdir(parents=True, exist_ok=True)
    index, problems = [], []
    for f in F:
        p = HERE / f["file"]
        p.write_bytes(f["text"].encode("utf-8"))
        b = p.read_bytes()
        index.append({k: v for k, v in f.items() if k not in ("text", "obj")} | {"bytes": len(b), "sha256": hashlib.sha256(b).hexdigest()})
        if f["obj"] is not None:
            clean = {k: v for k, v in f["obj"].items() if k != "derived_results"}
            problems.append({"name": f["id"], "scenario": clean})
    doc = {"fixture_set": "k12r8-city-plan-v2-import-stress-v1", "kind": "synthetic",
           "spec": "research/round-8/CORE_SPEC.txt @ codex/research-import-2026-10-05 c3f6c00",
           "notice": "СИНТЕТИКА: точки, кандидаты, веса, стоимости и бюджеты выдуманы (условные единицы, не тенге, не смета, "
                     "не население). Файлы не исполнять, адреса не открывать.",
           "bbox": BBOX, "max_bytes": MAX_BYTES, "placeholders": ["__SNAPSHOT__", "__SNAPSHOT_OTHER_CITY__"],
           "invariant": "после отказа: активный сценарий, вычисления и объяснение те же; входное состояние не изменено; "
                        "нет сети; Object.prototype не изменён; нет новых глобальных переменных",
           "fixtures": index}
    (HERE / "FIXTURES_V2_INDEX.json").write_text(json.dumps(doc, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    (HERE / "oracle_problems.json").write_text(json.dumps({"problems": problems}, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print({"fixtures": len(index), "accept": sum(f["expect"] == "accept" for f in F), "reject": sum(f["expect"] == "reject" for f in F),
           "oracle_problems": len(problems)})
