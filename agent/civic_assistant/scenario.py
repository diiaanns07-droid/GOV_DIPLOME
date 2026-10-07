"""Факты сценарного сравнения из результата движка R07 (civic-scenario-result-v1).

Объяснение A/B строится только по метрикам engine: число пар с найденным путём,
изменения длины по сопоставимым парам, потеря пути в модели. Никакого «лучшего
плана» или «лучшего города», времени в пути, пробок и CO2: движок их не считает.
Формат проверен на выводе engine.civic_scenarios.compare (ветка R07
claude/brave-hopper-bkc58b, SHA 18f8ac8, синтетический кейс synthetic-tiny-v1-demo).
"""

from __future__ import annotations

import copy
from datetime import datetime
import hashlib
import json
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
        "graph_data": "Сеть: «{label}». Снимок OpenStreetMap на {snapshot}, получен {retrieved}; лицензия: {license}. "
                      "Это не оперативные данные.",
        "graph_data_short": "Сеть: «{label}»; дата снимка данных не указана.",
        "closure": "План {p}: перекрытие ({n} уч.) с {start} до {end} — по условию сценария в момент анализа {state}.",
        "closure_active": "действует",
        "closure_inactive": "не действует",
        "closure_unverified": "Интервалы перекрытий не показаны: входные данные сценария не совпали с расчётом.",
        "route_base": "Без перекрытий: путь {v} м.",
        "route_plan": "План {p}: путь {v} м — {delta} относительно состояния без перекрытий.",
        "route_plan_status": "План {p}: {status}.",
        "route_base_status": "Без перекрытий: {status}.",
        "route_ab": "От плана A к плану B путь {delta}.",
        "route_status": {"unreachable": "пути в модели нет", "unknown": "путь не подтверждён (участки с неизвестным доступом)"},
        "pair_label": "Пара {i}: ",
        "unknown_access": "Режим доступа неизвестен для {share} % длины сети; такие участки маршрутом не используются.",
        "unknown_by_edges_none": "Долю участков (рёбер) с неизвестным доступом по их числу движок не сообщает — нет "
                                 "данных; доля по длине и доля по числу участков — разные метрики.",
        "unknown_by_edges": "По числу участков (рёбер) режим доступа неизвестен для {share} %; это другая метрика, "
                            "чем доля по длине.",
        "slice": "Граф — прямоугольная выборка: сеть за её границей не моделируется; путь через внешнюю сеть мог бы "
                 "быть короче, а «нет пути» не доказано.",
        "no_best": "Помощник не ранжирует варианты: показаны только длины путей в модели, выбор остаётся за сотрудником.",
        "many_pairs": "Пар маршрутов: {n}; ниже — сводка по парам, а не каждый путь.",
        "ab_identical": "По данным движка, в момент анализа у планов A и B закрыты одни и те же участки, поэтому "
                        "результаты A и B совпадают.",
        "plan_not_on_base": "План {p}: по данным движка, закрытые участки не лежат на базовых путях выбранных пар, "
                            "поэтому длины путей не меняются.",
        "kind_user": "Это ваш расчёт: результат сравнения, выполненного сервером (идентификатор {digest}…), "
                     "сохранён {stored}.",
        "kind_user_short": "Это ваш расчёт: результат сравнения, выполненного сервером (идентификатор {digest}…).",
        "kind_prepared": "Это подготовленный пример сценария, а не ваш расчёт.",
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
        "graph_data": "Желі: «{label}». OpenStreetMap суреті {snapshot} күнгі, {retrieved} алынған; лицензия: {license}. "
                      "Бұл жедел деректер емес.",
        "graph_data_short": "Желі: «{label}»; деректер суретінің күні көрсетілмеген.",
        "closure": "{p} жоспары: жабылу ({n} учаске) {start} бастап {end} дейін — сценарий шарты бойынша талдау "
                   "сәтінде {state}.",
        "closure_active": "әрекет етеді",
        "closure_inactive": "әрекет етпейді",
        "closure_unverified": "Жабылу аралықтары көрсетілмеді: сценарийдің кіріс деректері есеппен сәйкес келмеді.",
        "route_base": "Жабылусыз: жол {v} м.",
        "route_plan": "{p} жоспары: жол {v} м — жабылусыз күймен салыстырғанда {delta}.",
        "route_plan_status": "{p} жоспары: {status}.",
        "route_base_status": "Жабылусыз: {status}.",
        "route_ab": "A жоспарынан B жоспарына жол {delta}.",
        "route_status": {"unreachable": "модельде жол жоқ", "unknown": "жол расталмаған (қолжетімділігі белгісіз учаскелер)"},
        "pair_label": "{i}-жұп: ",
        "unknown_access": "Желі ұзындығының {share} % үшін қолжетімділік режимі белгісіз; мұндай учаскелер маршрутта қолданылмайды.",
        "unknown_by_edges_none": "Қолжетімділігі белгісіз учаскелердің (қабырғалардың) саны бойынша үлесін қозғалтқыш "
                                 "хабарламайды — деректер жоқ; ұзындық бойынша үлес пен саны бойынша үлес — әртүрлі көрсеткіштер.",
        "unknown_by_edges": "Учаскелер (қабырғалар) саны бойынша {share} % үшін қолжетімділік режимі белгісіз; бұл "
                            "ұзындық бойынша үлестен басқа көрсеткіш.",
        "slice": "Граф — тікбұрышты үзінді: оның шекарасынан тыс желі модельденбейді; сыртқы желі арқылы жол қысқа "
                 "болуы мүмкін, ал «жол жоқ» дәлелденбеген.",
        "no_best": "Көмекші нұсқаларды саралап, ұсыныс бермейді: тек модельдегі жолдардың ұзындығы салыстырылады.",
        "many_pairs": "Маршрут жұптары: {n}; төменде әр жол емес, жұптар бойынша жиынтық.",
        "ab_identical": "Қозғалтқыш деректері бойынша талдау сәтінде A және B жоспарларында бірдей учаскелер жабық, "
                        "сондықтан A мен B нәтижелері бірдей.",
        "plan_not_on_base": "{p} жоспары: қозғалтқыш деректері бойынша жабық учаскелер таңдалған жұптардың базалық "
                            "жолдарында жатпайды, сондықтан жол ұзындықтары өзгермейді.",
        "kind_user": "Бұл сіздің есебіңіз: сервер орындаған салыстыру нәтижесі (идентификатор {digest}…), "
                     "{stored} сақталған.",
        "kind_user_short": "Бұл сіздің есебіңіз: сервер орындаған салыстыру нәтижесі (идентификатор {digest}…).",
        "kind_prepared": "Бұл сіздің есебіңіз емес, дайындалған сценарий мысалы.",
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


