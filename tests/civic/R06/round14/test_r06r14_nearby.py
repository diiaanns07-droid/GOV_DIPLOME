"""R06 волна 2 п. 4: «Что делают рядом» — работы и отключения от сотрудника для экрана R08 (R11 IA_WAVE2 §4).

Правила R11 проверяет сервер: 4 строки «Зачем?», у отключения — источник, время и где; задержки видны (план и
прогноз). Формат для R08 — ITEM из ui/civic_akim/nearby.py. Демо — пример R08 со сроками от сегодняшнего дня.
"""

from datetime import datetime, timedelta, timezone

import pytest

from r06r14_helpers import call, context, make_service
from ui.civic_store import v2 as v2mod
from ui.civic_store.demo_r14 import DEMO_NEARBY, seed_r14_demo

ASTANA = timezone(timedelta(hours=5))
WHY = {"problem": "Течь под двором", "reason": "Меняют днём", "result": "Напор вернётся", "inconvenience": "6 часов без воды"}


def outage(**over):
    body = {"type": "outage", "utility": "water", "district": "nura", "lang": "ru", "title": "Не будет воды",
            "zone": "ул. Кабанбай батыра, 48–56", "detour": "Вода в цистерне у дома 52", "source": "water",
            "start": "2026-10-12T10:00", "end": "2026-10-12T16:00", "why": dict(WHY)}
    body.update(over)
    return body


def work(**over):
    body = {"type": "work", "status": "in_progress", "work_kind": "roadworks", "district": "nura", "lang": "ru",
            "title": "Ремонт дороги на улице Е-308", "planned_end": "2026-10-13", "forecast_end": "2026-10-20",
            "why": dict(WHY)}
    body.update(over)
    return body


def create(staff, body):
    result = staff.call("POST", "/works", body)
    assert result["status"] == 201, result
    return result["body"]["data"]["item"]


def test_outage_reaches_r08_in_item_format(stack, staff):
    svc, v2 = stack
    made = create(staff, outage())
    assert made["revision"] == 1
    items = v2.nearby.items("nura")
    assert [i["id"] for i in items] == [made["id"]]
    item = items[0]
    assert item["type"] == "outage" and item["utility"] == "water" and item["source"] == "water"
    assert item["start"] == "2026-10-12T10:00:00+05:00" and item["end"] == "2026-10-12T16:00:00+05:00"
    assert item["title_ru"] == "Не будет воды" and item["title_kk"] is None      # перевода нет — R08 пометит
    assert item["zone_ru"].startswith("ул. Кабанбай") and item["why"]["problem_ru"] == "Течь под двором"
    assert item["demo"] is False and "revision" not in item and "texts" not in item   # служебного нет
    assert v2.nearby.items("esil") == []


@pytest.mark.parametrize("over, field", [
    ({"source": None}, "source"),
    ({"source": "Казводоканал АО"}, "source"),            # реальные названия не придумываем — только id службы
    ({"zone": None}, "zone"),
    ({"start": None}, "start"),
    ({"end": "2026-10-12T09:00"}, "end"),
    ({"end": "2026-10-30T09:00"}, "end"),                 # дольше 14 дней — это работа
    ({"utility": "internet"}, "utility"),
    ({"district": "mars"}, "district"),
    ({"why": {"problem": "Течь"}}, "why.reason"),
    ({"why": {**WHY, "problem": ""}}, "why.problem"),
    ({"title": "<script>x</script>"}, "title"),
    ({"status": "in_progress"}, "status"),
    ({"lang": "en"}, "lang"),
    ({"organization": "ТОО"}, "organization"),
])
def test_bad_outage_is_refused(stack, staff, over, field):
    result = staff.call("POST", "/works", outage(**over))
    assert result["status"] == 422, result
    fields = result["body"]["error"]["fields"]
    assert any(name == field or name.startswith(field + ".") for name in fields), fields


@pytest.mark.parametrize("over, field", [
    ({"status": "cancelled"}, "status"),
    ({"planned_end": None}, "planned_end"),
    ({"planned_end": "13.10.2026"}, "planned_end"),
    ({"work_kind": "rocket"}, "work_kind"),
    ({"why": None}, "why"),
    ({"end": "2026-10-12T16:00"}, "end"),
])
def test_bad_work_is_refused(stack, staff, over, field):
    result = staff.call("POST", "/works", work(**over))
    assert result["status"] == 422 and field in result["body"]["error"]["fields"], result


