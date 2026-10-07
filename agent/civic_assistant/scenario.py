"""Факты сценарного сравнения из результата движка R07 (civic-scenario-result-v1).

Объяснение A/B строится только по метрикам engine: число пар с найденным путём,
изменения длины по сопоставимым парам, потеря пути в модели. Никакого «лучшего
плана» или «лучшего города», времени в пути, пробок и CO2: движок их не считает.
Формат проверен на выводе engine.civic_scenarios.compare (ветка R07
claude/brave-hopper-bkc58b, SHA 18f8ac8, синтетический кейс synthetic-tiny-v1-demo).
"""

from __future__ import annotations

from datetime import datetime
import math
import re

from agent.civic_assistant.facts import EVIDENCE_TYPES, ID_RE, ContextError, clean_text
from agent.civic_assistant.render import NO_DATA, _st, fmt_money

RESULT_SCHEMA = "civic-scenario-result-v1"
PLAN_IDS = ("A", "B")
STATUS_KEYS = ("pairs", "ok", "unknown", "unreachable")
CHANGE_KEYS = ("comparable_pairs", "unchanged", "longer", "shorter", "lost_within_model", "became_uncertain",
               "gained", "not_comparable", "mean_delta_m", "max_delta_m")

S = {
    "ru": {
        "graph_synthetic": "Граф сценария синтетический (условный), это не улицы Астаны.",
        "graph_hypothesis": "Граф сценария имеет статус гипотезы.",
        "graph_derived": "Граф сценария выведен из других данных; доступ части участков может быть неизвестен.",
        "graph_unknown": "Тип доказательности графа сценария не указан.",
        "hypothesis": "Перекрытие в сценарии — гипотеза для сравнения; это не решение городских органов о перекрытии.",
        "run": "Расчёт движка: режим «{mode}», момент анализа {at}.",
        "coverage": "Доля длины сети с известным режимом доступа: {share} %.",
        "baseline": "Без перекрытий пар с найденным путём: {ok} из {pairs}; без подтверждённого пути — {unknown}; "
                    "нет пути в модели — {unreachable}.",
        "plan_status": "План {p}: пар с найденным путём — {ok} из {pairs}; без подтверждённого пути — {unknown}; "
                       "нет пути в модели — {unreachable}.",
        "plan_vs_base": "План {p} относительно состояния без перекрытий: длиннее — {longer}, короче — {shorter}, "
                        "без изменений — {unchanged}, путь потерян в модели — {lost}, путь стал неподтверждённым — "
                        "{uncertain}.",
        "plan_mean": "План {p}: среднее изменение длины (сопоставимых пар: {n}) — {delta}.",
        "plan_no_active": "План {p}: в момент анализа ни одно перекрытие плана не действует.",
        "ab_status": "Пар с найденным путём: план A — {a}, план B — {b} (всего пар: {pairs}).",
        "ab_changes": "При переходе от плана A к плану B: длиннее — {longer}, короче — {shorter}, без изменений — "
                      "{unchanged}, путь потерян в модели — {lost}, путь появился — {gained}.",
        "ab_mean": "Среднее изменение длины от A к B (сопоставимых пар: {n}) — {delta}.",
        "ab_none": "Сравнение A и B движок не вернул — нет данных.",
        "delta_longer": "длиннее на {v} м",
        "delta_shorter": "короче на {v} м",
        "delta_zero": "без изменения",
        "delta_none": "нет данных (нет сопоставимых пар)",
        "metric_note": "Метрика — длина пути по сети в метрах, не время в пути; пробки, выбросы и безопасность "
                       "движок не моделирует.",
        "unreachable_note": "«Нет пути в модели» — свойство графа, а не доказанная потеря доступа на местности.",
        "mode": {"walking": "пешком", "driving": "на автомобиле"},
    },
    "kk": {
        "graph_synthetic": "Сценарий графы синтетикалық (шартты), бұл Астана көшелері емес.",
        "graph_hypothesis": "Сценарий графы болжам мәртебесінде.",
        "graph_derived": "Сценарий графы басқа деректерден шығарылған; кейбір учаскелердің қолжетімділігі белгісіз болуы мүмкін.",
        "graph_unknown": "Сценарий графының дәлелдік түрі көрсетілмеген.",
        "hypothesis": "Сценарийдегі жабылу — салыстыруға арналған болжам; бұл қала органдарының жабылу туралы шешімі емес.",
        "run": "Қозғалтқыш есебі: режим «{mode}», талдау сәті {at}.",
        "coverage": "Қолжетімділік режимі белгілі желі ұзындығының үлесі: {share} %.",
        "baseline": "Жабылусыз {pairs} жұптың {ok} жұбына жол табылды; расталған жолы жоқ — {unknown}; "
                    "модельде жол жоқ — {unreachable}.",
        "plan_status": "{p} жоспары: {pairs} жұптың {ok} жұбына жол табылды; расталған жолы жоқ — {unknown}; "
                       "модельде жол жоқ — {unreachable}.",
        "plan_vs_base": "{p} жоспары жабылусыз күймен салыстырғанда: ұзарды — {longer}, қысқарды — {shorter}, "
                        "өзгеріссіз — {unchanged}, модельде жол жоғалды — {lost}, жол расталмаған болды — {uncertain}.",
        "plan_mean": "{p} жоспары: ұзындықтың орташа өзгерісі (салыстырмалы жұптар: {n}) — {delta}.",
        "plan_no_active": "{p} жоспары: талдау сәтінде жоспардың бірде-бір жабылуы әрекет етпейді.",
        "ab_status": "Жол табылған жұптар: A жоспары — {a}, B жоспары — {b} (барлық жұптар: {pairs}).",
        "ab_changes": "A жоспарынан B жоспарына өткенде: ұзарды — {longer}, қысқарды — {shorter}, өзгеріссіз — "
                      "{unchanged}, модельде жол жоғалды — {lost}, жол пайда болды — {gained}.",
        "ab_mean": "A-дан B-ға ұзындықтың орташа өзгерісі (салыстырмалы жұптар: {n}) — {delta}.",
        "ab_none": "Қозғалтқыш A мен B салыстыруын қайтармады — деректер жоқ.",
        "delta_longer": "{v} м ұзарды",
        "delta_shorter": "{v} м қысқарды",
        "delta_zero": "өзгеріссіз",
        "delta_none": "деректер жоқ (салыстырмалы жұп жоқ)",
        "metric_note": "Көрсеткіш — желі бойынша жол ұзындығы (метр), жол уақыты емес; кептеліс, шығарындылар және "
                       "қауіпсіздік модельденбейді.",
        "unreachable_note": "«Модельде жол жоқ» — граф қасиеті, жергілікті жерде қолжетімділіктің жоғалғаны дәлелденбеген.",
        "mode": {"walking": "жаяу", "driving": "көлікпен"},
    },
}


