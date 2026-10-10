"""R06 раунд 14: этапы объекта, delay_days, stale и миграция старых записей без потерь."""

from datetime import date
import sqlite3

import pytest

from ui.civic_store import db as dbmod
from ui.civic_store.stages import compute_lifecycle, STAGES
from r06r14_helpers import ESIL_POINT, NURA_POINT, Staff, call, context, make_service, PASSWORD


TODAY = date(2026, 10, 11)


# --- чистый расчёт ------------------------------------------------------------------------

def life(**kw):
    base = {"stage": "construction", "planned_end": "2026-10-01", "forecast_end": None, "today": TODAY}
    base.update(kw)
    return compute_lifecycle(**base)


def test_overdue_counts_until_today_even_with_old_forecast():
    # План 1 окт, прогноз 5 окт уже прошёл, сегодня 11 окт → отстаёт на 10 дней, а не на 4.
    result = life(forecast_end="2026-10-05")
    assert result["delay_days"] == 10 and result["late"] is True


def test_future_forecast_after_plan_is_delay():
    result = life(planned_end="2026-10-20", forecast_end="2026-11-12")
    assert result["delay_days"] == 23 and result["late"] is True
    assert result["forecast_source"] == "editor"


def test_on_time_and_early_forecast():
    assert life(planned_end="2026-10-20")["delay_days"] == 0
    early = life(planned_end="2026-10-20", forecast_end="2026-10-15")
    assert early["delay_days"] == 0 and early["late"] is False


def test_moved_schedule_is_used_as_forecast():
    result = life(planned_end="2026-10-20", current_planned_end="2026-10-30")
    assert result["forecast_end"] == "2026-10-30" and result["forecast_source"] == "schedule"
    assert result["delay_days"] == 10


def test_operating_is_never_late_but_keeps_actual_delay():
    result = life(stage="operating", planned_end="2026-09-01", actual_end="2026-09-15")
    assert result["delay_days"] == 14 and result["late"] is False
    assert life(stage="operating")["delay_days"] == 0


def test_no_plan_or_no_stage_gives_none():
    assert life(planned_end=None)["delay_days"] is None
    assert life(stage=None)["delay_days"] is None and life(stage=None)["late"] is False


@pytest.mark.parametrize("days,stale", [(14, False), (15, True), (0, False)])
def test_stale_boundary_is_more_than_14_days(days, stale):
    result = life(last_update=date.fromordinal(TODAY.toordinal() - days))
    assert result["stale_days"] == days and result["stale"] is stale


def test_finished_or_unknown_objects_are_not_stale():
    old = date(2026, 1, 1)
    assert life(stage="operating", last_update=old)["stale"] is False
    assert life(stage=None, last_update=old)["stale"] is False


def test_stage_index_and_order():
    assert STAGES == ("planned", "design", "procurement", "construction", "acceptance", "operating")
    assert life(stage="procurement")["stage_index"] == 2


# --- API ---------------------------------------------------------------------------------

def test_public_object_has_stage_fields_and_default_from_status(staff):
    item = staff.create_object()
    result = call(staff.v2, "GET", f"/objects/{item['id']}")
    assert result["status"] == 200
    obj = result["body"]["data"]["item"]
    for key in ("stage", "planned_end", "forecast_end", "delay_days", "stale"):
        assert key in obj
    assert obj["stage"] == "planned" and obj["stage_source"] == "default"
    assert obj["planned_end"] == "2026-10-20" and obj["delay_days"] == 0
    assert obj["district"] == "nura" and obj["demo"] is True


def test_draft_is_invisible_publicly_but_stage_can_be_set(staff):
    draft = staff.create_object(publish=False)
    assert call(staff.v2, "GET", f"/objects/{draft['id']}")["status"] == 404
    result = staff.set_stage(draft["id"], 0, stage="design", planned_end="2026-12-01")
    assert result["status"] == 200, result
    assert result["body"]["data"]["item"]["stage"] == "design"
    listed = call(staff.v2, "GET", "/objects")["body"]["data"]["items"]
    assert draft["id"] not in [i["id"] for i in listed]


def test_set_stage_revision_conflict_and_history(staff, clock):
    item = staff.create_object()
    first = staff.set_stage(item["id"], 0, stage="procurement", planned_end="2026-10-01",
                            forecast_end="2026-10-25", reason="Объявлен тендер")
    assert first["status"] == 200
    data = first["body"]["data"]
    assert data["item"]["stage_revision"] == 1 and data["changed"] is True
    assert data["item"]["delay_days"] == 24 and data["item"]["late"] is True
    # Устаревшая форма: второй сотрудник со старой ревизией → 409, данные не тронуты.
    stale_form = staff.set_stage(item["id"], 0, stage="design")
    assert stale_form["status"] == 409 and stale_form["body"]["error"]["code"] == "stale_revision"
    assert stale_form["body"]["error"]["current_revision"] == 1
    # Та же форма ещё раз (двойной клик) — без новой ревизии.
    clock.advance(minutes=1)
    same = staff.set_stage(item["id"], 1, stage="procurement", planned_end="2026-10-01",
                           forecast_end="2026-10-25")
    assert same["body"]["data"]["changed"] is False and same["body"]["data"]["item"]["stage_revision"] == 1
    clock.advance(days=1)
    second = staff.set_stage(item["id"], 1, stage="construction", planned_end="2026-10-01",
                             forecast_end="2026-10-25")
    history = second["body"]["data"]["history"]
    assert [h["stage"] for h in history] == ["procurement", "construction"]
    assert history[0]["reason"] == "Объявлен тендер"
    public = call(staff.v2, "GET", f"/objects/{item['id']}")["body"]["data"]
    assert [h["stage"] for h in public["stage_history"]] == ["procurement", "construction"]
    assert "reason" not in public["stage_history"][0] and "actor_label" not in public["stage_history"][0]