def test_delay_is_kept_so_r08_shows_shifted_deadline(stack, staff):
    svc, v2 = stack
    create(staff, work())
    item = v2.nearby.items("nura")[0]
    assert (item["planned_end"], item["forecast_end"], item["status"]) == ("2026-10-13", "2026-10-20", "in_progress")


def test_kazakh_only_text_fills_russian_fallback(stack, staff):
    svc, v2 = stack
    create(staff, outage(lang="kk", title="Су болмайды", zone="Қабанбай батыр көшесі, 48–56", detour=None,
                         why={"problem": "Құбыр ағып тұр", "reason": "Күндіз ауыстырады", "result": "Қысым қалпына келеді",
                              "inconvenience": "6 сағат су жоқ"}))
    item = v2.nearby.items("nura")[0]
    assert item["title_kk"] == "Су болмайды" and item["title_ru"] == "Су болмайды" and item["text_lang"] == "kk"
    assert item["why"]["problem_ru"] == "Құбыр ағып тұр" and item["detour_ru"] is None


def test_update_needs_revision_and_drops_stale_translation(stack, staff):
    svc, v2 = stack
    made = create(staff, outage())
    kk = staff.call("POST", f"/works/{made['id']}", outage(lang="kk", title="Су болмайды", zone="Қабанбай, 48–56",
                    detour=None, why={"problem": "Ағып тұр", "reason": "Күндіз", "result": "Қысым", "inconvenience": "6 сағат"},
                    expected_revision=1))
    assert kk["status"] == 200, kk
    # Текст на ru поменяли — kk другой текст: перевод устарел, оставлять его молча нельзя.
    item = v2.nearby.items("nura")[0]
    assert item["title_kk"] == "Су болмайды" and item["title_ru"] == "Су болмайды"
    stale = staff.call("POST", f"/works/{made['id']}", outage(expected_revision=1))
    assert stale["status"] == 409 and stale["body"]["error"]["current_revision"] == 2
    assert staff.call("POST", f"/works/{made['id']}", outage(title="")) ["status"] == 422   # без ревизии/названия


def test_status_change_keeps_translation(stack, staff, clock):
    svc, v2 = stack
    made = create(staff, work())
    texts = {"lang": "kk", "title": "Е-308 көшесінде жол жөндеу",
             "why": {"problem": "Шұңқырлар", "reason": "Құбырдан кейін", "result": "Жаңа асфальт", "inconvenience": "Бір жолақ жабық"}}
    staff.call("POST", f"/works/{made['id']}", work(expected_revision=1, **texts))
    # Тот же kk-текст, сменился только статус — перевод (ru удалён раньше) не теряется, kk сохраняется.
    done = staff.call("POST", f"/works/{made['id']}", work(expected_revision=2, status="done", **texts))
    assert done["status"] == 200
    item = v2.nearby.items("nura")[0]
    assert item["status"] == "done" and item["title_kk"] == "Е-308 көшесінде жол жөндеу"


def test_remove_hides_item_and_history_is_kept(stack, staff):
    svc, v2 = stack
    made = create(staff, outage())
    assert staff.call("POST", f"/works/{made['id']}/remove", {"expected_revision": 5})["status"] == 409
    assert staff.call("POST", f"/works/{made['id']}/remove", {"expected_revision": 1})["status"] == 200
    assert v2.nearby.items("nura") == [] and staff.call("GET", "/works")["body"]["data"]["items"] == []
    with svc.db.read() as conn:
        actions = [r["action"] for r in conn.execute("SELECT action FROM civic_nearby_history ORDER BY id")]
        assert actions == ["create", "remove"]
        with pytest.raises(Exception):
            conn.execute("DELETE FROM civic_nearby_history")


