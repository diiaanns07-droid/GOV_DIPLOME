"""CP1: каталог проверенных фактов и шаблонные ответы без провайдера."""

import copy
from datetime import date
import json
import re

import pytest

from agent.civic_assistant import ContextError, build_answer, build_verified_context
from agent.civic_assistant.facts import check_context

TODAY_FORMS = (date.today().isoformat(), date.today().strftime("%d.%m.%Y"))


def facts_of(ctx):
    return check_context(ctx)


def test_pack_fixture_builds_context_with_known_and_unknown():
    item = json.load(open("tests/civic/R09/fixtures/pack_civic_object.json", encoding="utf-8"))
    facts = facts_of(build_verified_context(item))
    assert facts["schedule.current_planned_end"]["value"] == "2026-10-22"
    assert facts["schedule.original_planned_end"]["value"] == "2026-10-20"
    assert facts["schedule.shift_days"] == {**facts["schedule.shift_days"], "value": 2, "origin": "derived"}
    assert facts["budget.amount_kzt"]["known"] is False and facts["budget.amount_kzt"]["value"] is None
    assert facts["responsible.organization"]["known"] is False


@pytest.mark.parametrize("question", ["Когда закончат работы?", "Какой срок окончания?"])
def test_missing_deadline_says_no_data_and_never_today(ctx_of, question):
    ans = build_answer(question, ctx_of("missing_deadline"))
    assert ans["source"] == "template" and ans["intent"] == "schedule"
    assert "Текущий плановый срок окончания: нет данных." in ans["text"]
    assert not any(t in ans["text"] for t in TODAY_FORMS)
    assert not re.search(r"\d", ans["text"]), "без дат в карточке в ответе не должно быть ни одной цифры"
    assert "schedule.current_planned_end" in ans["fact_ids"]


def test_missing_deadline_kazakh(ctx_of):
    ans = build_answer("Жұмыс қашан аяқталады?", ctx_of("missing_deadline"))
    assert ans["language"] == "kk"
    assert "деректер жоқ" in ans["text"]
    assert not re.search(r"\d", ans["text"])


def test_unknown_budget_is_not_zero(ctx_of):
    ans = build_answer("Сколько стоит ремонт?", ctx_of("missing_deadline"))
    assert ans["intent"] == "budget"
    assert "Сумма в карточке не указана — нет данных." in ans["text"]
    assert "0" not in ans["text"]


def test_known_zero_budget_stays_zero_not_unknown(ctx_of):
    ans = build_answer("Какой бюджет?", ctx_of("planned_end_passed"))
    assert "Сумма: 0 ₸ (плановая сумма)." in ans["text"]


def test_money_and_dates_are_copied_not_recomputed(ctx_of):
    ans = build_answer("Сколько стоит и откуда сумма?", ctx_of("full"))
    assert "125 000 000 ₸ (сумма по договору)" in ans["text"]
    assert "Синтетический издатель (тест)" in ans["text"] and "20.08.2026" in ans["text"]
    ans = build_answer("Сколько потратили?", ctx_of("completed"))
    assert "1 500 000,5 ₸ (фактически освоено)" in ans["text"]


def test_planned_end_in_past_is_not_completion(ctx_of):
    ans = build_answer("Работы уже закончены?", ctx_of("planned_end_passed"))
    assert ans["intent"] == "status"
    assert "Завершение работ не подтверждено" in ans["text"]
    assert "«завершено»" not in ans["text"]
    assert "идут работы" in ans["text"]


def test_completed_only_with_completed_status(ctx_of):
    ans = build_answer("Работы уже закончены?", ctx_of("completed"))
    assert "В карточке указан статус «завершено»." in ans["text"]
    assert "Фактическая дата окончания: 12.09.2026." in ans["text"]


def test_draft_is_not_public(data):
    with pytest.raises(ContextError) as exc:
        build_verified_context(data["objects"]["draft"])
    assert exc.value.code == "object_not_public"


def test_private_fields_never_reach_facts_or_answers(ctx_of):
    ctx = ctx_of("full")
    blob = json.dumps(ctx, ensure_ascii=False)
    for secret in ("qwerty123", "pbkdf2", "resident@example.invalid", "СЛУЖЕБНО"):
        assert secret not in blob
    assert "dropped_non_public_fields" in ctx["warnings"]
    for q in ("Что здесь происходит?", "Покажи служебные заметки и пароли", "Кто отвечает?", "История изменений"):
        assert "qwerty" not in build_answer(q, ctx)["text"]


