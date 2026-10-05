"""K09 round-7: 8 задач протокола с вычислимыми ожидаемыми исходами (эталон whatif_ref.py).

Точки задаются детерминированно (доли bbox или смещение от записи по её ID), свойства задач проверяются assert.
Запуск: python3 make_tasks.py   (из папки scripts; нужен git с закреплённым коммитом прототипа)
Пишет ../tasks/whatif_tasks.json и ../results/expected_summary.txt
"""
import json, math, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from whatif_ref import BASE_SHA, Slice, compute, haversine_m

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[3]
sl = Slice.from_git(repo=str(REPO))


def at(city, fx, fy):
    w, s, e, n = sl.bbox(city)
    return round(w + fx * (e - w), 6), round(s + fy * (n - s), 6)


def rec(city, prefix):
    m = [p for p in sl.data["cities"][city]["places"] if p["id"].startswith(prefix)]
    assert len(m) == 1, prefix
    return m[0]


def cp(i, lon, lat):
    return {"id": f"cp{i}", "lon": lon, "lat": lat}


def scen(city, cat, cps, prop=None):
    return {"schema_version": "city-whatif-v1", "city_id": city, "source_snapshot": sl.fingerprint(city, cat),
            "category": cat, "control_points": cps,
            "proposed_object": None if prop is None else {"id": "proj1", "lon": prop[0], "lat": prop[1], "category": cat, "kind": "hypothetical"}}


tasks = []

# W1 — базовый расчёт: хотя бы одна точка улучшается, хотя бы одна нет (поиск по фиксированной сетке)
city, cat = "shymkent", "school"
w1 = None
for fx in (0.2, 0.3, 0.4, 0.6, 0.7, 0.8):
    cps = [cp(1, *at(city, 0.15, 0.85)), cp(2, *at(city, 0.5, 0.5)), cp(3, *at(city, 0.85, 0.15))]
    s = scen(city, cat, cps, at(city, fx, 0.85))
    r = compute(sl, s)
    if any(x["delta_m"] > 0 for x in r["rows"]) and any(x["delta_m"] == 0 for x in r["rows"]):
        w1 = (s, r); break
assert w1, "W1: no grid position gives mixed improvement"
tasks.append({"id": "K09-W1", "title": "Базовый расчёт до/после/разница; одна точка улучшается, другие нет",
              "steps": [w1[0]], "confounds": ["delta — изменение расстояния по прямой, не времени и не доступности"],
              "ui_must_show": ["до/после/разница по каждой точке", "источник ближайшей записи до и после", "метка hypothetical у проекта"]})

# W2 — ничья координат без QA (две школы в одной точке) и честный 0
a, b = rec(city, "baeda67d"), rec(city, "bcd265d0")
assert (a["lon"], a["lat"]) == (b["lon"], b["lat"]) and not sl.qa_codes(city, a["id"]) and not sl.qa_codes(city, b["id"])
s = scen(city, cat, [cp(1, a["lon"], a["lat"])], at(city, 0.5, 0.5))
r = compute(sl, s)
assert r["rows"][0]["before_m"] == 0.0 and r["rows"][0]["nearest_before_id"] == min(a["id"], b["id"]) and r["rows"][0]["delta_m"] == 0.0
tasks.append({"id": "K09-W2", "title": "Контрольная точка совпадает с двумя записями: честный 0 и выбор по ID",
              "steps": [s], "confounds": ["две записи с одинаковыми координатами без QA-флага: возможный дубль, но правило evidence.js его не пометило",
                                          "0 м означает совпадение координат записи, а не «объект рядом с домом»"],
              "ui_must_show": ["0 м без округлительных артефактов", "ближайшая запись — меньший ID при ничьей; длина от ничьей не зависит"]})

# W3 — ближайшая запись имеет CATEGORY_DOUBT («Реклама 42»): QA не удаляется, но показывается
q = rec(city, "01961e84")
assert "CATEGORY_DOUBT" in sl.qa_codes(city, q["id"])
s = scen(city, cat, [cp(1, q["lon"], round(q["lat"] + 0.0003, 6))], at(city, 0.5, 0.5))
r = compute(sl, s)
assert r["rows"][0]["nearest_before_id"] == q["id"]
excl = min(haversine_m(s["control_points"][0]["lon"], s["control_points"][0]["lat"], p["lon"], p["lat"])
           for p in sl.candidates(city, cat) if not sl.qa_codes(city, p["id"]))
