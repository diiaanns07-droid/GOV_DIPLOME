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


def make_home(tool, tmp_path):
    """Синтетический каталог пакета во временной папке; tool.HERE переключается на него (вызывающий восстанавливает)."""
    root = tmp_path / "r13home"
    (root / "analysis").mkdir(parents=True)
    base = tmp_path / "base"
    base.mkdir()
    sources = {"schema": "r05-r12-sources-v1", "city": "astana", "sources": [
        {"id": "src-r12-test-almaty-a", "url": SYNTH_URL_A, "publisher": "Синтетический издатель (тест)",
         "publisher_kind": "state_media", "access_status": "not_fetched"},
        {"id": "src-r12-test-almaty-b", "url": SYNTH_URL_B, "publisher": "Синтетический акимат (тест)",
         "publisher_kind": "official_gov", "access_status": "not_fetched"}]}
    cands = {"schema": "r05-r12-candidates-v1", "city": "astana", "candidates": [
        {"id": "cand-r12-test-almaty", "decision": "to_verify", "freshness": "current_or_upcoming_2026",
         "kind": "roadworks", "title_as_listed": "Синтетический кандидат (тест)",
         "source_ids": ["src-r12-test-almaty-a", "src-r12-test-almaty-b"]},
        {"id": "cand-r12-test-programme", "decision": "to_verify", "freshness": "current_or_upcoming_2026",
         "kind": "construction", "title_as_listed": "Синтетическая программа (тест)", "source_ids": []},
        {"id": "cand-r12-test-rejected", "decision": "rejected", "freshness": "unknown", "kind": "event",
         "title_as_listed": "Отклонённый (тест)", "source_ids": []}]}
    (base / "sources.json").write_text(json.dumps(sources, ensure_ascii=False), encoding="utf-8")
    (base / "candidates.json").write_text(json.dumps(cands, ensure_ascii=False), encoding="utf-8")
    cfg = json.loads((REPO / "data/civic/astana/round13-verified/config.json").read_text(encoding="utf-8"))
    cfg.update(base_sources=str(base / "sources.json"), base_candidates=str(base / "candidates.json"))
    (root / "config.json").write_text(json.dumps(cfg, ensure_ascii=False), encoding="utf-8")
    analysis = {"schema": "r05-r13-queue-analysis-v1", "as_of": "2026-10-07", "method": "synthetic test fixture",
                "clusters": [{"key": "test", "candidate_ids": ["cand-r12-test-almaty", "cand-r12-test-programme"],
                              "candidate_decisions": [
                                  {"candidate_id": "cand-r12-test-almaty", "role": "canonical", "related_to": [], "reason": "тест"},
                                  {"candidate_id": "cand-r12-test-programme", "role": "not_mappable_programme",
                                   "related_to": [], "reason": "тест"}],
                              "contradictions": [], "followup_hints": []}],
                "targets": [
                    {"slug": "test-almaty-closure", "kind": "roadworks", "title_ru": "Закрытие ул. Алматы (тест)",
                     "what_hint": "закрытие участка", "candidate_ids": ["cand-r12-test-almaty"],
                     "source_ids": ["src-r12-test-almaty-a", "src-r12-test-almaty-b"],
                     "location_text": "ул. Алматы, Акмешит — Сауран",
                     "osm_query": {"street": "Алматы", "from": "Акмешит", "to": "Сауран"},
                     "geometry_level": "street_segment", "mappable": True, "priority": 1,
                     "timing": {}, "required_evidence": [], "do_not_infer": [], "provability": {"score": 4, "reason": "тест"}},
                    {"slug": "test-programme", "kind": "construction", "title_ru": "Программа (тест)",
                     "what_hint": "программа", "candidate_ids": ["cand-r12-test-programme"], "source_ids": [],
                     "location_text": "город", "osm_query": None, "geometry_level": "none", "mappable": False,
                     "priority": 9, "timing": {}, "required_evidence": [], "do_not_infer": [],
                     "provability": {"score": 1, "reason": "тест"}}]}
    (root / "analysis" / "queue_analysis.json").write_text(json.dumps(analysis, ensure_ascii=False), encoding="utf-8")
    tool.HERE = root
    texts = tmp_path / "saved-pages"            # вне репозитория: tmp_path
    texts.mkdir()
    (texts / "a.html").write_text(PAGE_A, encoding="utf-8")
    (texts / "b.html").write_text(PAGE_B, encoding="utf-8")
    return {"root": root, "texts": texts, "tmp": tmp_path}
