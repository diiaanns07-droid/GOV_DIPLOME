"""K02 round 4 REVIEW: атаки на verified_explainer (K02 round 3) и его исправленную копию.

Каждая атака возвращает словарь {attack, outcome, detail}. outcome:
  defect   — найден дефект (молчаливая ошибка, падение с неконтролируемым исключением,
             потеря смысла данных);
  ok       — поведение корректное (контролируемый отказ или правильный вывод).
Атаки не меняют входы. Реальные записи K05 читаются из inputs/k05 (побайтные копии, MANIFEST.json).

Запуск из корня репозитория (нужен numpy, как для движка):
  python research/round-4-results/K02/attack_cases.py [r3|fixed]
"""
from __future__ import annotations

import copy
import importlib.util
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
R3 = ROOT / "research/round-3-results/K02/verified_explainer.py"
FIXED = HERE / "fixed/verified_explainer.py"
K05 = HERE / "inputs/k05"
sys.path.insert(0, str(ROOT))


def load(which: str):
    path = R3 if which == "r3" else FIXED
    spec = importlib.util.spec_from_file_location(f"ve_{which}", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module  # dataclass требует модуль в sys.modules
    spec.loader.exec_module(module)
    return module


def k05_records() -> dict[str, list[dict]]:
    """Все записи k05-obs-v1.1 из кейсов и примеров K05, по имени кейса."""
    def walk(v):
        if isinstance(v, dict):
            if v.get("schema_version") == "k05-obs-v1.1":
                return [v]
            return [o for x in v.values() for o in walk(x)]
        if isinstance(v, list):
            return [o for x in v for o in walk(x)]
        return []
    cases = json.loads((K05 / "cases__cases.json").read_text(encoding="utf-8"))
    out = {name: walk(value) for name, value in cases.items()}
    for city in ("astana", "shymkent"):
        out[f"{city}_sample_rows"] = walk(json.loads(
            (K05 / f"examples__{city}__k10_sample_row_counts.json").read_text(encoding="utf-8")))
        out[f"{city}_official_missing"] = walk(json.loads(
            (K05 / f"examples__{city}__official_registry_missing.json").read_text(encoding="utf-8")))
    return out


def naive_rows(records: list[dict]) -> list[dict]:
    """Прямое отображение k05 → формат catalog_from_observations раунда 3.
    Так поступил бы интегратор, читая докстринг r3. Подписи берутся из данных."""
    return [{"city": r["city_id"], "period": r["period"],
             "path": r["geo_unit_id"].split(".")[-1] + "." + r["indicator_id"],
             "value": r["value"], "kind": r["kind"], "unit": r["unit"],
             "label_ru": r["indicator_id"], "label_kk": r["indicator_id"], "source": r["obs_id"]}
            for r in records]


def catch(fn):
    try:
        return "returned", fn()
    except Exception as exc:  # фиксируем тип исключения: контролируемое ли оно
        return type(exc).__name__, str(exc)[:200]


def run(which: str) -> list[dict]:
    ve = load(which)
    recs = k05_records()
    has_k05 = hasattr(ve, "catalog_from_k05")
    results = []

    def add(attack, outcome, detail):
        results.append({"attack": attack, "outcome": outcome, "detail": detail})

    # A1. Реальные записи K05 через catalog_from_observations.
    real = recs["city_mix"] + recs["real_zero"] + recs["shymkent_official_missing"]
    if has_k05:
        status, value = catch(lambda: ve.catalog_from_k05(real))
        add("A1 real K05 records ingest", "ok" if status == "returned" else "defect",
            f"{status}: {len(value) if status == 'returned' else value}")
    else:
        status, value = catch(lambda: ve.catalog_from_observations(naive_rows(real)))
        add("A1 real K05 records ingest", "defect" if status != "returned" else "ok", f"{status}: {value}")

    # A2. Неполный охват (выборка 15 записей) печатается как обычное значение?
    incomplete = recs["incomplete_sample"]
    if has_k05:
        cat = ve.catalog_from_k05(incomplete)
        fact = next(iter(cat.values()))
        plan = {"sections": [{"type": "summary", "fact_ids": [fact.fact_id]}],
                "catalog_digest": ve.catalog_digest(cat)}
        acc = ve.validate_plan(plan, cat, city=fact.city, scenario_id=fact.scenario_id)
        text = ve.render(acc, cat, lang="ru")["verified_text"]
        add("A2 incomplete coverage marked", "ok" if "неполный охват" in text else "defect", text.splitlines()[-1])
    else:
        rows = naive_rows(incomplete)
        rows[0]["city"], rows[0]["period"] = "astana_real", "p20260923"   # обход грамматики ID
        rows[0]["unit"] = "count"                                         # обход KeyError
        cat = ve.catalog_from_observations(rows)
        fact = next(iter(cat.values()))
        acc = ve.validate_plan({"sections": [{"type": "summary", "fact_ids": [fact.fact_id]}]}, cat,
                               city=fact.city, scenario_id=fact.scenario_id)
        text = ve.render(acc, cat, lang="ru")["verified_text"]
        add("A2 incomplete coverage marked", "defect" if "охват" not in text else "ok",
            "coverage.complete=false потерян: " + text.splitlines()[-1])

    # A3. Неизвестная единица («records», «schools»).
    if has_k05:
        status, value = catch(lambda: ve.catalog_from_k05([dict(recs["incomplete_sample"][0], unit="parsecs")]))
        add("A3 unknown unit", "ok" if status == "ValueError" else "defect", f"{status}: {value}")
    else:
        rows = naive_rows(recs["incomplete_sample"])
        rows[0].update(city="astana_real", period="p20260923")
        cat = ve.catalog_from_observations(rows)
        fact = next(iter(cat.values()))
        acc = ve.validate_plan({"sections": [{"type": "summary", "fact_ids": [fact.fact_id]}]}, cat,
                               city=fact.city, scenario_id=fact.scenario_id)
        status, value = catch(lambda: ve.render(acc, cat, lang="ru"))
        add("A3 unknown unit", "defect" if status == "KeyError" else "ok",
            f"{status} при рендере уже принятого плана: {value}")

    # A4. Два снимка одного показателя (stale_check: одинаковые city/period/geo/indicator).
    pair = recs["stale_check"] + recs["period_mix"][:1]
    if has_k05:
        status, value = catch(lambda: ve.catalog_from_k05(pair))
        add("A4 duplicate fact id across snapshots", "ok" if status == "ValueError" else "defect", f"{status}: {value}")
    else:
        rows = naive_rows(pair)
        for i, r in enumerate(rows):
            r.update(city="astana_real", period="p20260923", unit="count", value=r["value"] + i * 100)
        cat = ve.catalog_from_observations(rows)
        add("A4 duplicate fact id across snapshots", "defect" if len(cat) < len(rows) else "ok",
            f"{len(rows)} записи → {len(cat)} факт; осталось значение {next(iter(cat.values())).value}")

    # A5. Цифры в подписи из данных попадают в «проверяемый» текст.
    label = "Школы: 999"
    if has_k05:
        status, value = catch(lambda: ve.Fact("astana_real/base/x.y", "astana_real", "base", "observed", 5,
                                              "count", {"ru": label, "kk": label}, "test"))
        add("A5 digits in label", "ok" if status == "ValueError" else "defect", f"{status}: {value}")
    else:
        rows = [{"city": "astana_real", "period": "base", "path": "x.y", "value": 5, "kind": "observed",
                 "unit": "count", "label_ru": label, "label_kk": label, "source": "test"}]
        cat = ve.catalog_from_observations(rows)
        acc = ve.validate_plan({"sections": [{"type": "summary", "fact_ids": ["astana_real/base/x.y"]}]}, cat,
                               city="astana_real", scenario_id="base")
        text = ve.render(acc, cat, lang="ru")["verified_text"]
        add("A5 digits in label", "defect" if "999" in text else "ok", text.splitlines()[-1])

    # A6. Учебная модель под чужим городом: explain(result, city="shymkent_real").
    from engine.optimizer import optimize
    from engine.simulation import simulate
    decisions = optimize(top_n=1)["results"][0]["decisions"]
    base = simulate(decisions)
    status, value = catch(lambda: ve.explain(base, lang="ru", city="shymkent_real"))
    add("A6 model result relabelled as real city", "defect" if status == "returned" else "ok",
        f"{status}: " + (value["text"].splitlines()[3] if status == "returned" else value))

    # A7. Устаревший план после смены результата (тот же город и сценарий, другой план).
    other = simulate([decisions[0]] + [d for d in optimize(top_n=3)["results"][2]["decisions"][1:]])
    cat_a, cat_b = ve.build_catalog(base), ve.build_catalog(other)
    plan = ve.StubSelector().select(ve.catalog_view(cat_a))
    status, value = catch(lambda: ve.validate_plan(plan, cat_b, city="astana_hackathon", scenario_id="base"))
    same_ids = set(cat_a) == set(cat_b)
    add("A7 stale plan reused on new result", "defect" if status == "returned" else "ok",
        f"ID совпадают: {same_ids}; Score {base['score']} → {other.get('score')}; {status}")

    # A7b. Смена города: план по учебной Астане против каталога Шымкента.
    shym = (ve.catalog_from_k05(recs["shymkent_sample_rows"]) if has_k05 else None)
    if shym:
        f = next(iter(shym.values()))
        status, value = catch(lambda: ve.validate_plan(plan, shym, city=f.city, scenario_id=f.scenario_id))
        add("A7b stale plan after city switch", "ok" if status == "PlanError" else "defect", f"{status}: {value}")

    # A8. Один ID в двух секциях.
    fid = "astana_hackathon/base/plan.score"
    dup = {"sections": [{"type": "summary", "fact_ids": [fid]}, {"type": "risks", "fact_ids": [fid]}]}
    if has_k05:
        dup["catalog_digest"] = ve.catalog_digest(cat_a)
    status, value = catch(lambda: ve.validate_plan(dup, cat_a, city="astana_hackathon", scenario_id="base"))
    add("A8 same id in two sections", "defect" if status == "returned" else "ok", f"{status}")

    # A9. NaN в ответе движка.
    broken = copy.deepcopy(base)
    broken["score"] = float("nan")
    status, value = catch(lambda: ve.explain(broken, lang="ru"))
    add("A9 NaN in engine result", "ok" if status in ("ValueError",) else "defect", f"{status}: {value if status != 'returned' else value['text'].splitlines()[3]}")

    # A10. Настоящий 0 при полном охвате и пропуск — различимы (K05 real_zero, missing).
    if has_k05:
        cat = ve.catalog_from_k05(recs["real_zero"] + recs["shymkent_official_missing"])
        zero = [f for f in cat.values() if f.value == 0][0]
        miss = [f for f in cat.values() if f.value is None][0]
        ok = zero.kind == "derived" and miss.kind == "unknown" and miss.missing_reason == "source_access_denied"
        add("A10 zero vs missing from K05", "ok" if ok else "defect",
            f"zero={zero.fact_id} kind={zero.kind}; missing kind={miss.kind} reason={miss.missing_reason}")
    else:
        add("A10 zero vs missing from K05", "defect", "нельзя проверить: записи K05 не принимаются (A1); missing_reason не хранится")
    return results


def main():
    which = sys.argv[1] if len(sys.argv) > 1 else "r3"
    results = run(which)
    for r in results:
        print(f"{r['outcome']:7} {r['attack']}: {r['detail']}")
    out = HERE / f"attack_result_{which}.json"
    out.write_text(json.dumps({"target": which, "results": results}, ensure_ascii=False, indent=1) + "\n",
                   encoding="utf-8")


if __name__ == "__main__":
    main()