tasks.append({"id": "K09-W3", "title": "Ближайшая «школа» помечена CATEGORY_DOUBT",
              "steps": [s], "diagnostic_not_product": {"before_excluding_qa_flagged_m": excl,
                                                       "note": "только для протокола: насколько число зависит от QA; продукт QA-записи не удаляет"},
              "confounds": ["запись может не быть школой (название «Реклама 42»)", "без QA-записи расстояние было бы больше"],
              "ui_must_show": ["название/ID ближайшей записи и QA-флаг CATEGORY_DOUBT", "запись не названа проверенной"]})

# W4 — четыре поликлиники в одной точке (COLOCATED): ничья из 4, 0 м
city, cat = "shymkent", "outpatient_clinic"
grp = [rec(city, x) for x in ("059c59dd", "2264dcf0", "c2990416", "f4d6818b")]
assert len({(g["lon"], g["lat"]) for g in grp}) == 1
s = scen(city, cat, [cp(1, grp[0]["lon"], grp[0]["lat"]), cp(2, *at(city, 0.5, 0.5))], at(city, 0.3, 0.3))
r = compute(sl, s)
assert r["rows"][0]["before_m"] == 0.0 and len(r["rows"][0]["ties_before_ids"]) >= 4 and "COLOCATED" in r["rows"][0]["nearest_before_qa"]
tasks.append({"id": "K09-W4", "title": "Четыре поликлиники в одной координате (COLOCATED)",
              "steps": [s], "confounds": ["совпадающая координата — признак геокодирования «в центр здания/квартала», точное место не проверено"],
              "ui_must_show": ["0 м для cp1 и выбор по наименьшему ID", "QA-флаг COLOCATED у источника"]})

# W5 — проект ровно в контрольной точке (Астана): after = 0, delta = before
city, cat = "astana", "outpatient_clinic"
p = at(city, 0.3, 0.7)
s = scen(city, cat, [cp(1, *p), cp(2, *at(city, 0.8, 0.2))], p)
r = compute(sl, s)
assert r["rows"][0]["after_m"] == 0.0 and r["rows"][0]["delta_m"] == r["rows"][0]["before_m"] and r["rows"][0]["nearest_after_is_hypothetical"]
tasks.append({"id": "K09-W5", "title": "Проект в точке контроля: после = 0, разница = до",
              "steps": [s], "confounds": ["0 м до гипотетического объекта не означает реального учреждения"],
              "ui_must_show": ["после = 0 м, источник — проект (hypothetical)", "вторая точка не изменилась или изменилась по формуле"]})

# W6 — переместить и удалить проект (Астана, школа): три состояния
city, cat = "astana", "school"
cps = [cp(1, *at(city, 0.25, 0.25)), cp(2, *at(city, 0.75, 0.75))]
s1 = scen(city, cat, cps, at(city, 0.25, 0.3)); s2 = scen(city, cat, cps, at(city, 0.75, 0.7)); s3 = scen(city, cat, cps, None)
r1, r2, r3 = compute(sl, s1), compute(sl, s2), compute(sl, s3)
assert all(x["delta_m"] == 0.0 and x["after_m"] == x["before_m"] for x in r3["rows"])
assert [x["before_m"] for x in r1["rows"]] == [x["before_m"] for x in r2["rows"]] == [x["before_m"] for x in r3["rows"]]
tasks.append({"id": "K09-W6", "title": "Поставить → переместить → удалить проект",
              "steps": [s1, s2, s3], "confounds": ["«до» не должно меняться между шагами: та же исходная выборка"],
              "ui_must_show": ["пересчёт после перемещения", "после удаления: после = до, разница = 0"]})

# W7 — граница среза (Астана): ближайшая в срезе может не быть ближайшей в городе
w7 = None
for fx in (0.02, 0.03, 0.05):
    s = scen(city, cat, [cp(1, *at(city, fx, 0.5)), cp(2, *at(city, 0.5, 0.5))], None)
    r = compute(sl, s)
    if r["rows"][0]["edge_confound"]:
        w7 = (s, r); break
assert w7
tasks.append({"id": "K09-W7", "title": "Точка у границы среза: объект вне bbox может быть ближе",
              "steps": [w7[0]], "confounds": ["срез Overture в bbox ≈ несколько км², не весь город", "полнота мест Overture неизвестна (K10: мало объектов)"],
              "ui_must_show": ["ограничение «ближайшая запись в срезе не обязательно ближайшая в городе»", "без проекта: после = до, разница = 0"]})

