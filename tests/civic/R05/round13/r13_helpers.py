"""Общие данные и помощники синтетических проверок R05 раунда 13."""

import contextlib
import copy
import importlib.util
import io
import json
from pathlib import Path


REPO = Path(__file__).resolve().parents[4]
TOOL = REPO / "data/civic/astana/round13-verified/tools/r13.py"

SYNTH_URL_A = "https://example.invalid/r05-test/almaty-closure"
SYNTH_URL_B = "https://example.invalid/r05-test/almaty-closure-update"

# Синтетический текст страницы (не реальная новость): реальные названия улиц нужны только для геокодера OSM.
PAGE_A = """СИНТЕТИЧЕСКИЙ ТЕКСТ ДЛЯ ТЕСТА R05 — не реальная новость.
<h1>Улицу Алматы в Астане частично закроют до конца 2026 года</h1>
<p>Опубликовано: 18 июля 2026</p>
<p>В Астане с 20 июля 2026 года будет закрыт участок улицы Алматы от улицы Акмешит до улицы Сауран
в связи со строительством транспортного тоннеля. Работы ведёт ГУ «Управление транспорта (тест)».
Ограничение продлится до конца 2026 года. Объезд организован по соседним улицам, водителей просят
заранее планировать маршрут. Пешеходное движение по тротуарам сохраняется.</p>
<script>var fake = "в Астане сумма 999 000 000 тенге";</script>
<p>Сумма работ в сообщении не указана. Подрядчик в сообщении не назван.</p>
"""

PAGE_B = """СИНТЕТИЧЕСКИЙ ТЕКСТ ДЛЯ ТЕСТА R05 — не реальная новость (обновление).
<h1>Перекрытие улицы Алматы в Астане продлено</h1>
<p>Дата публикации: 01.10.2026</p>
<p>В Астане продолжаются работы на участке улицы Алматы от улицы Акмешит до улицы Сауран:
строительство транспортного тоннеля идёт по графику. Ограничение движения сохранится до 31 декабря 2026 года.
Работы ведутся круглосуточно, на участке работают две смены. Жителей просят учитывать ограничение
при планировании поездок. Иных изменений в схеме движения нет, остановки общественного транспорта
перенесены на соседние улицы.</p>
"""


def evidence_form_a(tool, **overrides):
    form = tool.evidence_form("test-almaty-closure", "src-r12-test-almaty-a", None, None, None)
    form["capture"].update({"attached_by": "оператор R05 (тест)", "retrieved_at": "2026-10-06T09:00:00Z"})
    form["page"] = {"title_quote": "Улицу Алматы в Астане частично закроют до конца 2026 года",
                    "published_on": "2026-07-18", "published_quote": "Опубликовано: 18 июля 2026",
                    "city_quote": "В Астане с 20 июля 2026 года будет закрыт участок"}
    claims = {c["field"]: c for c in form["claims"]}
    claims["what"].update(value="Закрытие участка улицы на время строительства тоннеля",
                          quote="в связи со строительством транспортного тоннеля")
    claims["location.text"].update(value="ул. Алматы от ул. Акмешит до ул. Сауран",
                                   quote="участок улицы Алматы от улицы Акмешит до улицы Сауран")
    claims["schedule.planned_start"].update(value="2026-07-20",
                                            quote="с 20 июля 2026 года будет закрыт участок улицы Алматы")
    claims["schedule.current_planned_end"].update(value="2026-12-31", claim_type="expected",
                                                  quote="Ограничение продлится до конца 2026 года",
                                                  value_basis="«до конца 2026 года» → 2026-12-31")
    claims["responsible.organization"].update(value="ГУ «Управление транспорта (тест)»",
                                              quote="Работы ведёт ГУ «Управление транспорта (тест)»")
    form["not_stated"] = ["budget.amount_kzt", "budget.basis"]
    for key, value in overrides.items():
        form[key] = value
    return form


def review_form_for(tool, slug, *, reviewer="сотрудник R04 (тест)", decision="accept", level=None, **extra):
    form = tool.review_form(slug)
    form["reviewer"] = reviewer
    form["decision"] = decision
    form["title"] = "Закрытие участка ул. Алматы (Акмешит — Сауран)"
    form["description"] = "Участок закрыт на время строительства тоннеля; сроки — по сообщению источника."
    form["claims"] = {k: "accept" for k in form["claims"]}
    if level is not None:
        form["geometry"]["level"] = level
    form.update(extra)
    return form


def run(tool, *argv):
    """main(argv) в процессе: (код, JSON-вывод)."""
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        code = tool.main(list(map(str, argv)))
    out = buf.getvalue()
    try:
        return code, json.loads(out)
    except ValueError:
        return code, out


def write(path: Path, value) -> Path:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=1), encoding="utf-8")
    return path


def attach_a(tool, home, form=None, *extra):
    form = form if form is not None else evidence_form_a(tool)
    path = write(home["tmp"] / "form-a.json", form)
    return run(tool, "attach", path, "--text", home["texts"] / "a.html", "--attached-at", "2026-10-06T10:00:00Z", *extra)


def review(tool, home, form, *extra):
    path = write(home["tmp"] / "review.json", form)
    return run(tool, "review", path, "--reviewed-at", "2026-10-06T12:00:00Z", *extra)
