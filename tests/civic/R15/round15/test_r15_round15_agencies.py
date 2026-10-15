"""R15 раунд 15 · R17 «Штаб ведомств» и кризисный штаб (ui.civic_agencies) — THREATS_R15 §6.

Сервис проверяется напрямую (make_service(db).handle — так его вызывает шлюз R01, kind="service"):
- публичная часть кризиса и лента жителей без внутренних задач, внутренних обновлений и логинов (T-R17-01, -07);
- запись штаба — только сотрудник с CSRF и своим Origin (T-R17-02, -03); табло и журналы — только сотрудник (T-R17-06);
- задача ищется внутри своего кризиса (T-R17-04); службы — только из справочника (T-R17-05);
- зона без «полигонов от руки» и с пределом целей (T-R17-08); личные данные в публичном тексте — отказ (T-R17-09);
- закрытый кризис — только чтение (T-R17-12).
Нет ui.civic_agencies в сборке — NOT_RUN.
"""

from __future__ import annotations

import pytest

from r15_common import xfail
from r15_round15 import CSRF, DEVICES, MARK, PII, STAFF_LOGIN, Svc, XSS, context, device_needles, dump, leaks, module

ZONE = {"kind": "district", "district": "nura"}


@pytest.fixture()
def hq(tmp_path, monkeypatch):
    monkeypatch.delenv("CIVIC_DEMO", raising=False)
    return Svc(module("ui.civic_agencies", "R17"), tmp_path / "civic.sqlite3", demo=False)


def _incident(hq, kind="blizzard", zone=ZONE):
    status, body = hq.staff("POST", "/incidents", {
        "kind": kind, "zone": zone,
        "tasks": [{"service": "street_cleaning", "text_ru": f"{MARK} внутренняя задача штаба",
                   "text_kk": f"{MARK} штабтың ішкі тапсырмасы"}]})
    assert status == 201, (status, body)
    return body["incident"]


def _public_reads(hq, incident_id):
    """Всё, что видит житель: список, карточка, лента обновлений зоны (по району и по устройству)."""
    out = [hq.anon("GET", "/incidents"), hq.anon("GET", "/incidents/" + incident_id),
           hq.anon("GET", "/incidents", query="status=active&district=nura"),
           hq.resident("GET", "/incidents/updates", query="district=nura"),
           hq.resident("GET", "/incidents/" + incident_id, device=DEVICES[2])]
    for status, _body in out:
        assert status == 200, out
    return [body for _status, body in out]


def test_public_incident_hides_internal_tasks_and_updates(hq):
    """T-R17-01: задачи служб и обновления public:false не видны жителю нигде; публичное обновление — видно."""
    incident = _incident(hq)
    iid = incident["id"]
    status, body = hq.staff("POST", f"/incidents/{iid}/update",
                            {"text_ru": f"{MARK}-внутреннее: ждём технику", "text_kk": f"{MARK}-ішкі", "public": False})
    assert status == 200, body
    status, body = hq.staff("POST", f"/incidents/{iid}/update",
                            {"text_ru": "Службы расчищают улицы района", "text_kk": "Қызметтер көшелерді тазартып жатыр"})
    assert status == 200, body
    reads = _public_reads(hq, iid)
    assert not leaks(reads, [MARK, STAFF_LOGIN, "moderation", "journal", "by_role"]), dump(reads)[:600]
    assert "Службы расчищают улицы района" in dump(reads[1])
    # Сотрудник видит задачи и внутреннее обновление (иначе тест выше ничего не доказывает).
    status, staff_view = hq.staff("GET", "/incidents/" + iid)
    assert status == 200 and MARK in dump(staff_view)


