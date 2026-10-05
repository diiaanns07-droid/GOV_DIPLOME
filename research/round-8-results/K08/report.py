"""K08 R8: генератор отчёта плана city-plan-v2 (HTML + JSON-метаданные).

Вход — результат planlib.plan_result(ctx, scenario). Выход:
  report.json  — метаданные отчёта (report_schema k08-plan-report/v1): сценарий, digests, срез, версии, планы, источники
  report.html  — самодостаточная страница: без <script>, без внешних ресурсов; CSP default-src 'none'.
Все строки из сценария и данных выводятся через html.escape; ссылки из пользовательских полей не создаются.

CLI:
  python report.py --app-root APP build SCENARIO.json --out-dir DIR
"""
import argparse
import html
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import planlib as P  # noqa: E402

REPORT_SCHEMA = "k08-plan-report/v1"
GENERATOR = "research/round-8-results/K08/report.py"
STRATEGY_LABEL = {"manual": "Ручной план", "mean": "Минимум средневзвешенного расстояния",
                  "minimax": "Минимум расстояния худшей точки", "coverage": "Максимум охвата в радиусе"}
ASSUMPTIONS = [
    "Стоимости кандидатов и бюджет — условные единицы, заданные пользователем (или явно synthetic demo). Это не тенге и не смета.",
    "Вес контрольной точки — приоритет пользователя, не численность жителей.",
    "coverage_radius_m — параметр анализа, не норматив пешей доступности.",
    "Кандидаты — гипотетические места (kind=hypothetical). Исходные записи не удаляются и не изменяются.",
]
LIMITATIONS = [
    "Расстояния по прямой (гаверсинус), не путь по улицам и не время в пути; население, мощность, трафик не учитываются.",
    "База — записи Overture внутри сохранённого квадрата; ближайшая запись в срезе не обязательно ближайшее учреждение в городе.",
    "Срез неполон, координаты могут быть ошибочны; QA-флаги — правила сборки, отсутствие флага не означает проверку.",
    "Оптимум найден только среди введённых кандидатов и условий; это не лучший план города и не прогноз социальной пользы.",
    "Если исходных записей нет, before=null: нулевое покрытие в этом наборе записей не доказывает отсутствие услуги в городе.",
    "Отчёт — сценарный анализ, не решение акимата и не обоснование расходов.",
]


def e(x):
    """Экранирование для HTML-текста и атрибутов."""
    return html.escape("—" if x is None else str(x), quote=True)


def m_fmt(mm):
    return "—" if mm is None else f"{mm / 1000:,.1f}".replace(",", " ")


def build_report(res, generated_utc=None):
    sc = res["scenario"]
    meta = {
        "report_schema": REPORT_SCHEMA, "generator": GENERATOR, "generated_utc": generated_utc,
        "scenario_schema": sc["schema_version"], "metric_version": res["metric_version"], "formula": res["formula"],
        "scenario_digest": res["scenario_digest"], "problem_digest": res["problem_digest"],
        "source": {k: res["context"].get(k) for k in ("city_id", "label", "source_snapshot", "release", "retrieved_utc",
                                                    "bbox", "places_file", "inputs", "data_js_sha256", "evidence_js_sha256",
                                                    "records_in_slice", "attribution")},
        "scenario": sc,
        "plans": res["plans"],
        "optimization": res["optimization"],
        "sensitivity": res["sensitivity"],
        "source_records": res["source_records"],
        "classes": {"user_input": ["scenario.*"], "observed_secondary": ["source.release", "source.bbox", "source.places_file",
                    "source.attribution", "source_records[*] (кроме qa)"],
                    "derived": ["source.source_snapshot", "*_digest", "plans", "optimization", "sensitivity", "source_records[*].qa"],
                    "config": ["metric_version", "formula", "assumptions", "limitations"]},
        "assumptions": ASSUMPTIONS, "limitations": LIMITATIONS,
        "status_note": "Гипотетический сценарный отчёт. Не решение акимата и не доказательство пользы строительства.",
    }
    meta["comparison"] = {"groups": [{"selected_ids": (res["plans"][rep] or {}).get("selected_ids"), "strategies": ks}
                                     for rep, ks in plan_groups(res["plans"])],
                          "explanation": explain(meta), "explanation_kind": "template over computed facts (not LLM)"}
    return meta