INPUT_SCHEMA = "civic-assistant-scenario-input-v1"
MAX_ROUTE_PAIRS = 3
MAX_CLOSURES = 5


def payload_digest(payload) -> str:
    """Тот же канонический JSON, что engine.civic_scenarios.canon.sha256_hex (sort_keys, без пробелов, UTF-8)."""
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


ENTRY_SCHEMA = "civic-assistant-scenario-entry-v2"
ENTRY_KINDS = ("user_result", "prepared_case")
# Поля, которые R07 добавляет вне дайджеста: timing_ms — HTTP-адаптер после compare().
_DIGEST_EXCLUDED = ("result_digest", "timing_ms")


def result_digest_ok(result) -> bool:
    """result_digest = sha256(canonical_json(result без result_digest/timing_ms)) — как в compare() R07."""
    digest = result.get("result_digest") if isinstance(result, dict) else None
    if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
        return False
    try:
        return payload_digest({k: v for k, v in result.items() if k not in _DIGEST_EXCLUDED}) == digest
    except (TypeError, ValueError):
        return False


def verify_user_result(payload, result) -> str | None:
    """None, если результат — проверенный ответ движка именно на этот вход; иначе код отказа."""
    if not isinstance(result, dict) or result.get("schema_version") != RESULT_SCHEMA:
        return "result_schema"
    if not result_digest_ok(result):
        return "result_digest_mismatch"
    inp = result.get("input") if isinstance(result.get("input"), dict) else {}
    if not isinstance(payload, dict):
        return "payload_missing"
    try:
        if payload_digest(payload) != inp.get("payload_digest"):
            return "payload_digest_mismatch"
    except (TypeError, ValueError):
        return "payload_digest_mismatch"
    if inp.get("city") != "astana" or payload.get("city") != "astana":
        return "city_mismatch"
    for key in ("graph_id", "graph_digest", "mode", "analysis_at"):
        if inp.get(key) != payload.get(key):
            return "input_mismatch:" + key
    for key in ("origin_node_ids", "destination_node_ids"):
        if not isinstance(payload.get(key), list) or set(map(str, inp.get(key) or [])) != set(map(str, payload[key])):
            return "input_mismatch:" + key
    want = [p.get("id") for p in payload.get("plans") or [] if isinstance(p, dict)]
    got = [p.get("id") for p in result.get("plans") or [] if isinstance(p, dict)]
    if not want or len(want) > len(PLAN_IDS) or sorted(want) != sorted(got) or any(x not in PLAN_IDS for x in got):
        return "plans_mismatch"
    return _totals_problem(result)


def _int(value):
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else None


def _status_ok(summary, pairs) -> bool:
    if not isinstance(summary, dict) or _int(summary.get("pairs")) != pairs:
        return False
    by = summary.get("by_status") if isinstance(summary.get("by_status"), dict) else {}
    counts = [_int(by.get(k)) for k in ("ok", "unknown", "unreachable")]
    return None not in counts and sum(counts) == pairs


