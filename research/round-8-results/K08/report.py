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
    return meta


CSS = """body{font:14px/1.45 system-ui,sans-serif;margin:24px;max-width:1100px;color:#1d2433;background:#fff}
h1{font-size:20px}h2{font-size:16px;margin-top:28px;border-bottom:1px solid #d6dbe4}
table{border-collapse:collapse;margin:8px 0;width:100%}th,td{border:1px solid #d6dbe4;padding:4px 6px;text-align:left;vertical-align:top}
th{background:#f2f4f8}.num{text-align:right;font-variant-numeric:tabular-nums}.muted{color:#5b6577}.warn{background:#fff6e0}
.tag{display:inline-block;border:1px solid #9aa3b2;border-radius:3px;padding:0 4px;font-size:12px}code{font-size:12px;word-break:break-all}"""


def _table(head, rows, num_cols=()):
    h = "<table><thead><tr>" + "".join(f"<th>{e(x)}</th>" for x in head) + "</tr></thead><tbody>"
    for r in rows:
        h += "<tr>" + "".join(f'<td class="num">{e(v)}</td>' if i in num_cols else f"<td>{e(v)}</td>" for i, v in enumerate(r)) + "</tr>"
    return h + "</tbody></table>"


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


def _plans_section(meta, cands):
    """Этап 1: ручной план. Этап 2 расширяет сравнением стратегий (см. _compare_section)."""
    man = meta["plans"]["manual"]
    out = ["<h2>Ручной план</h2>",
           f"<p>Выбрано: {e(', '.join(man['selected_ids']) or 'ничего')} · допустим: {e('да' if man['feasibility']['feasible'] else 'нет')}"
           + (f" ({e('; '.join(man['feasibility']['reasons']))})" if man["feasibility"]["reasons"] else "") + "</p>"]
    out.append(_metrics_table({"manual": man}))
    return "\n".join(out)


def _metrics_table(plans):
    rows = []
    for k, p in plans.items():
        if p is None:
            rows.append([STRATEGY_LABEL.get(k, k), "нет допустимого плана", "", "", "", "", "", ""])
            continue
        m = p["metrics"]
        rows.append([STRATEGY_LABEL.get(k, k), ", ".join(p["selected_ids"]) or "∅", m["cost"],
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