CSS = """body{font:14px/1.45 system-ui,sans-serif;margin:24px;max-width:1100px;color:#1d2433;background:#fff}
h1{font-size:20px}h2{font-size:16px;margin-top:28px;border-bottom:1px solid #d6dbe4}
table{border-collapse:collapse;margin:8px 0;width:100%}th,td{border:1px solid #d6dbe4;padding:4px 6px;text-align:left;vertical-align:top}
th{background:#f2f4f8}.num{text-align:right;font-variant-numeric:tabular-nums}.muted{color:#5b6577}.warn{background:#fff6e0}
.tag{display:inline-block;border:1px solid #9aa3b2;border-radius:3px;padding:0 4px;font-size:12px}code{font-size:12px;word-break:break-all}
.tw{overflow-x:auto;max-width:100%}td,p,li,h1,h2{overflow-wrap:anywhere}@media (max-width:600px){body{margin:12px}}"""


def _table(head, rows, num_cols=()):
    h = "<div class=\"tw\"><table><thead><tr>" + "".join(f"<th>{e(x)}</th>" for x in head) + "</tr></thead><tbody>"
    for r in rows:
        h += "<tr>" + "".join(f'<td class="num">{e(v)}</td>' if i in num_cols else f"<td>{e(v)}</td>" for i, v in enumerate(r)) + "</tr>"
    return h + "</tbody></table></div>"


def render_html(meta):
    sc, src = meta["scenario"], meta["source"]
    cands = {c["id"]: c for c in sc["candidates"]}
    parts = ["<!doctype html><html lang=\"ru\"><head><meta charset=\"utf-8\">",
             "<meta http-equiv=\"Content-Security-Policy\" content=\"default-src 'none'; style-src 'unsafe-inline'\">",
             "<meta name=\"referrer\" content=\"no-referrer\">",
             f"<title>{e('Сценарный отчёт: ' + (src.get('label') or sc['city_id']))}</title><style>{CSS}</style></head><body>",
             f"<h1>{e('Сценарный отчёт city-plan-v2 — ' + (src.get('label') or sc['city_id']) + ', ' + sc['category'])}</h1>",
             f"<p class=\"warn\">{e(meta['status_note'])}</p>"]
    parts.append("<h2>Происхождение и версии</h2>" + _table(["Поле", "Значение", "Класс"], [
        ["source_snapshot", src["source_snapshot"], "derived"],
        ["Выпуск Overture", src["release"], "observed_secondary"],
        ["Дата выгрузки пакета", src["retrieved_utc"], "observed_secondary"],
        ["Пакет K10", f"{(src.get('inputs') or {}).get('k10_branch')}@{(src.get('inputs') or {}).get('k10_sha')}", "observed_secondary"],
        ["Файл мест", f"{(src.get('places_file') or {}).get('path')} sha256 {(src.get('places_file') or {}).get('sha256')}", "observed_secondary"],
        ["data.js / evidence.js sha256", f"{src['data_js_sha256']} / {src['evidence_js_sha256']}", "derived"],
        ["Квадрат среза (bbox)", ", ".join(str(x) for x in src["bbox"]), "observed_secondary"],
        ["Записей категории в срезе", src["records_in_slice"], "derived"],
        ["metric_version / formula", f"{meta['metric_version']} / {meta['formula']}", "config"],
        ["problem_digest", meta["problem_digest"], "derived"],
        ["scenario_digest", meta["scenario_digest"], "derived"],
        ["Отчёт", f"{meta['report_schema']} · {meta['generator']} · {meta['generated_utc']}", "config"],
    ]))
    parts.append("<h2>Ввод пользователя</h2>")
    parts.append(f"<p>Бюджет: <b>{e(sc['budget'])}</b> <span class=\"tag\">условные единицы</span> · max_selected {e(sc['max_selected'])} · "
                 f"coverage_radius_m {e(sc['coverage_radius_m'])} <span class=\"tag\">параметр анализа</span></p>")
    parts.append(_table(["Контрольная точка", "lon", "lat", "Вес (приоритет)"],
                        [[p["id"], p["lon"], p["lat"], p["weight"]] for p in sc["control_points"]], (1, 2, 3)))
    parts.append(_table(["Кандидат", "lon", "lat", "Стоимость, усл. ед.", "kind", "Ограничение"],
                        [[c["id"], c["lon"], c["lat"], c["cost"], c["kind"],
                          "required" if c["id"] in sc["required_ids"] else ("excluded" if c["id"] in sc["excluded_ids"] else "")]
                         for c in sc["candidates"]], (1, 2, 3)))
    parts.append(_plans_section(meta, cands))
    parts.append(_sources_section(meta))
    parts.append("<h2>Допущения</h2><ul>" + "".join(f"<li>{e(x)}</li>" for x in meta["assumptions"]) + "</ul>")
    parts.append("<h2>Ограничения</h2><ul>" + "".join(f"<li>{e(x)}</li>" for x in meta["limitations"]) + "</ul>")
    att = src.get("attribution") or []
    att_rows = [[a.get("dataset"), a.get("layer"), a.get("license")] if isinstance(a, dict) else [a, "", ""] for a in att]
    parts.append("<h2>Атрибуция поставщиков данных среза</h2>" + _table(["Поставщик", "Слой", "Лицензия"], att_rows)
                 + "<p class=\"muted\">Тексты лицензий и ATTRIBUTION.md поставляются с демо (web/attribution/). "
                   "Поле лицензии записи — не юридическая проверка.</p></body></html>")
    return "\n".join(parts)