def _changes_ok(summary, pairs) -> bool:
    if not isinstance(summary, dict) or _int(summary.get("pairs")) != pairs:
        return False
    ch = summary.get("changes") if isinstance(summary.get("changes"), dict) else {}
    keys = ("unchanged", "longer", "shorter", "lost_within_model", "became_uncertain", "gained", "not_comparable")
    counts = {k: _int(ch.get(k)) for k in keys}
    if None in counts.values() or sum(counts.values()) != pairs:
        return False
    return _int(summary.get("comparable_pairs")) == counts["unchanged"] + counts["longer"] + counts["shorter"]


def _totals_problem(result) -> str | None:
    """Итоги согласованы со входом: пар = точек отправления × назначения, суммы статусов и изменений сходятся."""
    inp = result["input"]
    origins, dests = inp.get("origin_node_ids"), inp.get("destination_node_ids")
    if not isinstance(origins, list) or not isinstance(dests, list):
        return "totals_mismatch:input"
    pairs = len(origins) * len(dests)
    base = result.get("baseline") if isinstance(result.get("baseline"), dict) else {}
    if not isinstance(base.get("routes"), list) or len(base["routes"]) != pairs \
            or not _status_ok(base.get("status_summary"), pairs):
        return "totals_mismatch:baseline"
    for plan in result.get("plans") or []:
        vs = plan.get("vs_baseline") if isinstance(plan.get("vs_baseline"), dict) else {}
        if not _status_ok(plan.get("status_summary"), pairs) or not _changes_ok(vs.get("summary"), pairs):
            return "totals_mismatch:plan_" + str(plan.get("id"))
    ids = {p.get("id") for p in result.get("plans") or [] if isinstance(p, dict)}
    ab = result.get("a_vs_b")
    if (ab is not None) != (ids == {"A", "B"}):
        return "totals_mismatch:a_vs_b"
    if ab is not None and (not isinstance(ab, dict) or ab.get("from_plan") != "A" or ab.get("to_plan") != "B"
                           or not _changes_ok(ab.get("summary"), pairs)):
        return "totals_mismatch:a_vs_b"
    return None


def _slim_route(r):
    keep = ("origin_node_id", "destination_node_id", "status", "length_m", "reason")
    return {k: r.get(k) for k in keep if k in r}


def _slim_pair(x):
    keep = ("origin_node_id", "destination_node_id", "from_status", "to_status", "delta_m", "change")
    return {k: x.get(k) for k in keep if k in x}


def _warning_codes(items) -> list[dict]:
    """Предупреждения движка: только коды (и число, если есть) — текст сообщений помощник не цитирует."""
    out = []
    for w in items or []:
        if isinstance(w, dict) and isinstance(w.get("code"), str) and len(w["code"]) <= 60:
            out.append({k: w[k] for k in ("code", "count") if k in w and (k == "code" or isinstance(w[k], int))})
    return out[:20]


def slim_result(result: dict) -> dict:
    """Только то, что читает scenario_facts: без edge_ids/node_ids маршрутов и без пар сверх MAX_ROUTE_PAIRS.

    Сводки движка (status_summary, vs_baseline.summary, a_vs_b.summary) копируются как есть.
    """
    base = result.get("baseline") if isinstance(result.get("baseline"), dict) else {}
    routes = [r for r in base.get("routes") or [] if isinstance(r, dict)]
    keep_pairs = len(routes) <= MAX_ROUTE_PAIRS
    od = {(r.get("origin_node_id"), r.get("destination_node_id")) for r in routes} if keep_pairs else set()

    def pairs(items):
        return [_slim_pair(x) for x in items or [] if isinstance(x, dict)
                and (x.get("origin_node_id"), x.get("destination_node_id")) in od]

    out = {k: result.get(k) for k in ("schema_version", "engine", "input", "graph_coverage",
                                       "assumptions", "limitations", "result_digest") if k in result}
    out["warnings"] = _warning_codes(result.get("warnings"))
    out["baseline"] = {"status_summary": base.get("status_summary"), "routes_total": len(routes),
                       "routes": [_slim_route(r) for r in routes] if keep_pairs else []}
    plans = []
    for p in result.get("plans") or []:
        if not isinstance(p, dict):
            continue
        vs = p.get("vs_baseline") if isinstance(p.get("vs_baseline"), dict) else {}
        active = p.get("active_closed_edge_ids")
        plans.append({"id": p.get("id"), "status_summary": p.get("status_summary"),
                      "active_closed_edge_count": len(active) if isinstance(active, list) else None,
                      # Интервалы и активность перекрытий — в closure_summary (из полного результата); здесь без рёбер.
                      "inactive_closure_count": len([c for c in p.get("inactive_closures") or [] if isinstance(c, dict)]),
                      "routes": [_slim_route(r) for r in p.get("routes") or [] if isinstance(r, dict)
                                 and (r.get("origin_node_id"), r.get("destination_node_id")) in od],
                      "vs_baseline": {"summary": vs.get("summary"), "pairs": pairs(vs.get("pairs"))},
                      "warnings": _warning_codes(p.get("warnings")),
                      **({"closed_on_baseline_count": len(p["closed_on_baseline_routes"])}
                         if isinstance(p.get("closed_on_baseline_routes"), list) else {})})
    out["plans"] = plans
    ab = result.get("a_vs_b") if isinstance(result.get("a_vs_b"), dict) else None
    out["a_vs_b"] = None if ab is None else {"from_plan": ab.get("from_plan"), "to_plan": ab.get("to_plan"),
                                             "summary": ab.get("summary"), "pairs": pairs(ab.get("pairs")),
                                             **({"identical_active_closures": ab["identical_active_closures"]}
                                                if isinstance(ab.get("identical_active_closures"), bool) else {})}
    return out


