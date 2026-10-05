"""Reference explanation via the unmodified K02 renderer (verified_explainer.py, K02 @ 24c1750).

The browser module web/facts.js re-implements the same catalog/selector/validate/render steps in JS;
tests/conformance.cjs checks that its text equals the text produced here for every case below.

Adapter-only changes (no edits to K02 code): two header strings of K02 mention "ответ движка"/"Сценарий",
which is wrong for a data slice; they are overridden in K02's _TEXT dict at import time.

Usage: python3 tools/explain_ref.py  -> tests/expected_explanations.json   (stdlib + product agent/evidence.py)
"""
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
APP = HERE.parent
sys.path.insert(0, str(APP.parents[1]))  # repository root: K02 imports agent.evidence.format_value (read-only)
sys.path.insert(0, str(APP / "inputs" / "k02"))
import verified_explainer as K02  # noqa: E402

GROUP_ORDER = ["school", "preschool", "college_university", "hospital", "outpatient_clinic", "pharmacy",
               "government_office"]
K02._TEXT["header"] = {"ru": "Проверяемая часть (значения из каталога фактов среза)",
                       "kk": "Тексерілетін бөлік (мәндер кесінді деректер каталогынан)"}
K02._TEXT["scenario"] = {"ru": "Срез", "kk": "Кесінді"}

STUB_NAME = "шаблонное объяснение (детерминированная заглушка, не LLM)"


def load_evidence():
    def js(name):
        t = (APP / "web" / name).read_text(encoding="utf-8")
        return json.loads(t[t.index("{"):t.rstrip().rindex(";")])
    return js("data.js"), js("evidence.js")


def scenario_id(slice_id, groups):
    mask = sum(1 << i for i, g in enumerate(GROUP_ORDER) if g in groups)
    return f"{slice_id}_g{mask}"


def labels(path, data, ev):
    if path.startswith("places.") and path.split(".", 1)[1] in data["groups"]:
        g = path.split(".", 1)[1]
        return data["groups"][g]["label"] + ": записей в квадрате", ev["group_kk"][g] + ": шаршыдағы жазбалар"
    return {
        "places.selected": ("Записей выбранных категорий в квадрате", "Таңдалған санаттар жазбалары шаршыда"),
        "district_status.matched": ("Записей с проверенной привязкой к району", "Ауданға сенімді байланған жазбалар"),
        "district_status.ambiguous": ("Записей с неоднозначным районом", "Ауданы анық емес жазбалар"),
        "district_status.unmatched": ("Записей внутри города вне районов", "Қала ішінде, ауданнан тыс жазбалар"),
        "segments.foot_unknown": ("Сегментов дорог без данных о проходе пешком", "Жаяу өту дерегі жоқ жол сегменттері"),
        "capacity.school_places": ("Мощность школ (места)", "Мектептер сыйымдылығы (орын)"),
        "registry.official_schools": ("Официальный реестр школ", "Мектептердің ресми тізілімі"),
        "population.children": ("Число детей", "Балалар саны"),
    }[path]


def catalog_rows(data, ev, city, groups):
    """Facts of the current city/filter/slice. Values come from data.js records and K05 observations."""
    c, e = data["cities"][city], ev["cities"][city]
    period = scenario_id(ev["slice_id"], groups)
    obs = {o["indicator_id"]: o for o in e["observations"]}
    sel = [p for p in c["places"] if p["group"] in groups]
    rows = []

    def add(path, value, kind, source):
        ru, kk = labels(path, data, ev)
        rows.append({"city": city, "period": period, "path": path, "value": value, "kind": kind, "unit": "count",
                     "label_ru": ru, "label_kk": kk, "source": source})
    add("places.selected", len(sel), "derived", "data.js: число записей выбранных категорий")
    for g in GROUP_ORDER:
        if g in groups:
            o = obs[f"places.{g}"]
            add(f"places.{g}", o["value"], o["kind"], "k05:" + o["obs_id"])
    st = {}
    for p in sel:
        s = e["place_district"][p["id"]]["status"]
        st[s] = st.get(s, 0) + 1
    for s in ("matched", "ambiguous", "unmatched"):
        add(f"district_status.{s}", st.get(s, 0), "derived", "K03 k03_assign_v1 по записям фильтра")
    o = obs["segments.foot_unknown"]
    add("segments.foot_unknown", o["value"], o["kind"], "k05:" + o["obs_id"])
    for ind in ("capacity.school_places", "registry.official_schools", "population.children"):
        o = obs[ind]
        add(ind, o["value"], o["kind"], "k05:" + o["obs_id"])
    return rows


def stub_select(view):
    """Deterministic selector: picks IDs only, writes no numbers. Same order rules as facts.js."""
    def ids(pred):
        return [v["id"] for v in view if pred(v)]
    end = lambda v, *s: any(v["id"].endswith("/" + x) for x in s)  # noqa: E731
    summary = ids(lambda v: v["has_value"] and "/places." in v["id"])[:K02.MAX_FACTS_PER_SECTION]
    risks = ids(lambda v: v["has_value"] and end(v, "district_status.ambiguous", "district_status.unmatched",
                                                  "segments.foot_unknown"))
    gaps = ids(lambda v: not v["has_value"])[:K02.MAX_FACTS_PER_SECTION]
    sections = [{"type": "summary", "fact_ids": summary}, {"type": "risks", "fact_ids": risks},
                {"type": "data_gaps", "fact_ids": gaps}]
    return {"sections": [s for s in sections if s["fact_ids"]], "comment": None}


def explain(data, ev, city, groups, lang="ru"):
    catalog = K02.catalog_from_observations(catalog_rows(data, ev, city, groups))
    scen = scenario_id(ev["slice_id"], groups)
    plan = stub_select(K02.catalog_view(catalog))
    accepted = K02.validate_plan(plan, catalog, city=city, scenario_id=scen)
    out = K02.render(accepted, catalog, lang=lang)
    return {"text": out["text"], "facts_used": [f["id"] for f in out["facts_used"]], "scenario": scen}


CASES = [
    ("shymkent", GROUP_ORDER, "ru"), ("astana", GROUP_ORDER, "ru"), ("astana", GROUP_ORDER, "kk"),
    ("shymkent", ["school"], "ru"), ("astana", ["preschool", "pharmacy"], "ru"),
    ("shymkent", ["school", "preschool", "college_university", "hospital", "outpatient_clinic", "pharmacy"], "kk"),
]


def main():
    data, ev = load_evidence()
    out = []
    for city, groups, lang in CASES:
        r = explain(data, ev, city, set(groups), lang)
        out.append({"city": city, "groups": groups, "lang": lang, **r})
    path = APP / "tests" / "expected_explanations.json"
    path.write_text(json.dumps({"renderer": "K02 verified_explainer.render @24c1750", "cases": out},
                               ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(out[0]["text"])
    print(f"wrote {path.relative_to(APP)} ({len(out)} cases)")


if __name__ == "__main__":
    main()