def plan_groups(plans):
    """Свернуть одинаковые наборы: [(ключ_представителя, [ключи стратегий]), ...] в порядке manual, mean, minimax, coverage."""
    groups = []
    for k in ("manual", "mean", "minimax", "coverage"):
        p = plans.get(k)
        sel = tuple(p["selected_ids"]) if p else None
        for g in groups:
            if g[2] == sel:
                g[1].append(k)
                break
        else:
            groups.append((k, [k], sel))
    return [(g[0], g[1]) for g in groups]


def explain(meta):
    """Шаблонное объяснение по вычисленным фактам (не LLM)."""
    pl, opt = meta["plans"], meta["optimization"]
    out = []
    if opt["status"] != "optimal":
        return ["Допустимых наборов нет: " + "; ".join(opt.get("infeasible_reasons") or []) + ". Ограничения не снимались."]
    groups = plan_groups(pl)
    if len(groups) == 1:
        out.append("Ручной план совпадает со всеми тремя оптимальными наборами; это один и тот же набор, а не три решения.")
    else:
        for rep, ks in groups:
            if len(ks) > 1:
                out.append("Совпадают: " + ", ".join(STRATEGY_LABEL[k] for k in ks) + ".")
    m = {k: pl[k]["metrics"] for k in ("mean", "minimax", "coverage") if pl.get(k)}
    if pl["mean"]["selected_ids"] != pl["minimax"]["selected_ids"]:
        out.append(f"«Средневзвешенное» и «худшая точка» дают разные наборы: средневзвешенное {m_fmt(m['mean']['weighted_mean_mm'])} м против "
                   f"{m_fmt(m['minimax']['weighted_mean_mm'])} м, худшая точка {m_fmt(m['mean']['max_mm'])} м против {m_fmt(m['minimax']['max_mm'])} м.")
    if pl["coverage"]["selected_ids"] != pl["mean"]["selected_ids"]:
        out.append(f"«Охват» выбирает набор с весом в радиусе {m['coverage']['covered_weight']} против {m['mean']['covered_weight']} у «средневзвешенного».")
    out.append(f"Оптимум найден полным перебором {opt['evaluated']} наборов ({opt['feasible_count']} допустимых) только среди введённых кандидатов при условном бюджете.")
    out.append("Вывод о вместимости, нагрузке или пользе для жителей из этих расстояний сделать нельзя: мощность и население не учитываются.")
    return out


