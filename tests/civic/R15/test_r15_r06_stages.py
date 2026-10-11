"""R15: R06 (предложения и этапы, ui/civic_store) — защита в глубину, честность «отстающих», геометрия, демо-голоса.

Находки S17–S21 (мелочи) нашёл ревьюер R06 сессии 10 окт; перепроверены на FINAL-кандидате R01 a2d90dd.
Через настоящий HTTP на 127.0.0.1 и временную базу; сотрудник входит как в интерфейсе (сессия R02 + CSRF).
"""

from __future__ import annotations

import json
from datetime import date, timedelta

import pytest

from r15_common import live_server, need_module, request, xfail

INSIDE = [71.35, 51.13]  # точка внутри Астаны (тот же район, что в тестах R06)


@pytest.fixture()
def srv(tmp_path):
    with live_server(tmp_path) as server:
        if not hasattr(server, "civic_v2"):
            pytest.skip("в этой сборке нет шлюза /api/civic/v2 (R01)")
        yield server


class Staff:
    """Сотрудник акимата: cookie сессии + X-CSRF-Token + свой Origin."""

    def __init__(self, srv):
        self.srv = srv
        self.origin = "http://127.0.0.1:%d" % srv.server_address[1]
        status, data = self.call("GET", "/api/civic/v2/modules", staff=False)
        modules = data.get("modules", {}) if status == 200 else {}
        for key in ("proposals.create", "objects.stage"):
            if (modules.get(key) or {}).get("status") != "ready":
                pytest.skip(f"маршрут {key} (R06) не подключён в этой сборке")
        store = srv.civic.service("store")
        store.accounts.create_user("r15-stages", "R15-Strong-Pass-2026", display_name="R15", role="editor")
        status, headers, raw = request(srv, "POST", "/api/civic/v1/session/login",
                                       {"username": "r15-stages", "password": "R15-Strong-Pass-2026"},
                                       headers={"Origin": self.origin})
        assert status == 200, raw
        self.cookie = headers.get("set-cookie", "").split(";")[0]
        self.token = json.loads(raw)["data"]["csrf_token"]

    def call(self, method, path, body=None, staff=True):
        headers = {"Origin": self.origin}
        if staff:
            headers.update({"Cookie": self.cookie, "X-CSRF-Token": self.token})
        status, _h, raw = request(self.srv, method, path, body, headers=headers)
        return status, json.loads(raw or b"{}")

    def create_object(self, publish=True):
        """Опубликованный объект v1 со сроком 6 дней назад — он в списке отстающих."""
        late = (date.today() - timedelta(days=6)).isoformat()
        body = {"kind": "roadworks", "title": "R15 ремонт прохода", "description": "Синтетическая запись R15.",
                "status": "planned", "geometry": {"type": "Point", "coordinates": INSIDE},
                "geometry_precision": "approximate",
                "schedule": {"planned_start": (date.today() - timedelta(days=30)).isoformat(),
                             "original_planned_end": late, "current_planned_end": late, "actual_end": None},
                "budget": {"amount_kzt": None, "basis": "unknown", "source_id": None},
                "responsible": {"organization": None, "public_contact": None},
                "evidence_type": "synthetic", "source_refs": [], "evidence_notes": "R15"}
        status, data = self.call("POST", "/api/civic/v1/staff/objects", body)
        assert status == 201, data
        item = data["data"]["item"]
        if publish:
            status, data = self.call("POST", "/api/civic/v1/staff/objects/%s/publish" % item["id"],
                                     {"expected_revision": item["revision"], "reason": "Публикация"})
            assert status == 200, data
            item = data["data"]["item"]
        return item, late

    def create_proposal(self, **over):
        body = {"kind": "square", "geometry": {"type": "Point", "coordinates": INSIDE}, "title_ru": "Сквер R15",
                "planned_year": 2027}
        body.update(over)
        return self.call("POST", "/api/civic/v2/proposals", body)

    def put_stage(self, object_id, body):
        return self.call("PUT", "/api/civic/v2/objects/%s/stage" % object_id, body)


def _context(staff, *, same_origin):
    """Как шлюз R01 передаёт запрос в модуль: cookie есть, X-CSRF-Token нет."""
    return {"headers": {"cookie": staff.cookie, "host": staff.origin[len("http://"):]},
            "cookies": dict([staff.cookie.split("=", 1)]), "client_ip": "127.0.0.1",
            "host_allowed": True, "is_same_origin": same_origin, "is_https": False}


# --- 2. S17: функции модуля R06 сами проверяют CSRF (защита в глубину) --------------------------------

@xfail("S17")
def test_r06_module_functions_refuse_cookie_without_csrf(srv):
    """Шлюз R01 проверяет CSRF только для маршрутов с пометкой staff; функции R06 верят вызывающему.

    Одна забытая пометка в таблице маршрутов — и одобрение проекта / этап объекта меняются по одной cookie.
    """
    staff = Staff(srv)
    v2 = need_module("ui.civic_store.v2")
    status, created = staff.create_proposal()
    assert status == 201, created
    with pytest.raises(Exception) as exc:
        v2.decide_proposal(created["item"]["id"], "approve", {}, context=_context(staff, same_origin=None))
    assert getattr(exc.value, "status", None) in (401, 403), exc.value
    status, other = staff.create_proposal(title_ru="Сквер R15 второй")
    assert status == 201, other
    with pytest.raises(Exception) as exc:
        v2.vote_proposal(other["item"]["id"], 1, "device-r15-s17-000001",
                         context={"host_allowed": False, "is_same_origin": False, "client_ip": "127.0.0.1"})
    assert getattr(exc.value, "status", None) == 403, exc.value


