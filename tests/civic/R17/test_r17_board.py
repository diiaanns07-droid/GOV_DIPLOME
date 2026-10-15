"""R17 · расчёт табло служб, совместных обращений и журнала передач (ui/civic_agencies/metrics.py).

Крайние случаи из prompt R17 п. 6: нет данных, одна служба, передачи по кругу; плюс дубли, район, срок не
обнуляется передачей, медиана в рабочих днях, доля «проверено жителями» без исправленных — null, а не 0 %.
"""

from datetime import datetime, timedelta

import pytest

from ui.civic_agencies import metrics as calc
from ui.civic_agencies import fixture, profiles

NOW = datetime(2026, 10, 15, 12, 0, tzinfo=calc.ASTANA)   # четверг


def rec(n, *, service="water", status="new", created_days=1.0, due_days=2.0, history=None, district="nura",
        services=None, handoffs=None, resolution=None, duplicate_of=None, demo=True, target=None):
    created = NOW - timedelta(days=created_days)
    record = {"id": f"c-test{n:04d}", "code": f"T-{n}", "created_at": calc.iso(created), "category": "utilities",
              "subtopic": "no_water", "district": district, "status": status, "service": service,
              "due_at": calc.iso(created + timedelta(days=due_days)),
              "status_history": history if history is not None else [{"at": calc.iso(created), "status": "new"}],
              "target": target or {"kind": "area", "id": f"yard-{n}"}, "demo": demo}
    if services is not None:
        record["services"] = services
    if handoffs is not None:
        record["handoffs"] = handoffs
    if resolution is not None:
        record["resolution"] = resolution
    if duplicate_of:
        record["duplicate_of"] = duplicate_of
    return record


def row(body, sid):
    return next(r for r in body["services"] if r["service"] == sid)


def test_no_data_lists_all_20_services_with_zeros():
    body = calc.board([], NOW)
    assert [r["service"] for r in body["services"]] == list(profiles.SERVICE_IDS)
    assert len(body["services"]) == 20
    assert body["empty"] is True and body["demo"] is False
    assert all(r["open"] == 0 and r["median_answer_days"] is None and r["verified_share"] is None
               for r in body["services"])
    assert body["totals"]["open"] == 0 and body["totals"]["verified_share"] is None


def test_one_service_open_overdue_and_deadline_bar_sums_to_open():
    records = [
        rec(1, created_days=5, due_days=1),                     # new, срок прошёл -> просрочено
        rec(2, created_days=0.2, due_days=3),                   # new, срок впереди
        rec(3, status="in_progress", created_days=3, due_days=1,
            history=[{"at": calc.iso(NOW - timedelta(days=3)), "status": "new"},
                     {"at": calc.iso(NOW - timedelta(days=2)), "status": "in_progress"}]),
    ]
    body = calc.board(records, NOW)
    water = row(body, "water")
    assert water["open"] == 3 and water["overdue"] == 1
    assert sum(water["deadline"].values()) == water["open"]
    assert water["deadline"]["answered"] == 1
    assert body["totals"]["open"] == 3 and body["totals"]["overdue"] == 1
    others = [r for r in body["services"] if r["service"] != "water"]
    assert all(r["open"] == 0 for r in others)


def test_median_answer_in_working_days_and_only_lead():
    # Подано в пятницу 10:00, ответ в понедельник — 1 рабочий день (выходные не считаются).
    friday = datetime(2026, 10, 9, 10, 0, tzinfo=calc.ASTANA)
    monday = datetime(2026, 10, 12, 9, 0, tzinfo=calc.ASTANA)
    record = rec(1, status="accepted", created_days=(NOW - friday).total_seconds() / 86400,
                 history=[{"at": calc.iso(friday), "status": "new"}, {"at": calc.iso(monday), "status": "accepted"}],
                 services=[{"service": "water", "role": "lead", "status": "in_progress"},
                           {"service": "road", "role": "partner", "status": "new"}])
    body = calc.board([record], NOW)
    assert row(body, "water")["median_answer_days"] == 1.0 and row(body, "water")["answered"] == 1
    assert row(body, "road")["median_answer_days"] is None      # участвующая служба — без медианы ответа жителю
    assert row(body, "road")["open"] == 1 and row(body, "road")["joint"] == 1


def test_verified_share_and_returned():
    fixed_hist = [{"at": calc.iso(NOW - timedelta(days=4)), "status": "new"},
                  {"at": calc.iso(NOW - timedelta(days=3)), "status": "fixed"}]
    records = [
        rec(1, status="fixed", created_days=4, history=fixed_hist, resolution={"state": "verified"}),
        rec(2, status="fixed", created_days=4, history=fixed_hist, resolution={"state": "reported"}),
        rec(3, status="in_progress", created_days=4, history=fixed_hist,
            resolution={"state": "reopened", "reopen_count": 1}),
    ]
    water = row(calc.board(records, NOW), "water")
    assert water["fixed"] == 2 and water["verified"] == 1 and water["verified_share"] == 0.5
    assert water["returned"] == 1 and water["open"] == 1