def closure_summary(result: dict, payload) -> list[dict] | None:
    """Интервалы перекрытий из ПРОВЕРЕННОГО входа (payload_digest совпал) — без списков рёбер."""
    inp = result.get("input") if isinstance(result.get("input"), dict) else {}
    try:
        if not isinstance(payload, dict) or payload_digest(payload) != inp.get("payload_digest"):
            return None
    except (TypeError, ValueError):
        return None
    plans = {p.get("id"): p for p in result.get("plans") or [] if isinstance(p, dict)}
    sig = lambda c: (c.get("start_at"), c.get("end_at"), sorted(c.get("edge_ids") or []))  # noqa: E731
    out = []
    for plan in payload.get("plans") or []:
        pid = plan.get("id") if isinstance(plan, dict) else None
        if pid not in PLAN_IDS or pid not in plans:
            continue
        inactive = [sig(c) for c in plans[pid].get("inactive_closures") or [] if isinstance(c, dict)]
        closures = [c for c in plan.get("closures") or [] if isinstance(c, dict) and isinstance(c.get("edge_ids"), list)]
        for c in closures[:MAX_CLOSURES]:
            out.append({"plan": pid, "edges": len(c["edge_ids"]), "start_at": clean_text(c.get("start_at"), 40),
                        "end_at": clean_text(c.get("end_at"), 40), "active": sig(c) not in inactive})
        if len(closures) > MAX_CLOSURES:
            out.append({"plan": pid, "truncated": True})
    return out


def make_entry(result: dict, payload, graph, *, kind: str, stored_at: str | None = None) -> dict:
    """Компактная запись для помощника (кэш и подготовленные кейсы): факты те же, что из полного результата."""
    if kind not in ENTRY_KINDS:
        raise ValueError("kind")
    entry = {"schema": ENTRY_SCHEMA, "kind": kind, "result": slim_result(result),
             "closures": closure_summary(result, payload), "graph": graph,
             "payload_digest": (result.get("input") or {}).get("payload_digest"),
             "result_digest": result.get("result_digest"), "stored_at": stored_at}
    # Отдельная копия: запись в кэше не меняется, если вызывающий код потом правит свой result/graph.
    return copy.deepcopy(entry)


def _date_display(value):
    """'2026-05-06T03:25:00Z' или '2026-10-07' -> '06.05.2026'; иначе None."""
    if not isinstance(value, str) or len(value) < 10:
        return None
    try:
        d = datetime.fromisoformat(value[:10])
    except ValueError:
        return None
    return f"{d.day:02d}.{d.month:02d}.{d.year:04d}"


def _graph_facts(graph, result_input, warnings):
    """Сведения о сети из MANIFEST R07 (сервер), только если это тот же граф, что в расчёте."""
    if not isinstance(graph, dict):
        return []
    if graph.get("id") != result_input.get("graph_id") or graph.get("digest") != result_input.get("graph_digest"):
        warnings.append("scenario_graph_info_mismatch")
        return []
    source = graph.get("source") if isinstance(graph.get("source"), dict) else {}
    lic = graph.get("license")
    if isinstance(lic, dict):
        parts = [clean_text(lic.get("id"), 40)] + [clean_text(a, 80) for a in (lic.get("attribution") or [])
                                                    if isinstance(a, str)]
        lic = "; ".join(x for x in parts if x) or None
    else:
        lic = clean_text(lic, 120)
    snap, got = clean_text(source.get("snapshot_at"), 40), clean_text(source.get("retrieved_at"), 40)
    return [
        _fact("scenario.graph.label", "graph_label", clean_text(graph.get("label"), 160), "text"),
        _fact("scenario.graph.snapshot_at", "graph_snapshot_at", snap, "timestamp",
              display=[_date_display(snap)] if _date_display(snap) else None),
        _fact("scenario.graph.retrieved_at", "graph_retrieved_at", got, "timestamp",
              display=[_date_display(got)] if _date_display(got) else None),
        _fact("scenario.graph.license", "graph_license", lic, "text"),
    ]