def test_works_are_staff_only(stack, staff):
    svc, v2 = stack
    assert call(v2, "GET", "/works")["status"] == 401
    assert call(v2, "POST", "/works", outage())["status"] == 401
    assert call(v2, "POST", "/works", outage(), ctx=context(staff.cookie))["status"] == 403   # без CSRF
    listed = staff.call("GET", "/works", query="district=nura")["body"]["data"]
    assert listed["items"] == [] and "water" in listed["options"]["sources"]


def test_gateway_functions_and_not_bound(stack, staff):
    svc, v2 = stack
    v2mod._BOUND = None
    with pytest.raises(v2mod.V2Error) as err:
        v2mod.nearby_items("nura")
    assert err.value.status == 503 and err.value.code == "module_not_ready"   # R08 тогда показывает свой пример
    v2mod.bind(svc)
    status, made = v2mod.create_work(outage(), context=staff.ctx())
    assert status == 201
    assert [i["id"] for i in v2mod.nearby_items(district="nura")] == [made["item"]["id"]]
    assert v2mod.list_works(district="nura", context=staff.ctx())["items"][0]["revision"] == 1
    with pytest.raises(v2mod.V2Error):
        v2mod.create_work(outage(), context=context())
    v2mod.update_work(made["item"]["id"], outage(expected_revision=1, title="Воды не будет"), context=staff.ctx())
    v2mod.remove_work(made["item"]["id"], {"expected_revision": 2}, context=staff.ctx())
    assert v2mod.nearby_items("nura") == []


def test_demo_items_follow_today_and_seed_is_idempotent(stack, clock):
    svc, v2 = stack
    report = seed_r14_demo(svc)
    assert [x["action"] for x in report["nearby"]] == ["create"] * len(DEMO_NEARBY)
    assert [x["action"] for x in seed_r14_demo(svc)["nearby"]] == ["kept"] * len(DEMO_NEARBY)
    items = {i["id"]: i for i in v2.nearby.items("nura")}
    water = items["nb-demo-water-nura"]
    today = clock().astimezone(ASTANA).date()
    tomorrow = (today + timedelta(days=1)).isoformat()
    assert water["start"] == f"{tomorrow}T10:00:00+05:00" and water["end"] == f"{tomorrow}T16:00:00+05:00"
    assert water["demo"] is True and water["title_kk"] == "Суық су болмайды"
    road = items["nb-demo-road-nura"]
    assert road["forecast_end"] > road["planned_end"]                              # задержка видна
    clock.advance(days=5)                                                           # показ через 5 дней — то же «завтра»
    later = {i["id"]: i for i in v2.nearby.items("nura")}["nb-demo-water-nura"]
    assert later["start"].startswith((today + timedelta(days=6)).isoformat())
    assert {i["district"] for i in v2.nearby.items()} == {"nura", "esil", "almaty"}


def test_demo_edited_by_staff_keeps_staff_dates(stack, staff):
    svc, v2 = stack
    seed_r14_demo(svc)
    body = outage(start="2026-10-14T09:00", end="2026-10-14T12:00", expected_revision=1)
    assert staff.call("POST", "/works/nb-demo-water-nura", body)["status"] == 200
    water = {i["id"]: i for i in v2.nearby.items("nura")}["nb-demo-water-nura"]
    assert water["start"] == "2026-10-14T09:00:00+05:00" and water["demo"] is True


def test_r08_feed_uses_r06_items_when_available(stack, staff, clock):
    """Стык с R08 (есть в дереве сборки R01): лента «Рядом» берёт записи R06, баннер отключения — из них.
    Часы ленты — те же тестовые, что у хранилища (иначе «завтра» демо-записи считается от другого дня)."""
    nearby = pytest.importorskip("ui.civic_akim.nearby")
    svc, v2 = stack
    seed_r14_demo(svc)
    now = clock()
    feed = nearby.feed("nura", now=now, nearby_fn=lambda district=None: v2.nearby.items(district), objects=lambda d, t: [])
    assert feed["sources"]["nearby"] == "r06"
    assert [b["id"] for b in feed["banners"]][:1] == ["nb-demo-water-nura"]
    assert feed["tabs"]["now"] >= 1 and feed["tabs"]["planned"] >= 1
    road = next(c for c in feed["items"] if c["id"] == "nb-demo-road-nura")
    assert road["delayed"] is True and road["why"]["reason_ru"].startswith("Сначала меняли трубы")