def test_duplicates_and_other_districts_are_not_counted():
    records = [rec(1), rec(2, duplicate_of="c-test0001"), rec(3, district="esil")]
    body = calc.board(records, NOW, district="nura")
    assert row(body, "water")["open"] == 1
    assert calc.board(records, NOW)["totals"]["open"] == 2


def test_period_limits_flow_metrics_but_not_open():
    old = rec(1, created_days=60, due_days=1)
    body = calc.board([old], NOW, days=30)
    water = row(body, "water")
    assert water["open"] == 1 and water["overdue"] == 1     # открытое старое обращение видно всегда
    assert water["received"] == 0                           # но в поток за 30 дней не входит


def test_handoffs_in_circle_are_flagged():
    t0 = NOW - timedelta(days=2)
    handoffs = [{"at": calc.iso(t0), "from": "road", "to": "water", "reason": "Сначала труба", "by_role": "operator"},
                {"at": calc.iso(t0 + timedelta(hours=5)), "from": "water", "to": "road", "reason": "Не наш участок",
                 "by_role": "operator"},
                {"at": calc.iso(t0 + timedelta(hours=9)), "from": "road", "to": "water", "reason": "Сначала труба",
                 "by_role": "editor"}]
    record = rec(1, created_days=3, handoffs=handoffs,
                 services=[{"service": "water", "role": "lead", "status": "in_progress"},
                           {"service": "road", "role": "partner", "status": "new"}])
    assert calc.loop_flags(calc.handoffs_of(record)) == [False, True, True]
    body = calc.board([record], NOW)
    assert row(body, "water")["handoffs_in"] == 2 and row(body, "water")["handoffs_out"] == 1
    assert row(body, "road")["handoffs_out"] == 2 and body["totals"]["loops"] == 1
    log = calc.handoff_log([record], NOW)
    assert log["total"] == 3 and log["loops"] == 1
    assert log["items"][0]["at"] > log["items"][-1]["at"]                 # новые сверху
    assert all(e["due_at"] == record["due_at"] for e in log["items"])      # срок тот же — передача его не обнуляет
    assert all("by" not in e and e["by_role"] in ("operator", "editor") for e in log["items"])  # только роль
    assert log["pairs"][0] == {"from": "road", "to": "water", "count": 2}


def test_joint_lists_only_multi_service_without_texts():
    single = rec(1)
    single["text"] = "Личный текст жителя"
    joint = rec(2, services=[{"service": "water", "role": "lead", "status": "done"},
                             {"service": "road", "role": "partner", "status": "in_progress"}])
    joint["text"] = "Личный текст жителя"
    body = calc.joint([single, joint], NOW)
    assert body["counts"] == {"total": 1, "open": 1, "overdue": 0}
    item = body["items"][0]
    assert item["lead"] == "water" and [p["service"] for p in item["parts"]] == ["water", "road"]
    assert "text" not in item and "device_hash" not in item


def test_unknown_service_ids_are_ignored():
    record = rec(1, services=[{"service": "mars_service", "role": "lead", "status": "new"},
                              {"service": "water", "role": "partner", "status": "new"}])
    parts = calc.parts_of(record)
    assert [p["service"] for p in parts] == ["water"] and parts[0]["role"] == "lead"


def test_lagging_top3_by_overdue_services_only():
    records = [rec(i, service=s, created_days=5, due_days=1) for i, s in
               enumerate(["water", "water", "road", "gas", "gas", "gas", "power"], 1)]
    top = calc.lagging(calc.board(records, NOW), 3)
    assert [t["service"] for t in top] == ["gas", "water", "power"]   # при равенстве — по id, устойчиво
    assert set(top[0]) == {"service", "overdue", "open"}       # только службы, без людей


def test_fixture_is_deterministic_and_v21():
    first, second = fixture.demo_records(NOW), fixture.demo_records(NOW)
    assert first == second
    assert all(r["demo"] is True and r["service"] in profiles.PROFILES for r in first)
    scene = next(r for r in first if r["id"] == fixture.SCENE_COMPLAINT)
    assert [p["service"] for p in scene["services"]] == ["water", "road"]
    assert scene["handoffs"][0]["from"] == "road" and scene["handoffs"][0]["to"] == "water"
    body = calc.board(first, NOW)
    served = {r["service"] for r in body["services"] if r["received"] or r["open"]}
    assert len(served) >= 18          # почти все службы с данными — табло не пустое на показе
    assert body["totals"]["joint"] >= 3 and body["totals"]["loops"] >= 1


@pytest.mark.parametrize("district", ["nura", "esil", None])
def test_totals_open_equals_distinct_complaints(district):
    records = fixture.demo_records(NOW)
    body = calc.board(records, NOW, district=district)
    distinct = sum(1 for r in calc._usable(records, district)
                   if any(p["status"] not in calc.PART_CLOSED for p in calc.parts_of(r)))
    assert body["totals"]["open"] == distinct
    assert body["totals"]["open"] <= sum(r["open"] for r in body["services"])   # совместные — в каждой службе