def test_post_alias_for_gateway_without_put(staff):
    item = staff.create_object()
    result = staff.call("POST", f"/objects/{item['id']}/stage", {"expected_revision": 0, "stage": "design"})
    assert result["status"] == 200


@pytest.mark.parametrize("body,field", [
    ({"stage": "built"}, "stage"),
    ({"stage": "design", "planned_end": "2026-13-01"}, "planned_end"),
    ({"stage": "design", "forecast_end": "завтра"}, "forecast_end"),
    ({"stage": "design", "reason": "<b>x</b>"}, "reason"),
    ({"stage": "design", "delay_days": 5}, "delay_days"),
])
def test_set_stage_validation(staff, body, field):
    item = staff.create_object()
    result = staff.call("PUT", f"/objects/{item['id']}/stage", {"expected_revision": 0, **body})
    assert result["status"] == 422 and field in result["body"]["error"]["fields"]


def test_set_stage_requires_staff_and_csrf(staff):
    item = staff.create_object()
    anon = call(staff.v2, "PUT", f"/objects/{item['id']}/stage", {"expected_revision": 0, "stage": "design"})
    assert anon["status"] == 401
    no_csrf = call(staff.v2, "PUT", f"/objects/{item['id']}/stage", {"expected_revision": 0, "stage": "design"},
                   ctx=context(staff.cookie, None))
    assert no_csrf["status"] == 403 and no_csrf["body"]["error"]["code"] == "csrf_failed"
    cross = staff.call("PUT", f"/objects/{item['id']}/stage", {"expected_revision": 0, "stage": "design"},
                       same_origin=False)
    assert cross["status"] == 403
    missing = staff.set_stage("no-such-object", 0, stage="design")
    assert missing["status"] == 404


def test_stale_after_14_days_and_reset_by_update(staff, clock):
    item = staff.create_object()
    staff.set_stage(item["id"], 0, stage="construction", planned_end="2026-12-01")
    clock.advance(days=15)
    obj = call(staff.v2, "GET", f"/objects/{item['id']}")["body"]["data"]["item"]
    assert obj["stale"] is True and obj["stale_days"] == 15
    staff.set_stage(item["id"], 1, stage="acceptance", planned_end="2026-12-01")
    obj = call(staff.v2, "GET", f"/objects/{item['id']}")["body"]["data"]["item"]
    assert obj["stale"] is False and obj["stale_days"] == 0


def test_bbox_and_district_filters(staff):
    nura = staff.create_object()
    esil = staff.create_object(geometry={"type": "Point", "coordinates": ESIL_POINT})
    ids = lambda q: [i["id"] for i in call(staff.v2, "GET", "/objects", query=q)["body"]["data"]["items"]]
    assert set(ids("")) == {nura["id"], esil["id"]}
    assert ids("district=nura") == [nura["id"]]
    assert ids("bbox=71.40,51.08,71.44,51.10") == [esil["id"]]
    assert call(staff.v2, "GET", "/objects", query="bbox=1,2,3")["status"] == 400
    assert call(staff.v2, "GET", "/objects", query="district=mars")["status"] == 400


def test_lagging_for_akim_by_district(staff, clock):
    late = staff.create_object()
    ok_obj = staff.create_object()
    other = staff.create_object(geometry={"type": "Point", "coordinates": ESIL_POINT})
    staff.set_stage(late["id"], 0, stage="construction", planned_end="2026-10-01", forecast_end="2026-11-03")
    staff.set_stage(ok_obj["id"], 0, stage="design", planned_end="2027-05-01")
    staff.set_stage(other["id"], 0, stage="construction", planned_end="2026-09-01")
    clock.advance(days=20)  # ok_obj и other не обновлялись 20 дней → stale; late обновлялся тогда же
    data = staff.v2.lagging_objects("nura")
    assert [i["id"] for i in data["late"]] == [late["id"]]
    assert data["late"][0]["delay_days"] == 33
    assert {i["id"] for i in data["stale"]} == {late["id"], ok_obj["id"]}
    assert data["counts"] == {"total": 2, "late": 1, "stale": 2}
    city = call(staff.v2, "GET", "/objects/lagging")["body"]["data"]
    assert city["counts"]["late"] == 2 and city["late"][0]["id"] == other["id"]  # 60 дней > 33
    assert city["by_district"]["esil"] == {"total": 1, "late": 1, "stale": 1}


