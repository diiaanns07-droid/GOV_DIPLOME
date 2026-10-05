"""Reference explanation via the K02 renderer (inputs/k02v4 = K02 r4 fixed + BUILD r5 adaptation, see its MANIFEST).

The browser module web/facts.js re-implements catalog / digest / selector / validate / render in JS;
tests/conformance.cjs checks byte-equal text and equal catalog_digest for every case written here.

Header strings of K02 that mention "ответ движка"/"Сценарий" are overridden at import (data slice, not engine).

Usage: python3 tools/explain_ref.py  -> tests/expected_explanations.json   (stdlib + product agent/evidence.py)
"""
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
APP = HERE.parent
sys.path.insert(0, str(APP / "inputs" / "k02v4"))
sys.path.insert(0, str(HERE))
import verified_explainer as K02  # noqa: E402
import contract as K  # noqa: E402

GROUP_ORDER = ["school", "preschool", "college_university", "hospital", "outpatient_clinic", "pharmacy",
               "government_office"]
K02._TEXT["header"] = {"ru": "Проверяемая часть (значения из каталога фактов среза)",
                       "kk": "Тексерілетін бөлік (мәндер кесінді деректер каталогынан)"}
K02._TEXT["scenario"] = {"ru": "Срез", "kk": "Кесінді"}

FIXED = {  # path -> (ru, kk); no digits allowed (K02 rule)
    "places.selected": ("Выбранные категории в квадрате", "Таңдалған санаттар шаршыда"),
    "district_status.matched": ("С проверенной привязкой к району", "Ауданға сенімді байланған"),
    "district_status.ambiguous": ("С неоднозначным районом", "Ауданы анық емес"),
    "district_status.unmatched": ("В городе, но вне районов", "Қала ішінде, ауданнан тыс"),
    "qa.colocated": ("С совпадающими координатами", "Координаттары бірдей"),
    "qa.category_doubt": ("С сомнением в категории", "Санаты күмәнді"),
    "segments.foot_unknown": ("Дороги без данных о проходе пешком", "Жаяу өту дерегі жоқ жолдар"),
    "city.place_records_total": ("Соцобъекты по всему городу", "Бүкіл қаладағы әлеуметтік нысандар"),
    "registry.official_schools": ("Официальный реестр школ", "Мектептердің ресми тізілімі"),
    "capacity.school_places": ("Мощность школ", "Мектептер сыйымдылығы"),
    "population.children": ("Число детей", "Балалар саны"),
}
CITY_OBS = {"city.place_records_total": "overture_place_records.city_total",
            "registry.official_schools": "official_registry.schools",
            "capacity.school_places": "capacity.school_places", "population.children": "population.children"}


def load_evidence(web=None):
    web = web or APP / "web"

    def js(name):
        t = (web / name).read_text(encoding="utf-8")
        return K.loads_strict(t[t.index("{"):t.rstrip().rindex(";")])
    return js("data.js"), js("evidence.js")


def scenario_id(release, groups):
    mask = sum(1 << i for i, g in enumerate(GROUP_ORDER) if g in groups)
    return f"k10r3-{release}-g{mask}"