def _plans_section(meta, cands):
    pl, opt = meta["plans"], meta["optimization"]
    sc = meta["scenario"]
    out = ["<h2>Сравнение планов</h2>",
           f"<p>Бюджет {e(sc['budget'])} <span class=\"tag\">условные единицы, не тенге и не смета</span> · статус поиска: "
           f"<b>{e(opt['status'])}</b> · перебрано {e(opt['evaluated'])}, допустимо {e(opt['feasible_count'])}. "
           "Результат поиска — предложение; применяет пользователь.</p>"]
    man = pl["manual"]
    if not man["feasibility"]["feasible"]:
        out.append(f"<p class=\"warn\">Ручной план недопустим: {e('; '.join(man['feasibility']['reasons']))}</p>")
    if opt["status"] != "optimal":
        out.append(f"<p class=\"warn\">Нет допустимых наборов: {e('; '.join(opt.get('infeasible_reasons') or []))}</p>")
    groups = plan_groups(pl)
    out.append(_metrics_table({rep: pl[rep] for rep, _ in groups}, {rep: ks for rep, ks in groups}))
    out.append("<h2>Объяснение (шаблон по вычисленным фактам, не LLM)</h2><ul>" + "".join(f"<li>{e(x)}</li>" for x in explain(meta)) + "</ul>")
    names = {r["id"]: r.get("name") for r in meta["source_records"]}
    for rep, ks in groups:
        p = pl[rep]
        if p is None:
            continue
        out.append(f"<h2>По точкам: {e(' = '.join(STRATEGY_LABEL[k] for k in ks))}</h2>")
        rows = []
        for r in p["rows"]:
            na = r["nearest_after"]
            who = "—" if na is None else (f"исходная запись {na['id']} {names.get(na['id']) or ''}".strip() if na["kind"] == "source"
                                          else f"гипотетический {na['id']}")
            rows.append([r["id"], r["weight"], m_fmt(r["before_mm"]), m_fmt(r["after_mm"]),
                         m_fmt(r["delta_mm"]) if r["delta_mm"] is not None else "—", who])
        out.append(_table(["Точка", "Вес", "До, м", "После, м", "Разница, м (по прямой)", "Ближайшая после"], rows, (1, 2, 3, 4)))
    if opt["pareto"]:
        out.append("<h2>Парето: условная стоимость → взвешенная сумма расстояний</h2>" + _table(
            ["Стоимость, усл. ед.", "Взвешенная сумма, м", "Объекты"],
            [[x["cost"], m_fmt(x["weighted_sum_mm"]), ", ".join(x["selected_ids"]) or "∅"] for x in opt["pareto"]], (0, 1)))
    out.append("<h2>Изменение бюджета (те же кандидаты, веса, ограничения)</h2>" + _table(
        ["Бюджет, усл. ед.", "Статус", "Средневзв.", "Худшая точка", "Охват", "Средневзв., м"],
        [[s["budget"], s["status"]] + [", ".join(s["objectives"][k]) if s["objectives"].get(k) is not None else "—" for k in ("mean", "minimax", "coverage")]
         + [m_fmt(s["mean_metrics"]["weighted_mean_mm"]) if s["mean_metrics"] and s["mean_metrics"]["weighted_mean_mm"] is not None else "—"]
         for s in meta["sensitivity"]], (0, 5))
        + "<p class=\"muted\">Исследование параметра бюджета, не прогноз экономии и не вероятностная устойчивость.</p>")
    return "\n".join(out)


def _metrics_table(plans, merged=None):
    rows = []
    for k, p in plans.items():
        label = " = ".join(STRATEGY_LABEL.get(x, x) for x in (merged or {}).get(k, [k]))
        if p is None:
            rows.append([label, "нет допустимого плана", "", "", "", "", "", ""])
            continue
        m = p["metrics"]
        rows.append([label, ", ".join(p["selected_ids"]) or "∅", m["cost"],
                     m_fmt(m["weighted_mean_mm"]) if m["weighted_mean_mm"] is not None else "—",
                     m_fmt(m["max_mm"]), f"{m['covered_weight']} ({m['coverage_fraction']:.0%})", m["unknown_count"],
                     "да" if p["feasibility"]["feasible"] else "нет"])
    return _table(["План", "Объекты", "Стоимость, усл. ед.", "Средневзв., м", "Худшая точка, м", "Охват веса", "Без расстояния", "Допустим"],
                  rows, (2, 3, 4, 6))


def _sources_section(meta):
    rows = []
    for r in meta["source_records"]:
        srcs = "; ".join(f"{s.get('dataset')} · {s.get('license')} · {s.get('record_id') or '—'} · {s.get('update_time') or '—'}"
                         for s in (r.get("sources") or []))
        qa = "; ".join(f["rule"] for f in r["qa"]["flags"]) or ("нет флагов (≠ проверено)" if r["qa"]["available"] else "QA недоступно")
        rows.append([r["id"], r.get("name"), r.get("category_overture"), r.get("confidence"), srcs, qa])
    return ("<h2>Исходные записи, использованные как ближайшие</h2>"
            + _table(["Overture id", "Название", "Категория Overture", "confidence", "Источник · лицензия · record_id · дата", "QA"], rows, (3,)))


def write(meta, out_dir):
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    (out / "report.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1, allow_nan=False) + "\n", encoding="utf-8")
    (out / "report.html").write_text(render_html(meta) + "\n", encoding="utf-8")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--app-root", required=True)
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build"); b.add_argument("scenario"); b.add_argument("--out-dir", required=True)
    b.add_argument("--generated-utc", default=None)
    a = ap.parse_args()
    ctx = P.Context(a.app_root)
    try:
        sc = P.validate_plan_scenario(P.loads_strict(Path(a.scenario).read_bytes()), ctx)
    except P.PlanError as err:
        print(f"ОТКЛОНЕНО {err.code}: {err.message}", file=sys.stderr)
        return 2
    meta = build_report(P.plan_result(ctx, sc), a.generated_utc)
    write(meta, a.out_dir)
    o = meta["optimization"]
    print(f"{sc['city_id']}/{sc['category']}: status {o['status']}, evaluated {o['evaluated']}, feasible {o['feasible_count']}; "
          f"report -> {a.out_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