@pytest.mark.parametrize("who", ["anon", "resident", "no_csrf", "bad_csrf", "cross_origin", "resident_role"])
def test_crisis_writes_need_staff_with_csrf(hq, who):
    """T-R17-02, -03: создать, добавить задачу/обновление, закрыть — только сотрудник с CSRF со своего сайта."""
    incident = _incident(hq)
    iid = incident["id"]
    task_id = incident["tasks"][0]["id"]
    resident_principal = None
    if who == "resident_role":
        from r15_round15 import staff_principal
        resident_principal = staff_principal(role="resident")
    calls = [("/incidents", {"kind": "flood", "zone": {"kind": "district", "district": "esil"}}),
             (f"/incidents/{iid}/task", {"task_id": task_id, "status": "done"}),
             (f"/incidents/{iid}/task", {"service": "road", "text_ru": "Подменная задача", "text_kk": "Жалған"}),
             (f"/incidents/{iid}/update", {"text_ru": "Эвакуация! Звоните", "text_kk": "Эвакуация!", "public": True}),
             (f"/incidents/{iid}/close", {"result_ru": "Закрыто посторонним", "result_kk": "Жабылды"})]
    for path, body in calls:
        if who == "anon":
            status, reply = hq.anon("POST", path, body)
        elif who == "resident":
            status, reply = hq.resident("POST", path, body, device=DEVICES[3])
        elif who == "no_csrf":
            status, reply = hq.staff("POST", path, body, csrf=None)
        elif who == "bad_csrf":
            status, reply = hq.staff("POST", path, body, csrf="x" * len(CSRF))
        elif who == "cross_origin":
            status, reply = hq.staff("POST", path, body, origin=False)
        else:
            status, reply = hq.staff("POST", path, body, principal=resident_principal)
        assert status in (401, 403), (who, path, status, reply)
    status, view = hq.staff("GET", "/incidents/" + iid)
    assert status == 200
    view = view["incident"]
    assert view["status"] == "active" and view["tasks"][0]["status"] == "todo" and len(view["tasks"]) == 1
    assert not [u for u in view["updates"] if "Эвакуация" in (u.get("text_ru") or "")]
    status, listing = hq.staff("GET", "/incidents")
    assert len(listing["items"]) == 1, "посторонний создал кризис"


@pytest.mark.parametrize("path", ["/agencies/board", "/agencies/joint", "/agencies/handoffs",
                                  "/agencies/board?service=water"])
def test_board_and_journals_are_staff_only(hq, path):
    """T-R17-06: табло, совместные и журнал передач — сотрудник; житель и аноним — 401/403."""
    route, _sep, query = path.partition("?")
    for status, body in (hq.anon("GET", route, query=query), hq.resident("GET", route, query=query)):
        assert status in (401, 403), (path, status, body)
    status, body = hq.staff("GET", route, query=query, csrf=None)  # чтение: сессии достаточно
    assert status == 200, body
    assert STAFF_LOGIN not in dump(body)


def test_staff_journal_names_role_not_login(hq):
    """T-R17-07: журнал штаба и вид сотрудника — роль, а не логин или имя сотрудника (без «рейтинга людей»)."""
    incident = _incident(hq)
    iid = incident["id"]
    hq.staff("POST", f"/incidents/{iid}/task", {"task_id": incident["tasks"][0]["id"], "status": "doing"})
    hq.staff("POST", f"/incidents/{iid}/update", {"text_ru": "Работаем", "text_kk": "Жұмыс істеп жатырмыз"})
    status, view = hq.staff("GET", "/incidents/" + iid)
    assert status == 200 and view["incident"].get("journal"), view
    assert STAFF_LOGIN not in dump(view) and "R15 Тест" not in dump(view)


def test_task_of_other_incident_cannot_be_changed(hq):
    """T-R17-04: задача кризиса A через адрес кризиса B — 404, задача A не меняется."""
    a = _incident(hq)
    b = _incident(hq, kind="flood", zone={"kind": "district", "district": "esil"})
    task_a = a["tasks"][0]["id"]
    status, body = hq.staff("POST", f"/incidents/{b['id']}/task", {"task_id": task_a, "status": "done"})
    assert status in (404, 422), (status, body)
    status, view = hq.staff("GET", "/incidents/" + a["id"])
    assert view["incident"]["tasks"][0]["status"] == "todo"


@pytest.mark.parametrize("service", [XSS, "kgb", "", None, 7])
def test_task_service_must_come_from_directory(hq, service):
    """T-R17-05: служба задачи — только id CONTRACT §3 (в чипах штаба id выводится как текст, но не должен быть HTML)."""
    incident = _incident(hq)
    status, body = hq.staff("POST", f"/incidents/{incident['id']}/task",
                            {"service": service, "text_ru": "Задача", "text_kk": "Тапсырма"})
    assert status in (400, 422), (status, body)
    status, body = hq.staff("POST", "/incidents", {"kind": "heat_outage", "zone": ZONE,
                                                   "tasks": [{"service": service, "text_ru": "Задача"}]})
    assert status in (400, 422), (status, body)