def _num(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        return None
    return value


def _count(value):
    v = _num(value)
    return int(v) if v is not None and v >= 0 and float(v).is_integer() else None


def _fact(fid, label, value, kind="count", display=None):
    fact = {"id": fid, "label_key": label, "value": value, "known": value is not None, "kind": kind,
            "origin": "scenario", "source_ids": []}
    if display:
        fact["meta"] = {"display": display}
    return fact


def _fmt_at(value: str | None) -> str | None:
    if not isinstance(value, str):
        return None
    try:
        dt = datetime.fromisoformat(value)
    except ValueError:
        return None
    off = dt.strftime("%z")
    off = f"UTC{off[:3]}:{off[3:]}" if off else "UTC"
    return f"{dt.day:02d}.{dt.month:02d}.{dt.year:04d} {dt.hour:02d}:{dt.minute:02d} ({off})"


def _status_facts(prefix, summary):
    summary = summary if isinstance(summary, dict) else {}
    by = summary.get("by_status") if isinstance(summary.get("by_status"), dict) else {}
    values = {"pairs": _count(summary.get("pairs")), "ok": _count(by.get("ok")),
              "unknown": _count(by.get("unknown")), "unreachable": _count(by.get("unreachable"))}
    return [_fact(f"{prefix}.{k}", "pairs_" + k, values[k]) for k in STATUS_KEYS]


def _change_facts(prefix, summary):
    summary = summary if isinstance(summary, dict) else {}
    changes = summary.get("changes") if isinstance(summary.get("changes"), dict) else {}
    out = [_fact(f"{prefix}.comparable_pairs", "comparable_pairs", _count(summary.get("comparable_pairs")))]
    for k in ("unchanged", "longer", "shorter", "lost_within_model", "became_uncertain", "gained", "not_comparable"):
        out.append(_fact(f"{prefix}.{k}", "pairs_" + k, _count(changes.get(k))))
    for k, src in (("mean_delta_m", "mean_delta_m_comparable"), ("max_delta_m", "max_delta_m_comparable")):
        out.append(_fact(f"{prefix}.{k}", k, _num(summary.get(src)), kind="metric_m"))
    return out


def scenario_facts(result, scenario_id=None) -> tuple[list[dict], list[str]]:
    """Нормализация результата compare() R07 в каталог фактов. Неизвестное -> known=False."""
    warnings: list[str] = []
    if not isinstance(result, dict) or result.get("schema_version") != RESULT_SCHEMA:
        raise ContextError("scenario_schema", "ожидается " + RESULT_SCHEMA)
    inp = result.get("input") if isinstance(result.get("input"), dict) else {}
    if inp.get("city") != "astana":
        raise ContextError("scenario_city", "раунд 11 — только Астана")
    if scenario_id is not None and (not isinstance(scenario_id, str) or not ID_RE.match(scenario_id)):
        raise ContextError("scenario_id")
    ev = inp.get("graph_evidence_type") if inp.get("graph_evidence_type") in EVIDENCE_TYPES else None
    mode = inp.get("mode") if inp.get("mode") in ("walking", "driving") else None
    at = clean_text(inp.get("analysis_at"), 40)
    cov = result.get("graph_coverage") if isinstance(result.get("graph_coverage"), dict) else {}
    share = _num(cov.get("known_access_share_by_length"))
    share = share if share is not None and 0 <= share <= 1 else None
    share_pct = None if share is None else fmt_money(round(share * 100, 1))
    engine = result.get("engine") if isinstance(result.get("engine"), dict) else {}
    facts = [
        _fact("scenario.graph_evidence_type", "graph_evidence_type", ev, "enum"),
        _fact("scenario.mode", "mode", mode, "enum"),
        _fact("scenario.analysis_at", "analysis_at", at, "timestamp", display=[_fmt_at(at)] if _fmt_at(at) else None),
        _fact("scenario.known_access_share", "known_access_share", share, "share",
              display=[share_pct] if share_pct else None),
        _fact("scenario.engine", "engine", {"name": clean_text(engine.get("name"), 80),
                                            "version": clean_text(engine.get("version"), 20),
                                            "result_digest": clean_text(result.get("result_digest"), 80),
                                            "graph_id": clean_text(inp.get("graph_id"), 120)}, "engine"),
    ]
    facts += _status_facts("scenario.baseline", (result.get("baseline") or {}).get("status_summary")
                           if isinstance(result.get("baseline"), dict) else None)
    plans = result.get("plans") if isinstance(result.get("plans"), list) else []
    seen = set()
    for p in plans:
        if not isinstance(p, dict) or p.get("id") not in PLAN_IDS or p["id"] in seen:
            warnings.append("scenario_plan_skipped")
            continue
        pid = p["id"]
        seen.add(pid)
        facts += _status_facts(f"scenario.{pid}", p.get("status_summary"))
        vs = p.get("vs_baseline") if isinstance(p.get("vs_baseline"), dict) else {}
        facts += _change_facts(f"scenario.{pid}.vs_baseline", vs.get("summary"))
        active = p.get("active_closed_edge_ids")
        facts.append(_fact(f"scenario.{pid}.active_closures", "active_closed_edges",
                           len(active) if isinstance(active, list) else None))
    ab = result.get("a_vs_b") if isinstance(result.get("a_vs_b"), dict) else None
    if ab and ab.get("from_plan") == "A" and ab.get("to_plan") == "B":
        facts += _change_facts("scenario.AB", ab.get("summary"))
    if any(f["value"] is None for f in facts if f["kind"] == "count"):
        warnings.append("scenario_metric_missing")
    return facts, warnings


def _v(facts, fid):
    f = facts.get(fid)
    return f["value"] if f and f["known"] else None


def _n(value, lang):
    return NO_DATA[lang] if value is None else str(value)


def _delta(value, lang):
    s = S[lang]
    if value is None:
        return s["delta_none"]
    if value > 0:
        return s["delta_longer"].format(v=fmt_money(value))
    if value < 0:
        return s["delta_shorter"].format(v=fmt_money(-value))
    return s["delta_zero"]


def _status_line(facts, lang, prefix, key, plan=None):
    ids = [f"{prefix}.{k}" for k in STATUS_KEYS]
    vals = {k: _n(_v(facts, f"{prefix}.{k}"), lang) for k in STATUS_KEYS}
    return _st(S[lang][key].format(p=plan, **vals), ids, facts=facts)


def _changes_line(facts, lang, prefix, key, plan=None):
    keys = ("longer", "shorter", "unchanged", "lost_within_model", "became_uncertain", "gained")
    ids = [f"{prefix}.{k}" for k in keys]
    vals = {k: _n(_v(facts, f"{prefix}.{k}"), lang) for k in keys}
    return _st(S[lang][key].format(p=plan, longer=vals["longer"], shorter=vals["shorter"],
                                   unchanged=vals["unchanged"], lost=vals["lost_within_model"],
                                   uncertain=vals["became_uncertain"], gained=vals["gained"]), ids, facts=facts)


def _mean_line(facts, lang, prefix, key, plan=None):
    n = _v(facts, f"{prefix}.comparable_pairs")
    mean = _v(facts, f"{prefix}.mean_delta_m")
    return _st(S[lang][key].format(p=plan, n=_n(n, lang), delta=_delta(mean, lang)),
               [f"{prefix}.comparable_pairs", f"{prefix}.mean_delta_m"], kind="fact" if mean is not None else "missing",
               facts=facts)


def render_scenario(facts: dict, lang: str, focus: str = "compare") -> list[dict]:
    if "scenario.engine" not in facts:
        return []
    s = S[lang]
    ev = _v(facts, "scenario.graph_evidence_type")
    out = []
    graph_note = {"synthetic": "graph_synthetic", "hypothesis": "graph_hypothesis", "derived": "graph_derived",
                  None: "graph_unknown"}.get(ev)
    if graph_note:
        out.append(_st(s[graph_note], ["scenario.graph_evidence_type"], kind="notice"))
    # Перекрытие в сценарии — всегда гипотеза пользователя, даже на наблюдаемом графе.
    out.append(_st(s["hypothesis"], [], kind="notice"))
    mode, at = _v(facts, "scenario.mode"), _v(facts, "scenario.analysis_at")
    at_text = (facts["scenario.analysis_at"].get("meta") or {}).get("display", [None])[0] if at else None
    out.append(_st(s["run"].format(mode=s["mode"].get(mode, NO_DATA[lang]), at=at_text or NO_DATA[lang]),
                   ["scenario.mode", "scenario.analysis_at"], facts=facts))
    share = facts.get("scenario.known_access_share")
    if share and share["known"]:
        out.append(_st(s["coverage"].format(share=share["meta"]["display"][0]), ["scenario.known_access_share"],
                       kind="derived", facts=facts))
    out.append(_status_line(facts, lang, "scenario.baseline", "baseline"))
    plans = [p for p in PLAN_IDS if f"scenario.{p}.pairs" in facts]
    for p in plans:
        if _v(facts, f"scenario.{p}.active_closures") == 0:
            out.append(_st(s["plan_no_active"].format(p=p), [f"scenario.{p}.active_closures"], kind="notice",
                           facts=facts))
        if focus == "impact" or "scenario.AB.comparable_pairs" not in facts:
            out.append(_status_line(facts, lang, f"scenario.{p}", "plan_status", p))
        out.append(_changes_line(facts, lang, f"scenario.{p}.vs_baseline", "plan_vs_base", p))
        out.append(_mean_line(facts, lang, f"scenario.{p}.vs_baseline", "plan_mean", p))
    if focus == "compare":
        if "scenario.AB.comparable_pairs" in facts:
            out.append(_st(s["ab_status"].format(a=_n(_v(facts, "scenario.A.ok"), lang),
                                                 b=_n(_v(facts, "scenario.B.ok"), lang),
                                                 pairs=_n(_v(facts, "scenario.A.pairs"), lang)),
                           ["scenario.A.ok", "scenario.B.ok", "scenario.A.pairs"], facts=facts))
            out.append(_changes_line(facts, lang, "scenario.AB", "ab_changes"))
            out.append(_mean_line(facts, lang, "scenario.AB", "ab_mean"))
        else:
            out.append(_st(s["ab_none"], [], kind="missing"))
    out.append(_st(s["metric_note"], [], kind="notice"))
    out.append(_st(s["unreachable_note"], [], kind="notice"))
    return out