def catalog_rows(data, ev, city, groups):
    """Facts of the current city / category filter / slice; values from data.js records and contract observations."""
    c, e = data["cities"][city], ev["cities"][city]
    period = scenario_id(e["release"], groups)
    cid = "kz." + city
    obs = {o["indicator_id"]: o for o in e["observations"]}
    sel = [p for p in c["places"] if p["group"] in groups]
    sel_ids = {p["id"] for p in sel}
    rows = []

    def add(path, value, kind, unit, complete, reason, source, labels=None):
        ru, kk = labels or FIXED[path]
        rows.append({"city": cid, "period": period, "path": path, "value": value, "kind": kind, "unit": unit,
                     "label_ru": ru, "label_kk": kk, "source": source, "coverage_complete": complete,
                     "missing_reason": reason})

    def from_obs(path, o, labels=None):
        add(path, o["value"], o["kind"], o["unit"], o["coverage"]["complete"], o.get("missing_reason"),
            o["obs_id"], labels)

    add("places.selected", len(sel), "derived", "records", True, None, "data.js: записи выбранных категорий")
    for g in GROUP_ORDER:
        if g in groups:
            from_obs(f"places.{g}", obs[f"overture_place_records.{g}.conf_ge_0_0"],
                     (data["groups"][g]["label"] + " в квадрате", ev["group_kk"][g] + ", шаршыда"))
    st = {}
    for p in sel:
        s = e["place_district"][p["id"]]["status"]
        st[s] = st.get(s, 0) + 1
    for s in ("matched", "ambiguous", "unmatched"):
        add(f"district_status.{s}", st.get(s, 0), "derived", "records", True, None, "k03_assign_v2 по записям фильтра")
    coloc = {i for g in e["qa"]["colocated"] for i in g["ids"]}
    add("qa.colocated", len(sel_ids & coloc), "derived", "records", True, None, "K05 check_objects COLOCATED")
    add("qa.category_doubt", len(sel_ids & set(e["qa"]["category_doubt"])), "derived", "records", True, None,
        "правило CATEGORY_DOUBT build_evidence.py")
    from_obs("segments.foot_unknown", obs["segments_foot_access.unknown"])
    for path, ind in CITY_OBS.items():
        from_obs(path, obs[ind])
    return rows


def stub_select(view, digest):
    """Deterministic selector: picks IDs only, writes no numbers. Same rules as facts.js."""
    end = lambda v, *s: any(v["id"].endswith("/" + x) for x in s)  # noqa: E731
    summary = [v["id"] for v in view if v["has_value"] and "/places." in v["id"]][:K02.MAX_FACTS_PER_SECTION]
    risks = [v["id"] for v in view if v["has_value"] and end(
        v, "district_status.ambiguous", "district_status.unmatched", "qa.colocated", "qa.category_doubt",
        "segments.foot_unknown")]
    gaps = [v["id"] for v in view if not v["has_value"]][:K02.MAX_FACTS_PER_SECTION]
    sections = [{"type": "summary", "fact_ids": summary}, {"type": "risks", "fact_ids": risks},
                {"type": "data_gaps", "fact_ids": gaps}]
    return {"sections": [s for s in sections if s["fact_ids"]], "comment": None, "catalog_digest": digest}


def build(data, ev, city, groups):
    catalog = K02.catalog_from_observations(catalog_rows(data, ev, city, groups))
    return catalog, scenario_id(ev["cities"][city]["release"], groups), K02.catalog_digest(catalog)


def explain(data, ev, city, groups, lang="ru"):
    catalog, scen, digest = build(data, ev, city, groups)
    plan = stub_select(K02.catalog_view(catalog), digest)
    accepted = K02.validate_plan(plan, catalog, city="kz." + city, scenario_id=scen)
    out = K02.render(accepted, catalog, lang=lang)
    return {"text": out["text"], "facts_used": [f["id"] for f in out["facts_used"]], "scenario": scen,
            "catalog_digest": digest}


CASES = [
    ("shymkent", GROUP_ORDER, "ru"), ("astana", GROUP_ORDER, "ru"), ("astana", GROUP_ORDER, "kk"),
    ("shymkent", ["school"], "ru"), ("astana", ["preschool", "pharmacy"], "ru"),
    ("shymkent", ["school", "preschool", "college_university", "hospital", "outpatient_clinic", "pharmacy"], "kk"),
    ("shymkent", ["government_office"], "ru"),
]


def main():
    data, ev = load_evidence()
    out = []
    for city, groups, lang in CASES:
        r = explain(data, ev, city, set(groups), lang)
        out.append({"city": city, "groups": groups, "lang": lang, **r})
    path = APP / "tests" / "expected_explanations.json"
    path.write_text(K.dumps_strict({"renderer": "inputs/k02v4/verified_explainer.py (K02 r4 fixed + BUILD r5)",
                                    "cases": out}, indent=1) + "\n", encoding="utf-8", newline="\n")
    print(out[0]["text"])
    print(f"wrote {path.relative_to(APP)} ({len(out)} cases)")


if __name__ == "__main__":
    main()