def _route_facts(result, warnings):
    """Длины путей по парам (до MAX_ROUTE_PAIRS) и разницы — только значения движка, без пересчёта."""
    base = result.get("baseline") if isinstance(result.get("baseline"), dict) else {}
    base_routes = [r for r in (base.get("routes") or []) if isinstance(r, dict)]
    total = base.get("routes_total") if isinstance(base.get("routes_total"), int) else len(base_routes)
    if not base_routes or total > MAX_ROUTE_PAIRS:
        return [], total
    key = lambda r: (r.get("origin_node_id"), r.get("destination_node_id"))  # noqa: E731
    plans = {p.get("id"): p for p in (result.get("plans") or []) if isinstance(p, dict) and p.get("id") in PLAN_IDS}
    ab = result.get("a_vs_b") if isinstance(result.get("a_vs_b"), dict) else {}
    ab_pairs = {key(x): x for x in (ab.get("pairs") or []) if isinstance(x, dict)}
    facts = []
    for i, br in enumerate(base_routes, start=1):
        pre = f"scenario.route{i}"
        facts += [_fact(pre + ".baseline.status", "route_status", br.get("status") if br.get("status") in
                        ("ok", "unknown", "unreachable") else None, "enum"),
                  _fact(pre + ".baseline.length_m", "route_length_m",
                        _num(br.get("length_m")) if br.get("status") == "ok" else None, "metric_m")]
        for pid, plan in plans.items():
            route = next((r for r in plan.get("routes") or [] if isinstance(r, dict) and key(r) == key(br)), None)
            vs = next((x for x in ((plan.get("vs_baseline") or {}).get("pairs") or [])
                       if isinstance(x, dict) and key(x) == key(br)), None)
            status = route.get("status") if route and route.get("status") in ("ok", "unknown", "unreachable") else None
            facts += [_fact(f"{pre}.{pid}.status", "route_status", status, "enum"),
                      _fact(f"{pre}.{pid}.length_m", "route_length_m",
                            _num(route.get("length_m")) if route and status == "ok" else None, "metric_m"),
                      _fact(f"{pre}.{pid}.delta_m", "route_delta_m", _num(vs.get("delta_m")) if vs else None,
                            "metric_m")]
        x = ab_pairs.get(key(br))
        if x is not None:
            facts.append(_fact(f"{pre}.AB.delta_m", "route_delta_m", _num(x.get("delta_m")), "metric_m"))
    return facts, len(base_routes)


def _closure_facts(result, payload, warnings):
    """Интервалы перекрытий из входа сценария; активность — по списку inactive_closures движка."""
    if isinstance(payload, dict) and payload.get("schema") == ENTRY_SCHEMA:
        summary = payload.get("closures")
        if summary is None:
            warnings.append("scenario_payload_mismatch")
            return [_fact("scenario.closures_unverified", "closures_unverified", True, "flag")]
        facts, counters = [], {}
        for c in summary:
            pid = c.get("plan")
            if c.get("truncated"):
                warnings.append("scenario_closures_truncated")
                continue
            counters[pid] = counters.get(pid, 0) + 1
            start, end = _fmt_at(c.get("start_at")), _fmt_at(c.get("end_at"))
            value = {"edges": c.get("edges"), "start_at": c.get("start_at"), "end_at": c.get("end_at"),
                     "active": bool(c.get("active"))}
            facts.append(_fact(f"scenario.{pid}.closure{counters[pid]}", "closure", value, "closure",
                               display=[x for x in (start, end) if x]))
        return facts
    if not isinstance(payload, dict):
        return []
    inp = result.get("input") if isinstance(result.get("input"), dict) else {}
    try:
        same = payload_digest(payload) == inp.get("payload_digest")
    except (TypeError, ValueError):
        same = False
    if not same:
        warnings.append("scenario_payload_mismatch")
        return [_fact("scenario.closures_unverified", "closures_unverified", True, "flag")]
    facts = []
    plans = {p.get("id"): p for p in (result.get("plans") or []) if isinstance(p, dict)}
    for plan in payload.get("plans") or []:
        pid = plan.get("id") if isinstance(plan, dict) else None
        if pid not in PLAN_IDS or pid not in plans:
            continue
        inactive = plans[pid].get("inactive_closures") or []
        sig = lambda c: (c.get("start_at"), c.get("end_at"), sorted(c.get("edge_ids") or []))  # noqa: E731
        inactive_sigs = [sig(c) for c in inactive if isinstance(c, dict)]
        for j, c in enumerate((plan.get("closures") or [])[:MAX_CLOSURES], start=1):
            if not isinstance(c, dict) or not isinstance(c.get("edge_ids"), list):
                continue
            start, end = _fmt_at(c.get("start_at")), _fmt_at(c.get("end_at"))
            value = {"edges": len(c["edge_ids"]), "start_at": clean_text(c.get("start_at"), 40),
                     "end_at": clean_text(c.get("end_at"), 40), "active": sig(c) not in inactive_sigs}
            facts.append(_fact(f"scenario.{pid}.closure{j}", "closure", value, "closure",
                               display=[x for x in (start, end) if x]))
        if len(plan.get("closures") or []) > MAX_CLOSURES:
            warnings.append("scenario_closures_truncated")
    return facts