# --- 5. S18: опубликованный срок нельзя молча отодвинуть — объект уходит из «отстающих» -----------------

@xfail("S18")
def test_r06_published_delay_is_not_hidden_without_reason(srv):
    staff = Staff(srv)
    v2 = need_module("ui.civic_store.v2")
    item, late = staff.create_object()
    status, data = staff.put_stage(item["id"], {"expected_revision": 0, "stage": "construction", "planned_end": late})
    assert status == 200, data
    assert any(o["id"] == item["id"] for o in v2.lagging_objects()["late"]), "объект с прошлым сроком не в отстающих"
    status, data = staff.put_stage(item["id"], {"expected_revision": 1, "stage": "construction",
                                                "planned_end": (date.today() + timedelta(days=240)).isoformat()})
    still_late = any(o["id"] == item["id"] for o in v2.lagging_objects()["late"])
    assert status == 422 or still_late, "срок отодвинут без причины, объект исчез из отстающих «Картины дня»"


@xfail("S18")
def test_r06_published_stage_does_not_go_back_without_reason(srv):
    staff = Staff(srv)
    item, late = staff.create_object()
    status, data = staff.put_stage(item["id"], {"expected_revision": 0, "stage": "operating", "planned_end": late})
    assert status == 200, data
    status, data = staff.put_stage(item["id"], {"expected_revision": 1, "stage": "planned", "planned_end": late})
    assert status == 422, "этап «работает» -> «план» без причины"


def test_r06_stage_change_with_reason_is_allowed(srv):
    """Обратная сторона S18: с причиной перенос срока проходит (работа редактора не блокируется)."""
    staff = Staff(srv)
    item, late = staff.create_object()
    assert staff.put_stage(item["id"], {"expected_revision": 0, "stage": "construction", "planned_end": late})[0] == 200
    status, data = staff.put_stage(item["id"], {"expected_revision": 1, "stage": "construction",
                                                "planned_end": (date.today() + timedelta(days=60)).isoformat(),
                                                "reason": "Подрядчик сменился, срок по допсоглашению"})
    assert status == 200, data


# --- 5. S19: геометрия проекта — внутри Астаны и в разумных размерах ------------------------------------

@xfail("S19")
@pytest.mark.parametrize("geometry", [
    {"type": "Point", "coordinates": [72.08, 51.58]},                                   # ~67 км от центра
    # 1200 вершин (тело ~17 КБ — меньше предела шлюза R01 64 КБ; 5000 коротких точек тоже проходят).
    {"type": "Polygon", "coordinates": [[[71.4, 51.1]] * 1199 + [[71.4, 51.1]]]},
], ids=["outside_city", "1200_vertices"])
def test_r06_proposal_geometry_outside_city_or_huge_is_refused(srv, geometry):
    staff = Staff(srv)
    status, data = staff.create_proposal(geometry=geometry)
    assert status == 422, (status, str(data)[:200])


def test_r06_proposal_inside_city_is_accepted(srv):
    staff = Staff(srv)
    status, data = staff.create_proposal()
    assert status == 201, data


# --- 3. S20: демо-голоса не перевернуть по id из исходников ---------------------------------------------

@xfail("S20")
def test_r06_demo_seed_votes_cannot_be_flipped(srv):
    demo = need_module("ui.civic_store.demo_r14")
    staff = Staff(srv)
    report = demo.seed_r14_demo(srv.civic.service("store"))
    seeded = next((p for p in report["proposals"] if p.get("action") == "create" and p.get("votes_up")), None)
    if seeded is None:
        pytest.skip("демо R06 не создало предложений с голосами")
    status, data = staff.call("POST", "/api/civic/v2/proposals/%s/vote" % seeded["id"],
                              {"value": -1, "device_id": "demo-seed-0-00000-device"}, staff=False)
    assert status == 200, data
    # previous == 1: это был голос «за» демо-устройства, и он стал «против».
    assert data.get("previous") != 1, "демо-голос перевёрнут по id устройства из исходников R06"


# --- 4. S21: правки этапа черновика не становятся публичной историей -----------------------------------

@xfail("S21")
def test_r06_draft_stage_edits_are_not_published(srv):
    staff = Staff(srv)
    v2 = need_module("ui.civic_store.v2")
    item, _late = staff.create_object(publish=False)
    for rev, plan in enumerate(("2026-09-01", "2026-11-15")):
        status, data = staff.put_stage(item["id"], {"expected_revision": rev, "stage": "design", "planned_end": plan,
                                                    "reason": "внутренняя цель отдела"})
        assert status == 200, data
    status, data = staff.call("POST", "/api/civic/v1/staff/objects/%s/publish" % item["id"],
                              {"expected_revision": item["revision"], "reason": "Публикация"})
    assert status == 200, data
    public = v2.get_object(item["id"])["stage_history"]
    assert "2026-09-01" not in [h["planned_end"] for h in public], public
