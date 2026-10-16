"""R04 П3: «ИИ-разбор пачки обращений» (сцена 0) — analyze(): итог, задачи, повторы, службы, место, срочность, пределы.

Пример — фикстура R04 ui/civic_ml_api/intake_sample_r04.json (42 придуманных обращения, demo: true), пока нет набора
R02. Тесты не ходят в сеть; тексты не уходят наружу.
"""

from __future__ import annotations

import json
import random
import re

import pytest

import ui.civic_ml_api as api
from ui.civic_ml_api import intake
from ui.civic_ml_api.intake import MAX_BYTES, MAX_TEXTS, analyze, load_sample

FIXTURE = json.loads(intake.SAMPLE_R04.read_text(encoding="utf-8"))
FIXTURE_TEXTS = [{"id": t["id"], "text": t["text"]} for t in FIXTURE["texts"]]
PII = ("87011234567", "880101300123")
TASK_FIELDS = {"id", "title_ru", "title_kk", "category", "subtopic", "services", "joint", "why_ru", "why_kk", "target",
               "point", "district", "address_text", "text_ids", "people", "texts", "urgent", "urgent_rule", "urgent_why",
               "urgent_why_ru", "urgent_why_kk", "evidence"}
_EMOJI = re.compile("[\U0001F300-\U0001FAFF☀-➿\U0001F000-\U0001F2FF]")


@pytest.fixture(scope="module")
def night():
    return analyze(FIXTURE_TEXTS)


def task_with(result, text_id):
    return next(t for t in result["tasks"] if text_id in t["text_ids"])


def test_fixture_is_synthetic_demo():
    assert FIXTURE["demo"] is True and FIXTURE["synthetic"] is True and 30 <= len(FIXTURE["texts"]) <= 50


def test_summary_numbers_are_counted_from_tasks(night):
    s, tasks = night["summary"], night["tasks"]
    assert set(s) >= {"total", "tasks", "services", "urgent", "merged", "no_address", "ms", "ready"}
    assert s["total"] == len(FIXTURE_TEXTS) == sum(t["people"] for t in tasks)
    assert s["tasks"] == len(tasks) and s["merged"] == s["total"] - s["tasks"]
    assert s["urgent"] == sum(t["urgent"] for t in tasks)
    assert s["no_address"] == sum(t["target"] is None for t in tasks) and s["ready"] + s["no_address"] == s["tasks"]
    assert s["services"] == len({x["id"] for t in tasks for x in t["services"]})
    assert 0 <= s["ms"] < 10_000
    # сгруппировано по ведущей службе: сумма задач в группах = число задач
    assert sum(g["tasks"] for g in night["services"]) == s["tasks"]
    assert night["demo"] is False and night["version"].startswith("r04-intake-")
    assert [t["id"] for t in tasks] == [f"t{n}" for n in range(1, len(tasks) + 1)]


def test_every_task_has_contract_fields(night):
    for task in night["tasks"]:
        assert TASK_FIELDS <= set(task), TASK_FIELDS - set(task)
        assert not any(k.startswith("_") for k in task)
        assert task["title_ru"] and task["title_kk"] and task["why_ru"] and task["why_kk"]
        assert task["services"] and all({"id", "role", "name_ru", "name_kk"} <= set(x) for x in task["services"])
        assert task["services"][0]["role"] == "lead"
        assert task["people"] == len(task["text_ids"]) and len(task["texts"]) == min(5, task["people"])


def test_same_stop_texts_ru_kk_latin_merged_into_one_task(night):
    shelter = task_with(night, "n01")
    assert shelter["category"] == "transport" and shelter["subtopic"] == "stop_shelter"
    assert set(shelter["text_ids"]) == {"n01", "n02", "n03", "n04", "n05", "n06"}       # ru, kk, латиница, «ост.»
    assert shelter["target"]["kind"] == "object" and shelter["target"]["label_ru"] == "Остановка «Хан Шатыр»"
    assert shelter["services"][0]["id"] == "transport"
    assert "Склеено 6 обращений: одно место, одна категория, похожий текст." in shelter["why_ru"]
    assert "6 өтініш біріктірілді" in shelter["why_kk"]
    lamp = task_with(night, "n07")                                     # та же остановка, другая категория
    assert lamp is not shelter and lamp["category"] == "lighting" and lamp["people"] == 1