def _unwrap(scenario):
    """Результат R07 как есть, обёртка v1 {schema, result, payload, graph} или запись v2 (make_entry)."""
    if isinstance(scenario, dict) and scenario.get("schema") == ENTRY_SCHEMA:
        return scenario.get("result"), scenario, scenario.get("graph")
    if isinstance(scenario, dict) and scenario.get("schema") == INPUT_SCHEMA:
        return scenario.get("result"), scenario.get("payload"), scenario.get("graph")
    return scenario, None, None


def scenario_facts(scenario, scenario_id=None) -> tuple[list[dict], list[str]]:
    """Нормализация результата compare() R07 в каталог фактов. Неизвестное -> known=False."""
    warnings: list[str] = []
    result, payload, graph = _unwrap(scenario)
    if not isinstance(result, dict) or result.get("schema_version") != RESULT_SCHEMA:
        raise ContextError("scenario_schema", "ожидается " + RESULT_SCHEMA)
    inp = result.get("input") if isinstance(result.get("input"), dict) else {}
    if inp.get("city") != "astana":
        raise ContextError("scenario_city", "раунд 11 — только Астана")
    if scenario_id is not None and (not isinstance(scenario_id, str) or not ID_RE.match(scenario_id)):
        raise ContextError("scenario_id")
    entry_kind = payload.get("kind") if isinstance(payload, dict) and payload.get("schema") == ENTRY_SCHEMA else None
    if entry_kind is not None and entry_kind not in ENTRY_KINDS:
        raise ContextError("scenario_kind", "неизвестный вид записи")
    if isinstance(scenario_id, str):
        # Смешение запрещено: "result:<digest>" — только проверенный расчёт пользователя с тем же digest,
        # id подготовленного кейса — никогда не пользовательский результат.
        if scenario_id.startswith("result:"):
            if entry_kind != "user_result" or scenario_id != "result:" + str(result.get("result_digest")):
                raise ContextError("scenario_kind_mismatch")
        elif entry_kind == "user_result":
            raise ContextError("scenario_kind_mismatch")
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
    if entry_kind is not None:
        stored = clean_text(payload.get("stored_at"), 40) if entry_kind == "user_result" else None
        digest = result.get("result_digest") if entry_kind == "user_result" else None
        facts += [_fact("scenario.kind", "scenario_kind", entry_kind, "enum"),
                  _fact("scenario.result_ref", "result_ref",
                        digest[:12] if isinstance(digest, str) and re.fullmatch(r"[0-9a-f]{64}", digest) else None,
                        "text"),
                  _fact("scenario.stored_at", "scenario_stored_at", stored, "timestamp",
                        display=[_fmt_at(stored)] if _fmt_at(stored) else None)]
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
        count = len(active) if isinstance(active, list) else _count(p.get("active_closed_edge_count"))
        facts.append(_fact(f"scenario.{pid}.active_closures", "active_closed_edges", count))
        # R07 1.1.0: сколько закрытых участков лежит на базовых путях пар (нет поля у 1.0 -> факта нет).
        on_base = p.get("closed_on_baseline_routes")
        on_base = len(on_base) if isinstance(on_base, list) else _count(p.get("closed_on_baseline_count"))
        if on_base is not None:
            facts.append(_fact(f"scenario.{pid}.closed_on_baseline", "closed_on_baseline_edges", on_base))
    ab = result.get("a_vs_b") if isinstance(result.get("a_vs_b"), dict) else None
    if ab and ab.get("from_plan") == "A" and ab.get("to_plan") == "B":
        facts += _change_facts("scenario.AB", ab.get("summary"))
        if isinstance(ab.get("identical_active_closures"), bool):  # R07 1.1.0
            facts.append(_fact("scenario.AB.identical_active_closures", "identical_active_closures",
                               ab["identical_active_closures"], "flag"))
    if any(f["value"] is None for f in facts if f["kind"] == "count"):
        warnings.append("scenario_metric_missing")
    route_facts, pairs = _route_facts(result, warnings)
    facts += route_facts
    facts.append(_fact("scenario.route_pairs", "route_pairs", pairs))
    facts += _closure_facts(result, payload, warnings)
    facts += _graph_facts(graph, inp, warnings)
    unknown = None if share is None else round((1 - share) * 100, 1)
    facts.append(_fact("scenario.unknown_access_share", "unknown_access_share",
                       None if share is None else round(1 - share, 4), "share",
                       display=[fmt_money(unknown)] if unknown is not None else None))
    # Доля по ЧИСЛУ рёбер — другая метрика; движок R07 (56538a3) её не возвращает -> known=False, не пересчитываем.
    by_edges = _num(cov.get("unknown_access_share_by_edges"))
    by_edges = by_edges if by_edges is not None and 0 <= by_edges <= 1 else None
    facts.append(_fact("scenario.unknown_access_share_by_edges", "unknown_access_share_by_edges", by_edges, "share",
                       display=[fmt_money(round(by_edges * 100, 1))] if by_edges is not None else None))
    codes = sorted({w.get("code") for w in result.get("warnings") or [] if isinstance(w, dict)
                    and isinstance(w.get("code"), str) and len(w["code"]) <= 60})
    facts.append(_fact("scenario.engine_warnings", "engine_warnings", codes, "codes"))
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