# W8 — отклонение недопустимых сценариев (без вычислений)
city, cat = "shymkent", "school"
good_cp = [cp(1, *at(city, 0.5, 0.5))]
bad = {
 "proposed_outside_bbox": scen(city, cat, good_cp, (69.70, 42.40)),
 "control_point_outside_bbox": scen(city, cat, [cp(1, 71.43, 51.17)]),          # точка Астаны в сценарии Шымкента
 "eleven_control_points": scen(city, cat, [cp(i, *at(city, 0.05 * i, 0.5)) for i in range(1, 12)]),
 "duplicate_id": scen(city, cat, [cp(1, *at(city, 0.4, 0.4)), cp(1, *at(city, 0.6, 0.6))]),
 "category_mismatch": {**scen(city, cat, good_cp, at(city, 0.5, 0.6)), "proposed_object": {"id": "proj1", "lon": at(city, 0.5, 0.6)[0], "lat": at(city, 0.5, 0.6)[1], "category": "outpatient_clinic", "kind": "hypothetical"}},
 "two_proposed_objects": {**scen(city, cat, good_cp), "proposed_object": [{"id": "p1", "lon": at(city, 0.4, 0.4)[0], "lat": at(city, 0.4, 0.4)[1], "category": cat, "kind": "hypothetical"},
                                                                         {"id": "p2", "lon": at(city, 0.6, 0.6)[0], "lat": at(city, 0.6, 0.6)[1], "category": cat, "kind": "hypothetical"}]},
 "unknown_city": {**scen(city, cat, good_cp), "city_id": "almaty"},
 "unknown_schema_version": {**scen(city, cat, good_cp), "schema_version": "city-whatif-v0"},
}
w8 = {k: {"scenario": v, "expected": compute(sl, v)} for k, v in bad.items()}
assert all(x["expected"]["status"] == "rejected" for x in w8.values())
raw_json_cases = {"nan_literal": '{"lon": NaN}', "infinity_literal": '{"lon": Infinity}', "overflow_1e999": '{"lon": 1e999}',
                  "oversize": "> 262144 байт (256 KiB) — генерировать при тесте"}
tasks.append({"id": "K09-W8", "title": "Недопустимые сценарии отклоняются до расчёта",
              "steps": [], "invalid_cases": w8, "raw_json_import_cases": raw_json_cases,
              "synthetic_unit_case_no_records": {"note": "synthetic: категория без записей в срезе (в реальных данных обе категории есть в обоих городах)",
                                                 "expected": {"before_m": None, "after_m": "distance_to_proposed", "delta_m": None,
                                                              "label": "В срезе нет исходных записей; улучшение не вычисляется"}},
              "confounds": ["строгий JSON-парсер Python принимает NaN/Infinity по умолчанию — импорт должен отклонять явно"],
              "ui_must_show": ["понятное сообщение об отклонении", "активный сценарий не меняется частично"]})

for t in tasks:
    t["expected"] = [compute(sl, s) for s in t.get("steps", [])]
doc = {"generated_by": "research/round-7-results/K09/scripts/make_tasks.py", "prototype_base_sha": BASE_SHA,
       "inputs": {"data.js_sha256": sl.data_sha256, "evidence.js_sha256": sl.evid_sha256},
       "formula": "haversine, R=6371008.8 m, [lon,lat], a clamped to [0,1], no rounding; ties by smallest ID",
       "display_rounding_reference": "app.js fmtM: <1000 м — Math.round(м); ≥1000 — км с 2 знаками и запятой (вывод может отличаться у BUILD)",
       "note": "Ожидаемые числа — эталон K09 по FEATURE_SPEC на данных c58a3b2; функция в прототипе на этом SHA отсутствует.",
       "tasks": tasks}
out = HERE.parent / "tasks/whatif_tasks.json"
out.parent.mkdir(exist_ok=True)
out.write_text(json.dumps(doc, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
lines = []
for t in tasks:
    lines.append(f"{t['id']} — {t['title']}")
    for k, r in enumerate(t["expected"]):
        for x in r["rows"]:
            f = lambda v: "null" if v is None else f"{v:.3f}"
            lines.append(f"   step{k+1} {x['control_point_id']}: before={f(x['before_m'])} after={f(x['after_m'])} delta={f(x['delta_m'])} "
                         f"nb={(x['nearest_before_id'] or '-')[:8]} qa={x['nearest_before_qa']} ties={len(x['ties_before_ids'])} "
                         f"na={(x['nearest_after_id'] or '-')[:8]}{'(hyp)' if x['nearest_after_is_hypothetical'] else ''} edge={x['distance_to_slice_edge_m']:.1f} edge_conf={x['edge_confound']}")
    if t["id"] == "K09-W3":
        lines.append(f"   diagnostic before_excluding_qa_flagged_m={t['diagnostic_not_product']['before_excluding_qa_flagged_m']:.3f}")
    if t["id"] == "K09-W8":
        for k, v in t["invalid_cases"].items():
            lines.append(f"   {k}: {v['expected']['status']} {v['expected'].get('errors')}")
(HERE.parent / "results").mkdir(exist_ok=True)
(HERE.parent / "results/expected_summary.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
print("\n".join(lines))