def test_joint_case_two_services_with_explanation(night):
    dig = task_with(night, "n08")
    assert set(dig["text_ids"]) == {"n08", "n09", "n10"}
    assert [(x["id"], x["role"]) for x in dig["services"]] == [("water", "lead"), ("road", "partner")]
    assert dig["joint"] is True and dig["title_ru"].startswith("Яма после раскопок")
    assert "Водоканал" in dig["why_ru"] and "Дорожная служба" in dig["why_ru"]
    assert dig["target"]["kind"] == "segment" and dig["address_text"] == "улица Баян Сулу"
    tree = task_with(night, "n34")
    assert {x["id"] for x in tree["services"]} == {"greenery", "power"} and tree["title_ru"].startswith("Дерево на")


@pytest.mark.parametrize("text_id, rule", [("n16", "manhole"), ("n18", "wires"), ("n21", "no_heat"), ("n39", "gas"),
                                           ("n14", "children"), ("n34", "wires")])
def test_urgent_by_explicit_rules(night, text_id, rule):
    task = task_with(night, text_id)
    assert task["urgent"] is True and task["urgent_rule"] == rule
    assert task["urgent_why"] == task["urgent_why_ru"] and task["urgent_why_kk"]
    assert task["urgent_why_ru"].lower()[:-1] in task["why_ru"].lower()


def test_not_urgent_without_rule(night):
    for text_id in ("n07", "n30", "n24", "n11", "n37"):        # «не горит фонарь» — не пожар; яма; баки
        assert task_with(night, text_id)["urgent"] is False, text_id


def test_urgent_tasks_first_then_by_people(night):
    flags = [t["urgent"] for t in night["tasks"]]
    assert flags == sorted(flags, reverse=True)
    calm = [t["people"] for t in night["tasks"] if not t["urgent"]]
    assert calm == sorted(calm, reverse=True)


def test_place_not_guessed_without_a_name(night):
    for text_id in ("n36", "n39", "n40", "n41", "n42"):
        task = task_with(night, text_id)
        assert task["target"] is None and task["point"] is None and task["address_text"] == ""
        assert "уточните адрес" in task["why_ru"] and "мекенжайды нақтылаңыз" in task["why_kk"]
    dark = task_with(night, "n37")                    # без места склеиваются только одинаковые тексты
    assert dark["text_ids"] == ["n37", "n38"] and dark["target"] is None


def test_places_found_by_name_with_case_endings_and_kk(night):
    expect = {"n03": "Остановка «Хан Шатыр»", "n12": "Двор: ЖК Инжу Арена", "n15": "Двор: BI City Tokyo",
              "n17": "улица Сыганак", "n22": "Двор: Нурсая-2", "n25": "проспект Мангилик Ел", "n26": "проспект Мангилик Ел",
              "n29": "улица Кенесары", "n31": "Парк Жеруйык", "n32": "Остановка «Монумент Байтерек»"}
    for text_id, label in expect.items():
        assert task_with(night, text_id)["address_text"] == label, text_id


def test_bench_at_bus_stop_goes_to_stop_service(night):
    bench = task_with(night, "n33")
    assert bench["category"] == "transport" and bench["services"][0]["id"] == "transport"


def test_titles_follow_text(night):
    assert task_with(night, "n16")["title_ru"] == "Открытый люк · улица Сыганак"
    assert task_with(night, "n16")["title_kk"] == "Ашық люк · Сығанақ көшесі"
    assert task_with(night, "n41")["title_ru"] == "Нет горячей воды"
    assert task_with(night, "n24")["title_ru"].startswith("Яма на дороге")
    assert all(t["title_kk"] != t["title_ru"] for t in night["tasks"])


def test_personal_data_never_leaves_moderation(night):
    dump = json.dumps(night, ensure_ascii=False)
    assert not any(pii in dump for pii in PII)
    assert night["summary"]["pii_masked"] == 2
    assert any(x["id"] == "n02" and "Звоните ***" in x["text"] for x in task_with(night, "n02")["texts"])
    assert any(x["id"] == "n11" and "ИИН ***" in x["text"] for x in task_with(night, "n11")["texts"])


def test_no_emoji_in_response(night):
    """П1: без картинок и эмодзи — только текст и значки набора R11 на экране."""
    assert not _EMOJI.search(json.dumps(night, ensure_ascii=False))