@xfail("S43")
@pytest.mark.parametrize("field", ["task.service", "tasks.service", "kind"])
def test_wrong_json_type_is_422_not_500(hq, field):
    """S43: список вместо строки в service/kind -> TypeError (unhashable) -> шлюз отвечает 500 вместо 422."""
    incident = _incident(hq)
    if field == "task.service":
        path, body = f"/incidents/{incident['id']}/task", {"service": ["road"], "text_ru": "Задача"}
    elif field == "tasks.service":
        path, body = "/incidents", {"kind": "flood", "zone": ZONE, "tasks": [{"service": ["road"], "text_ru": "Задача"}]}
    else:
        path, body = "/incidents", {"kind": ["blizzard"], "zone": ZONE}
    try:
        status, reply = hq.staff("POST", path, body)
    except TypeError as exc:  # шлюз R01 превратит это в 500 internal
        pytest.fail(f"{field}: {exc!r} -> 500")
    assert status in (400, 422), (status, reply)


@pytest.mark.parametrize("zone", [
    {"kind": "polygon", "geometry": {"type": "Polygon", "coordinates": [[[71.4, 51.1], [71.5, 51.1], [71.4, 51.2],
                                                                        [71.4, 51.1]]]}},
    {"kind": "district", "district": "nura", "geometry": {"type": "Point", "coordinates": [71.4, 51.1]}},
    {"kind": "targets", "targets": ["yard-1026285032"] * 3 + [f"yard-{i}" for i in range(60)]},
    {"kind": "targets", "targets": ["yard-999999999999"]},
    {"kind": "targets", "targets": [XSS]},
    {"kind": "district", "district": "moscow"},
])
def test_zone_is_district_or_map_targets(hq, zone):
    """T-R17-08: зона — район или цели карты R12 (≤ 50), без контура «от руки» и без выдуманных целей."""
    status, body = hq.staff("POST", "/incidents", {"kind": "water_outage", "zone": zone})
    assert status in (400, 422), (status, body)


@pytest.mark.parametrize("kind", sorted(PII))
def test_public_update_with_personal_data_is_refused(hq, kind):
    """T-R17-09: публичное обновление/итог с телефоном, ИИН, e-mail, картой не публикуются (видят все жители зоны)."""
    text, needles = PII[kind]
    incident = _incident(hq)
    iid = incident["id"]
    hq.staff("POST", f"/incidents/{iid}/update", {"text_ru": text, "text_kk": text})
    hq.staff("POST", f"/incidents/{iid}/close", {"result_ru": text, "result_kk": text})
    reads = _public_reads(hq, iid)
    assert not leaks(reads, needles), (kind, dump(reads)[:400])


def test_closed_incident_is_read_only(hq):
    """T-R17-12: после закрытия — 409 на задачи, обновления и повторное закрытие."""
    incident = _incident(hq)
    iid = incident["id"]
    status, body = hq.staff("POST", f"/incidents/{iid}/close", {"result_ru": "Улицы расчищены",
                                                               "result_kk": "Көшелер тазартылды"})
    assert status == 200, body
    for path, body in ((f"/incidents/{iid}/update", {"text_ru": "Ещё", "text_kk": "Тағы"}),
                       (f"/incidents/{iid}/task", {"service": "road", "text_ru": "Ещё задача"}),
                       (f"/incidents/{iid}/close", {"result_ru": "Снова", "result_kk": "Қайта"})):
        status, reply = hq.staff("POST", path, body)
        assert status == 409, (path, status, reply)


def test_resident_feed_is_bounded_and_without_devices(hq):
    """T-R17-11, P1/P6: лента жителя ограничена, без id устройств; мусор в since/yard/устройстве -> 400."""
    incident = _incident(hq)
    for i in range(35):
        hq.staff("POST", f"/incidents/{incident['id']}/update", {"text_ru": f"Обновление номер {i}",
                                                                "text_kk": f"Жаңарту {i}"})
    status, body = hq.resident("GET", "/incidents/updates", query="district=nura", device=DEVICES[4])
    assert status == 200 and len(body["items"]) <= 50, len(body.get("items", []))
    assert not leaks(body, device_needles(DEVICES[:5]))
    for query in ("since=вчера", "yard=" + XSS, "district=" + XSS):
        status, _b = hq.resident("GET", "/incidents/updates", query=query)
        assert status == 400, query
    status, _b = hq.call("GET", "/incidents/updates", query="district=nura",
                         ctx=context(device="bad\ndevice-id-r15"))
    assert status == 400


def test_unknown_or_malformed_incident_id_is_404(hq):
    """P7: неизвестный и кривой id — одинаковый 404, без трассировки."""
    for iid in ("inc-doesnotexist00", "inc-" + "a" * 60, "../../etc/passwd", XSS):
        status, body = hq.anon("GET", "/incidents/" + iid)
        assert status == 404, (iid, status, body)
        assert "Traceback" not in dump(body)