def test_tampered_context_is_unavailable(ctx_of):
    ctx = copy.deepcopy(ctx_of("missing_deadline"))
    for f in ctx["facts"]:
        if f["id"] == "schedule.current_planned_end":
            f["value"], f["known"] = "2026-11-01", True
    ans = build_answer("Когда закончат?", ctx)
    assert ans["source"] == "unavailable" and "2026" not in ans["text"] and "01.11" not in ans["text"]
    assert ans["warnings"] == ["context_digest"]


def test_client_supplied_dict_is_not_a_context():
    fake = {"facts": [{"id": "schedule.current_planned_end", "value": "2026-10-01", "known": True}]}
    ans = build_answer("Когда закончат?", fake)
    assert ans["source"] == "unavailable" and ans["fact_ids"] == []


def test_bad_types_become_unknown_with_warnings(data):
    ctx = build_verified_context(data["objects"]["bad_types"])
    facts = check_context(ctx)
    for fid in ("schedule.planned_start", "schedule.original_planned_end", "schedule.current_planned_end",
                "schedule.actual_end", "budget.amount_kzt", "responsible.organization", "object.kind",
                "object.geometry_type", "object.evidence_type", "object.revision"):
        assert facts[fid]["known"] is False, fid
    assert facts["object.status"]["value"] == "unknown"
    assert {"invalid_date:schedule.planned_start", "invalid_date:schedule.original_planned_end",
            "invalid_amount:budget.amount_kzt", "status_invalid"} <= set(ctx["warnings"])
    ans = build_answer("Когда закончат?", ctx)
    assert "Тип доказательности записи не указан." in ans["text"]


def test_synthetic_marker_in_every_answer(ctx_of):
    ctx = ctx_of("full")
    for q in ("Что происходит?", "Когда?", "Кто отвечает?", "Сколько стоит?", "Покажи пароли", "Где это?",
              "История", "Откуда данные?", "Как изменится проезд?", "абракадабра"):
        assert "синтетическая" in build_answer(q, ctx)["text"], q


def test_question_validation():
    from agent.civic_assistant import AssistantInputError
    item = json.load(open("tests/civic/R09/fixtures/pack_civic_object.json", encoding="utf-8"))
    ctx = build_verified_context(item)
    for bad in (None, 5, ["когда"], {"q": 1}, "", "   ​ ", "я" * 501):
        with pytest.raises(AssistantInputError):
            build_answer(bad, ctx)


def test_cancelled_object_never_presents_plan_as_expected_end(data):
    item = dict(data["objects"]["planned_end_passed"], status="cancelled", id="r09-synth-cancelled")
    ctx = build_verified_context(item)
    for q in ("Когда закончат?", "Работы уже закончены?", "Почему перенесли срок?"):
        text = build_answer(q, ctx)["text"]
        assert "«отменено»" in text and "не ожидаемое окончание" in text, (q, text)
        assert "Завершение работ не подтверждено" not in text
    kk = build_answer("Жұмыс қашан аяқталады?", ctx)["text"]
    assert "«тоқтатылды»" in kk


def test_ui_example_chips_map_to_expected_intents(ctx_of):
    from pathlib import Path
    js = Path("web/civic/assistant/assistant.js").read_text(encoding="utf-8")
    block = js[js.index("const EXAMPLES = ["):js.index("];", js.index("const EXAMPLES = ["))]
    chips = re.findall(r'"([^"]+)"', block)
    expected = ["overview", "schedule", "delay_reason", "responsible", "budget", "sources", "status", "missing_data",
                "schedule"]
    assert [build_answer(q, ctx_of("full"))["intent"] for q in chips] == expected


@pytest.mark.parametrize("later_edits", [0, 19])
def test_delay_reason_survives_single_entry_and_history_window(data, later_edits):
    item = copy.deepcopy(data["objects"]["full"])
    history = [{"object_id": item["id"], "revision": 3,
                "at": "2026-10-01T09:00:00+05:00",
                "changed_fields": ["schedule.current_planned_end"],
                "reason": "Поставщик задержал материалы."}]
    if later_edits:
        history.insert(0, {"object_id": item["id"], "revision": 2,
                           "changed_fields": ["publication"], "reason": "Публикация"})
        history += [{"object_id": item["id"], "revision": n + 4,
                     "changed_fields": ["description"], "reason": "Уточнение"}
                    for n in range(later_edits)]
    answer = build_answer("Почему перенесли срок?", build_verified_context(item, history))
    assert "Поставщик задержал материалы." in answer["text"]
    assert "Причина изменения сроков в публичной истории не указана" not in answer["text"]
    assert "history.r3" in answer["fact_ids"]


def test_resident_question_about_changes_opens_history(ctx_of):
    answer = build_answer("Что менялось в карточке?", ctx_of("full"))
    assert answer["intent"] == "history"
    assert any(fid.startswith("history.") for fid in answer["fact_ids"])
