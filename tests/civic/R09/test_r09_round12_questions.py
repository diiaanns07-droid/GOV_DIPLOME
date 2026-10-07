"""Раунд 12: полезные вопросы жителя RU/KK, которые раньше уходили в угаданный обзор.

Регрессии найдены прогоном вопросов из задания R09 (раунд 12) на базе 56538a3:
«какие сведения отсутствуют», «это реальные данные?», «куда жаловаться?», «Құны қайдан
алынды?», «Неше күнге ұзартылды?» получали intent=overview с warnings=['intent_guessed'].
"""

import copy

import pytest

from agent.civic_assistant import build_answer, build_verified_context
from agent.civic_assistant.audit import statement_violations
from agent.civic_assistant.facts import check_context

ROUTES = [
    ("Что здесь происходит?", "overview", "ru"),
    ("Что тут делают?", "overview", "ru"),
    ("Когда закончат ремонт?", "schedule", "ru"),
    ("На сколько сдвинули срок?", "schedule", "ru"),
    ("Что перенесли и почему?", "delay_reason", "ru"),
    ("Почему перенесли срок?", "delay_reason", "ru"),
    ("Кто отвечает?", "responsible", "ru"),
    ("Куда жаловаться?", "responsible", "ru"),
    ("Откуда стоимость?", "budget", "ru"),
    ("Откуда взялась сумма?", "budget", "ru"),
    ("Какие сведения отсутствуют?", "missing_data", "ru"),
    ("Чего не хватает в карточке?", "missing_data", "ru"),
    ("Какие данные неизвестны?", "missing_data", "ru"),
    ("Это реальные данные?", "sources", "ru"),
    ("Это настоящий ремонт?", "sources", "ru"),
    ("Работы уже идут?", "status", "ru"),
    ("Мұнда не болып жатыр?", "overview", "kk"),
    ("Жұмыс қашан аяқталады?", "schedule", "kk"),
    ("Мерзім неге ауыстырылды?", "delay_reason", "kk"),
    ("Кім жауапты?", "responsible", "kk"),
    ("Құны қайдан алынды?", "budget", "kk"),
    ("Қандай мәліметтер жоқ?", "missing_data", "kk"),
    ("Бұл нақты деректер ме?", "sources", "kk"),
    ("Неше күнге ұзартылды?", "schedule", "kk"),
]

# Слова, которые раньше давали ложное совпадение с новыми правилами.
NOT_CAPTURED = [
    ("Когда закончат демонтаж?", "schedule"),          # «демо» не должно уводить в источники
    ("В настоящее время что происходит?", "overview"),  # «настоящ» без «это настоящ»
]


@pytest.mark.parametrize("question,intent,lang", ROUTES)
def test_resident_questions_are_routed_without_guessing(ctx_of, question, intent, lang):
    a = build_answer(question, ctx_of("full"))
    assert a["intent"] == intent, (question, a["intent"])
    assert a["language"] == lang
    assert "intent_guessed" not in a["warnings"]
    assert a["source"] == "template"
    assert not [w for w in a["warnings"] if w.startswith("audit_dropped")], a["warnings"]


@pytest.mark.parametrize("question,intent", NOT_CAPTURED)
def test_new_stems_do_not_capture_other_questions(ctx_of, question, intent):
    assert build_answer(question, ctx_of("full"))["intent"] == intent


def test_missing_data_lists_exactly_the_unknown_fields(ctx_of):
    ctx = ctx_of("missing_deadline")
    facts = check_context(ctx)
    a = build_answer("Какие сведения отсутствуют?", ctx)
    listing = next(s for s in a["statements"] if s["text"].startswith("В опубликованной карточке не указано"))
    # Каждое названное поле действительно неизвестно в серверных фактах.
    assert listing["fact_ids"], listing
    assert all(not facts[fid]["known"] for fid in listing["fact_ids"])
    for label in ("текущий плановый срок окончания", "сумма", "ответственная организация", "источники сведений"):
        assert label in listing["text"]
    # Пустое поле не превращается в ноль и не выдаётся за «всё в порядке».
    assert "0 ₸" not in a["text"]
    assert any(s["kind"] == "notice" and "не ноль" in s["text"] for s in a["statements"])


def test_missing_data_on_complete_card_names_nothing_missing(ctx_of):
    a = build_answer("Какие сведения отсутствуют?", ctx_of("full"))
    assert "не указано" not in a["text"]
    assert "Основные поля карточки заполнены" in a["text"]
    # Фактическое окончание не требуется от незавершённых работ.
    assert "фактическая дата окончания" not in a["text"]


def test_missing_data_names_actual_end_only_for_completed(data):
    item = copy.deepcopy(data["objects"]["completed"])
    item["schedule"]["actual_end"] = None
    ctx = build_verified_context(item, data["history"].get("completed"))
    a = build_answer("Какие сведения отсутствуют?", ctx)
    assert "фактическая дата окончания" in a["text"]


def test_missing_data_flags_shift_without_published_reason(data):
    item = copy.deepcopy(data["objects"]["full"])
    item["schedule"]["original_planned_end"] = "2026-10-20"
    item["schedule"]["current_planned_end"] = "2026-10-29"
    history = [{"id": "h1", "object_id": item["id"], "revision": 1, "at": "2026-09-01T10:00:00+05:00",
                "changed_fields": ["publication"], "reason": "Публикация", "public_actor_label": "Редактор"},
               {"id": "h2", "object_id": item["id"], "revision": 2, "at": "2026-09-20T10:00:00+05:00",
                "changed_fields": ["schedule.current_planned_end"], "reason": None, "public_actor_label": "Редактор"}]
    ctx = build_verified_context(item, history)
    facts = check_context(ctx)
    a = build_answer("Чего не хватает в карточке?", ctx)
    assert "причина в публичной истории не указана" in a["text"]
    for st in a["statements"]:
        assert statement_violations(st, facts) == []
    # А с опубликованной причиной этой оговорки нет.
    history[1]["reason"] = "Поставщик задержал материалы (синтетика)"
    a2 = build_answer("Чего не хватает в карточке?", build_verified_context(item, history))
    assert "причина в публичной истории не указана" not in a2["text"]


def test_budget_question_about_origin_cites_the_source(ctx_of):
    facts = check_context(ctx_of("full"))
    a = build_answer("Откуда стоимость?", ctx_of("full"))
    assert any(fid.startswith("source.") for fid in a["fact_ids"]) or "Источник суммы не указан" in a["text"]
    for st in a["statements"]:
        assert statement_violations(st, facts) == []


def test_is_it_real_answers_with_evidence_type_first(ctx_of):
    a = build_answer("Это реальные данные?", ctx_of("full"))
    assert a["statements"][0]["kind"] == "notice"
    assert "синтетическ" in a["statements"][0]["text"]