def test_survives_restart(staff, db_path, clock):
    item = staff.create_object()
    staff.set_stage(item["id"], 0, stage="acceptance", planned_end="2026-10-30")
    svc2, v2b = make_service(db_path, clock)
    obj = call(v2b, "GET", f"/objects/{item['id']}")["body"]["data"]["item"]
    assert obj["stage"] == "acceptance" and obj["stage_source"] == "editor"


# --- миграция ---------------------------------------------------------------------------

def _dump(path, table, order):
    conn = sqlite3.connect(path)
    try:
        return [tuple(r) for r in conn.execute(f"SELECT * FROM {table} ORDER BY {order}")]
    finally:
        conn.close()


def test_migration_6_keeps_objects_and_history_and_derives_stage(tmp_path, clock, monkeypatch):
    path = tmp_path / "old.sqlite3"
    # База «раунда 13»: только миграции 1–5.
    monkeypatch.setattr(dbmod, "MIGRATIONS", dbmod.MIGRATIONS[:5])
    svc, _ = make_service(path, clock)
    svc.accounts.create_user("editor1", PASSWORD, display_name="Редактор", public_label="Акимат")
    from ui.civic_store.v2 import CivicV2
    staff = Staff(svc, CivicV2.__new__(CivicV2))
    planned = staff.create_object()
    progress = staff.create_object(status="in_progress",
                                   schedule={"planned_start": "2026-09-01", "original_planned_end": None,
                                             "current_planned_end": "2026-10-05", "actual_end": None})
    done = staff.create_object(status="completed",
                               schedule={"planned_start": "2026-06-01", "original_planned_end": None,
                                         "current_planned_end": "2026-08-01", "actual_end": "2026-08-10"})
    cancelled = staff.create_object(status="cancelled", publish=False)
    clock.advance(days=1)
    # Перенос срока после публикации: original_planned_end фиксируется, current меняется.
    upd = staff.v1("POST", f"/staff/objects/{progress['id']}/update", {
        "expected_revision": progress["revision"], "reason": "Перенос срока подрядчиком",
        "changes": {"schedule": {"original_planned_end": "2026-10-05", "current_planned_end": "2026-10-25"}}})
    assert upd["status"] == 200, upd
    pub = staff.v1("POST", f"/staff/objects/{progress['id']}/publish", {
        "expected_revision": upd["body"]["data"]["item"]["revision"], "reason": "Перенос срока"})
    assert pub["status"] == 200, pub
    before_objects = _dump(path, "civic_objects", "id")
    before_history = _dump(path, "civic_history", "id")
    before_public = _dump(path, "civic_public_objects", "id")
    assert len(before_history) >= 8

    monkeypatch.undo()  # код раунда 14: миграция 6 применяется при запуске
    monkeypatch.setattr(__import__("ui.civic_store.auth", fromlist=["x"]), "SCRYPT_N", 2 ** 10)
    svc2, v2 = make_service(path, clock)
    assert _dump(path, "civic_objects", "id") == before_objects
    assert _dump(path, "civic_history", "id") == before_history
    assert _dump(path, "civic_public_objects", "id") == before_public

    stages = {r[0]: r for r in _dump(path, "civic_object_stages", "object_id")}
    assert len(stages) == 4
    assert stages[planned["id"]][1:4] == ("planned", "2026-10-20", None)
    assert stages[progress["id"]][1:4] == ("construction", "2026-10-05", None)  # исходный срок
    assert stages[done["id"]][1] == "operating"
    assert stages[cancelled["id"]][1] is None
    assert all(r[7] == "migrated" for r in stages.values())
    hist = _dump(path, "civic_stage_history", "id")
    assert len(hist) == 4 and {h[4] for h in hist} == {"migrate"}

    obj = call(v2, "GET", f"/objects/{progress['id']}")["body"]["data"]["item"]
    # Перенесённый срок 25 окт — прогноз; сегодня 12 окт: отстаёт на 20 дней от исходного 5 окт.
    assert obj["forecast_end"] == "2026-10-25" and obj["delay_days"] == 20 and obj["late"] is True
    done_obj = call(v2, "GET", f"/objects/{done['id']}")["body"]["data"]["item"]
    assert done_obj["late"] is False and done_obj["delay_days"] == 9

    # Повторный запуск ничего не дублирует.
    make_service(path, clock)
    assert len(_dump(path, "civic_stage_history", "id")) == 4


def test_stage_history_is_append_only(staff, db_path):
    item = staff.create_object()
    staff.set_stage(item["id"], 0, stage="design")
    conn = sqlite3.connect(db_path)
    try:
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute("UPDATE civic_stage_history SET stage = 'operating'")
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute("DELETE FROM civic_stage_history")
    finally:
        conn.close()