def test_method_explains_what_is_ai_and_what_is_rules(night):
    m = night["method"]
    assert len(m["steps_ru"]) == len(m["steps_kk"]) == 5
    assert "подсказка ИИ" in " ".join(m["steps_ru"]) and "ЖИ кеңесі" in " ".join(m["steps_kk"])
    assert m["route"] and m["dedup"] and m["places"] == "birge.search_index.v1"


def test_input_forms_lines_dicts_and_short_lines():
    lines = "На остановке Хан Шатыр сломан навес\n\nок\nВо дворе ЖК Инжу Арена переполнены баки\n"
    r = analyze(lines)
    assert r["summary"]["total"] == 2 and [t for t in r["tasks"] if t["text_ids"] == ["t1"]]
    r = analyze([{"id": "a-1", "text": "Яма на проспекте Мангилик Ел"}, "Нет отопления в ЖК Нурсая-2"])
    assert {i for t in r["tasks"] for i in t["text_ids"]} == {"a-1", "t2"}


def test_limits_and_bad_input():
    with pytest.raises(ValueError):
        analyze(["Яма на дороге"] * (MAX_TEXTS + 1))
    with pytest.raises(ValueError):
        analyze(["я" * 1900] * 90)                                      # ≈ 342 КБ > 300 КБ
    assert len(("я" * 1900).encode()) * 90 > MAX_BYTES
    with pytest.raises(ValueError):
        analyze([])
    with pytest.raises(ValueError):
        analyze(["ок", "  "])
    with pytest.raises(ValueError):
        analyze([123])
    with pytest.raises(ValueError):
        analyze(None)
    with pytest.raises(ValueError):
        analyze(sample="day")
    with pytest.raises(ValueError):
        analyze({"texts": ["x"]})


def test_batch_id_is_stable_for_the_same_batch():
    a, b = analyze(FIXTURE_TEXTS), analyze(list(FIXTURE_TEXTS))
    assert re.fullmatch(r"[0-9a-f]{16}", a["batch_id"]) and a["batch_id"] == b["batch_id"]
    assert [t["text_ids"] for t in a["tasks"]] == [t["text_ids"] for t in b["tasks"]]
    assert analyze(FIXTURE_TEXTS[:-1])["batch_id"] != a["batch_id"]


def test_sample_night_is_demo():
    data = load_sample("night")
    assert data["demo"] is True and data["texts"] and "синтетика" in data["source"]
    r = analyze(sample="night")
    assert r["demo"] is True and r["summary"]["total"] == len(data["texts"])


def test_300_texts_within_ten_seconds():
    random.seed(15)
    tails = ["", " Срочно!", " Уже третий день.", " Өтінеміз, көмектесіңіздер.", " Жду ответа.", " Сколько можно?",
             " Просьба принять меры."]
    texts = [t["text"] + random.choice(tails) for t in FIXTURE["texts"] for _ in range(8)][:300]
    random.shuffle(texts)
    r = analyze(texts)
    assert r["summary"]["total"] == 300 and r["summary"]["ms"] < 10_000
    assert r["summary"]["tasks"] < 120                                  # повторы склеены
    assert len(json.dumps(r, ensure_ascii=False).encode()) < 400_000


def test_gateway_functions_staff_only_and_body():
    staff, ctx = {"username": "op", "role": "editor"}, {"headers": {}}
    with pytest.raises(PermissionError):
        api.intake_analyze(body={"sample": "night"}, context=ctx, principal=None)
    with pytest.raises(PermissionError):
        api.intake_sample(context=ctx, principal=None)
    with pytest.raises(PermissionError):
        api.intake_commit(body={"batch_id": "0" * 16}, context=ctx, principal=None)
    r = api.intake_analyze(body={"sample": "night"}, context=ctx, principal=staff)
    assert r["demo"] is True and r["summary"]["total"] == 42
    r = api.intake_analyze(body={"texts": ["Яма на проспекте Мангилик Ел"]}, context=ctx, principal=staff)
    assert r["summary"]["total"] == 1 and r["demo"] is False
    with pytest.raises(ValueError):
        api.intake_analyze(body={"sample": 1}, context=ctx, principal=staff)
    assert api.intake_sample(context=ctx, principal=staff)["demo"] is True