def _route_lines(facts, lang):
    """Длины путей по парам и разницы — значения движка; статус без пути — не ноль и не «закрыто»."""
    s = S[lang]
    out = []
    pairs = _v(facts, "scenario.route_pairs") or 0
    for i in range(1, pairs + 1):
        pre = f"scenario.route{i}"
        if f"{pre}.baseline.status" not in facts:
            continue
        label = s["pair_label"].format(i=i) if pairs > 1 else ""
        base_len = _v(facts, f"{pre}.baseline.length_m")
        if base_len is not None:
            out.append(_st(label + s["route_base"].format(v=fmt_money(base_len)),
                           [f"{pre}.baseline.length_m", f"{pre}.baseline.status"], facts=facts))
        else:
            status = _v(facts, f"{pre}.baseline.status")
            out.append(_st(label + s["route_base_status"].format(status=s["route_status"].get(status, NO_DATA[lang])),
                           [f"{pre}.baseline.status"], kind="missing", facts=facts))
        for pid in PLAN_IDS:
            if f"{pre}.{pid}.status" not in facts:
                continue
            length = _v(facts, f"{pre}.{pid}.length_m")
            if length is not None:
                out.append(_st(label + s["route_plan"].format(p=pid, v=fmt_money(length),
                                                              delta=_delta(_v(facts, f"{pre}.{pid}.delta_m"), lang)),
                               [f"{pre}.{pid}.length_m", f"{pre}.{pid}.delta_m", f"{pre}.{pid}.status"], facts=facts))
            else:
                status = _v(facts, f"{pre}.{pid}.status")
                out.append(_st(label + s["route_plan_status"].format(
                    p=pid, status=s["route_status"].get(status, NO_DATA[lang])), [f"{pre}.{pid}.status"],
                    kind="missing", facts=facts))
        if f"{pre}.AB.delta_m" in facts and _v(facts, f"{pre}.AB.delta_m") is not None:
            out.append(_st(label + s["route_ab"].format(delta=_delta(_v(facts, f"{pre}.AB.delta_m"), lang)),
                           [f"{pre}.AB.delta_m"], facts=facts))
    return out


def _closure_lines(facts, lang):
    s = S[lang]
    if "scenario.closures_unverified" in facts:
        return [_st(s["closure_unverified"], ["scenario.closures_unverified"], kind="notice")]
    out = []
    for fid in sorted(f for f in facts if re.match(r"^scenario\.[AB]\.closure\d+$", f)):
        c = facts[fid]
        v = c["value"]
        disp = (c.get("meta") or {}).get("display") or []
        if len(disp) != 2:
            continue
        out.append(_st(s["closure"].format(p=fid.split(".")[1], n=v["edges"], start=disp[0], end=disp[1],
                                           state=s["closure_active" if v["active"] else "closure_inactive"]),
                       [fid], facts=facts))
    return out


def _engine_explanations(facts, lang):
    """Объяснения A/B, которые движок сообщил сам (R07 1.1.0); у 1.0 этих фактов нет — фраз нет."""
    s = S[lang]
    out = []
    for pid in PLAN_IDS:
        if _v(facts, f"scenario.{pid}.closed_on_baseline") == 0 and (_v(facts, f"scenario.{pid}.active_closures") or 0) > 0:
            out.append(_st(s["plan_not_on_base"].format(p=pid),
                           [f"scenario.{pid}.closed_on_baseline", f"scenario.{pid}.active_closures"], facts=facts))
    if _v(facts, "scenario.AB.identical_active_closures") is True:
        out.append(_st(s["ab_identical"], ["scenario.AB.identical_active_closures"], facts=facts))
    return out


def _graph_lines(facts, lang):
    s = S[lang]
    label = _v(facts, "scenario.graph.label")
    if not label:
        return []
    snap = ((facts["scenario.graph.snapshot_at"].get("meta") or {}).get("display") or [None])[0] \
        if "scenario.graph.snapshot_at" in facts else None
    got = ((facts["scenario.graph.retrieved_at"].get("meta") or {}).get("display") or [None])[0] \
        if "scenario.graph.retrieved_at" in facts else None
    if snap:
        return [_st(s["graph_data"].format(label=label, snapshot=snap, retrieved=got or NO_DATA[lang],
                                           license=_v(facts, "scenario.graph.license") or NO_DATA[lang]),
                    ["scenario.graph.label", "scenario.graph.snapshot_at", "scenario.graph.retrieved_at",
                     "scenario.graph.license"], facts=facts)]
    return [_st(s["graph_data_short"].format(label=label), ["scenario.graph.label"], kind="missing", facts=facts)]


def _coverage_lines(facts, lang, by_edges=False):
    """Доля известного/неизвестного доступа всегда с основой («длины сети»); по числу рёбер — отдельная метрика."""
    s = S[lang]
    out = []
    share = facts.get("scenario.known_access_share")
    if share and share["known"]:
        out.append(_st(s["coverage"].format(share=share["meta"]["display"][0]), ["scenario.known_access_share"],
                       kind="derived", facts=facts))
    unknown = facts.get("scenario.unknown_access_share")
    if unknown and unknown["known"]:
        out.append(_st(s["unknown_access"].format(share=unknown["meta"]["display"][0]),
                       ["scenario.unknown_access_share"], kind="derived", facts=facts))
    edges = facts.get("scenario.unknown_access_share_by_edges")
    if by_edges and edges is not None:
        if edges["known"]:
            out.append(_st(s["unknown_by_edges"].format(share=edges["meta"]["display"][0]),
                           ["scenario.unknown_access_share_by_edges"], kind="derived", facts=facts))
        else:
            out.append(_st(s["unknown_by_edges_none"], ["scenario.unknown_access_share_by_edges"], kind="missing"))
    return out


def render_scenario_freshness(facts: dict, lang: str) -> list[dict]:
    """Для вопроса о свежести/полноте: снимок сети, дата получения и доли неизвестного доступа с основой."""
    if "scenario.engine" not in facts:
        return []
    return _graph_lines(facts, lang) + _coverage_lines(facts, lang, by_edges=True)


def render_scenario(facts: dict, lang: str, focus: str = "compare") -> list[dict]:
    if "scenario.engine" not in facts:
        return []
    s = S[lang]
    ev = _v(facts, "scenario.graph_evidence_type")
    out = []
    kind = _v(facts, "scenario.kind")
    if kind == "user_result":
        digest = _v(facts, "scenario.result_ref") or NO_DATA[lang]
        stored = ((facts.get("scenario.stored_at") or {}).get("meta") or {}).get("display") or []
        if stored and _v(facts, "scenario.stored_at"):
            out.append(_st(s["kind_user"].format(digest=digest, stored=stored[0]),
                           ["scenario.kind", "scenario.result_ref", "scenario.stored_at"], kind="notice", facts=facts))
        else:
            out.append(_st(s["kind_user_short"].format(digest=digest), ["scenario.kind", "scenario.result_ref"],
                           kind="notice", facts=facts))
    elif kind == "prepared_case":
        out.append(_st(s["kind_prepared"], ["scenario.kind"], kind="notice", facts=facts))
    graph_note = {"synthetic": "graph_synthetic", "hypothesis": "graph_hypothesis", "derived": "graph_derived",
                  None: "graph_unknown"}.get(ev)
    if graph_note:
        out.append(_st(s[graph_note], ["scenario.graph_evidence_type"], kind="notice"))
    # Перекрытие в сценарии — всегда гипотеза пользователя, даже на наблюдаемом графе.
    out.append(_st(s["hypothesis"], [], kind="notice"))
    out += _graph_lines(facts, lang)
    mode, at = _v(facts, "scenario.mode"), _v(facts, "scenario.analysis_at")
    at_text = (facts["scenario.analysis_at"].get("meta") or {}).get("display", [None])[0] if at else None
    out.append(_st(s["run"].format(mode=s["mode"].get(mode, NO_DATA[lang]), at=at_text or NO_DATA[lang]),
                   ["scenario.mode", "scenario.analysis_at"], facts=facts))
    out += _closure_lines(facts, lang)
    out += _engine_explanations(facts, lang)
    routes = _route_lines(facts, lang)
    if routes:
        out += routes
    else:
        pairs = _v(facts, "scenario.route_pairs")
        if pairs:
            out.append(_st(s["many_pairs"].format(n=pairs), ["scenario.route_pairs"], kind="notice", facts=facts))
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
    out += _coverage_lines(facts, lang)
    if "graph_is_slice" in (_v(facts, "scenario.engine_warnings") or []):
        out.append(_st(s["slice"], ["scenario.engine_warnings"], kind="notice"))
    if focus == "compare":
        out.append(_st(s["no_best"], [], kind="notice"))
    out.append(_st(s["metric_note"], [], kind="notice"))
    out.append(_st(s["unreachable_note"], [], kind="notice"))
    return out
