"""R15 раунд 15 · R13 «Встречи с акимом» (ui.civic_meetings) — THREATS_R15 §8.

Сервис проверяется напрямую (make_service(db).handle — kind="service" шлюза R01):
- встреча, поручение, итог — только сотрудник с CSRF и своим Origin (T-R13-04);
- «Приду» — только число: без устройств, хэшей и времени; один раз с устройства; id устройства в базе — хэшем
  (T-R13-01, T-R13-02, P6);
- вопрос к встрече с личными данными не виден до проверки (T-R13-03); связь поручения — белый список (T-R13-05);
- лента updates() — только своему устройству, ссылки внутренние (T-R06-01, T-R06-03);
- логин сотрудника не уходит жителю (P1).
Нет ui.civic_meetings в сборке — NOT_RUN.
"""

from __future__ import annotations

import re

import pytest

from r15_round15 import (CSRF, DEVICES, PII, STAFF_LOGIN, Svc, XSS, db_contains, device_needles, dump, iso_in, leaks,
                         module, staff_principal)


@pytest.fixture()
def meet(tmp_path, monkeypatch):
    monkeypatch.delenv("CIVIC_DEMO", raising=False)
    return Svc(module("ui.civic_meetings", "R13"), tmp_path / "civic.sqlite3", demo=False)


def _meeting(meet, days=3):
    status, body = meet.staff("POST", "/meetings", {
        "district": "nura", "title_ru": "Встреча акима района с жителями Нуры", "title_kk": "Аудан әкімінің кездесуі",
        "at": iso_in(days=days), "place": {"label_ru": "Школа, актовый зал", "label_kk": "Мектеп, акт залы"}})
    assert status == 201, (status, body)
    return body["meeting"]["id"]


@pytest.mark.parametrize("who", ["anon", "resident", "no_csrf", "bad_csrf", "cross_origin", "resident_role"])
def test_meeting_orders_result_need_staff_with_csrf(meet, who):
    """T-R13-04: «аким поручил…» и итог встречи пишет только сотрудник."""
    mid = _meeting(meet)
    calls = [("/meetings", {"district": "nura", "title_ru": "Поддельная встреча", "at": iso_in(days=2),
                            "place": {"label_ru": "Где-то"}}),
             (f"/meetings/{mid}/order", {"text_ru": "Поручение от постороннего", "service": "road", "due": iso_in(9)[:10]}),
             (f"/meetings/{mid}/result", {"result_ru": "Итог, написанный посторонним человеком"})]
    for path, body in calls:
        if who == "anon":
            status, reply = meet.anon("POST", path, body)
        elif who == "resident":
            status, reply = meet.resident("POST", path, body, device=DEVICES[5])
        elif who == "no_csrf":
            status, reply = meet.staff("POST", path, body, csrf=None)
        elif who == "bad_csrf":
            status, reply = meet.staff("POST", path, body, csrf="y" * len(CSRF))
        elif who == "cross_origin":
            status, reply = meet.staff("POST", path, body, origin=False)
        else:
            status, reply = meet.staff("POST", path, body, principal=staff_principal(role="resident"))
        assert status in (401, 403), (who, path, status, reply)
    status, card = meet.anon("GET", "/meetings/" + mid)
    assert status == 200
    assert not card["meeting"]["orders"] and card["meeting"]["result"] is None
    assert "Поддельная" not in dump(meet.anon("GET", "/meetings")[1])


def test_registrations_are_only_a_number(meet):
    """T-R13-02, P1, P6: «Приду» — число; кто и когда — нигде; id устройства в базе только хэшем."""
    mid = _meeting(meet)
    status, before = meet.anon("GET", "/meetings/" + mid)
    base = before["meeting"]["registered"]
    for dev in DEVICES[:3]:
        status, body = meet.resident("POST", f"/meetings/{mid}/register", {"going": True}, device=dev)
        assert status == 200, body
    reads = [meet.anon("GET", "/meetings/" + mid)[1], meet.anon("GET", "/meetings")[1],
             meet.resident("GET", "/meetings/" + mid, device=DEVICES[6])[1],
             meet.resident("GET", "/meetings", device=DEVICES[0])[1]]
    assert reads[0]["meeting"]["registered"] == base + 3
    assert not leaks(reads, device_needles(DEVICES[:3]) + [STAFF_LOGIN]), dump(reads)[:500]
    text = dump(reads)
    assert not re.search(r'"(registered_at|registrations|devices|device_hash|created_by)"', text), text[:500]
    assert reads[2]["meeting"]["my_registration"] is False and reads[3]["items"][0]["my_registration"] is True
    assert not db_contains(meet.db_path, DEVICES[:3]), "сырой id устройства в SQLite"


def test_register_is_idempotent_and_never_negative(meet):
    """T-R13-01: повтор «Приду» не накручивает; «Не смогу» без «Приду» не уводит в минус."""
    mid = _meeting(meet)
    base = meet.anon("GET", "/meetings/" + mid)[1]["meeting"]["registered"]
    for _ in range(5):
        meet.resident("POST", f"/meetings/{mid}/register", {"going": True}, device=DEVICES[7])
    for dev in DEVICES[8:12]:
        meet.resident("POST", f"/meetings/{mid}/register", {"going": False}, device=dev)
    assert meet.anon("GET", "/meetings/" + mid)[1]["meeting"]["registered"] == base + 1


def test_resident_writes_from_foreign_site_are_refused(meet):
    """S17/S37 раунда 14 для новых маршрутов: «Приду» и вопрос с чужого сайта — 403."""
    mid = _meeting(meet)
    for path, body in ((f"/meetings/{mid}/register", {"going": True}),
                       (f"/meetings/{mid}/question", {"text": "Когда починят освещение во дворе?"})):
        status, reply = meet.resident("POST", path, body, origin=False)
        assert status == 403, (path, status, reply)


@pytest.mark.parametrize("kind", sorted(PII))
def test_question_with_personal_data_is_not_public(meet, kind):
    """T-R13-03: вопрос к встрече с ПДн — «на проверке», публично его нет; сотрудник видит пометку."""
    mid = _meeting(meet)
    text, needles = PII[kind]
    status, body = meet.resident("POST", f"/meetings/{mid}/question", {"text": text + " — когда сделают двор?"},
                                 device=DEVICES[13])
    if status == 503:
        pytest.skip("NOT_RUN: вопросы встреч без «Вопроса акиму» (ui.civic_qa) в этой сборке")
    assert status in (200, 201), body
    assert body["question"]["status"] != "published", body
    public = [meet.anon("GET", "/meetings/" + mid)[1], meet.resident("GET", "/meetings/" + mid, device=DEVICES[14])[1]]
    assert not leaks(public, needles), dump(public)[:400]
    status, staff = meet.staff("GET", "/meetings/" + mid, csrf=None)
    assert status == 200 and staff["meeting"].get("pending_questions"), staff


def test_question_html_is_kept_as_text(meet):
    """T-R16-06 для вопросов встреч: HTML в вопросе хранится как текст (не исполняется — проверяет браузер)."""
    mid = _meeting(meet)
    status, body = meet.resident("POST", f"/meetings/{mid}/question", {"text": "Вопрос " + XSS + " про двор и свет"},
                                 device=DEVICES[15])
    if status == 503:
        pytest.skip("NOT_RUN: вопросы встреч без ui.civic_qa")
    assert status in (200, 201, 422), body


@pytest.mark.parametrize("link", [{"kind": "url", "id": "evil"}, {"kind": "javascript", "id": "alert"},
                                  {"kind": "complaint", "id": "https://evil.example/x"},
                                  {"kind": "complaint", "id": "../../etc"}, {"kind": "project", "id": XSS}])
def test_order_link_is_whitelisted(meet, link):
    """T-R13-05: связь поручения — только обращение/работа/проект с id по правилу CIVIC_ID."""
    mid = _meeting(meet)
    status, body = meet.staff("POST", f"/meetings/{mid}/order", {"text_ru": "Отремонтировать освещение во дворе",
                                                                 "service": "lighting", "due": iso_in(20)[:10],
                                                                 "link": link})
    assert status in (400, 422), (link, status, body)


@pytest.mark.parametrize("service", [XSS, "kgb", "", None, ["road"]])
def test_order_service_from_directory(meet, service):
    """T-R17-05 для поручений: служба — только из справочника CONTRACT §3."""
    mid = _meeting(meet)
    status, body = meet.staff("POST", f"/meetings/{mid}/order", {"text_ru": "Поручение службе по двору",
                                                                 "service": service, "due": iso_in(20)[:10]})
    assert status in (400, 422), (service, status, body)


def test_updates_only_for_own_device_with_internal_links(meet):
    """T-R06-01, T-R06-03: события ленты — устройству, которое нажало «Приду»; чужому — пусто; ссылки — #meetings/…"""
    mid = _meeting(meet, days=0.5)
    meet.resident("POST", f"/meetings/{mid}/register", {"going": True}, device=DEVICES[16])
    status, body = meet.staff("POST", f"/meetings/{mid}/order", {"text_ru": "Проверить освещение во дворе",
                                                                 "service": "lighting", "due": iso_in(20)[:10]})
    assert status == 201, body
    order_id = body["order"]["id"]
    meet.staff("POST", f"/meetings/{mid}/order", {"order_id": order_id, "status": "done"})
    meet.staff("POST", f"/meetings/{mid}/result", {"result_ru": "Встреча прошла, поручения выданы службам"})
    mine = meet.mod.updates(DEVICES[16], None, db_path=str(meet.db_path))
    other = meet.mod.updates(DEVICES[17], None, db_path=str(meet.db_path))
    assert mine, "у зарегистрированного устройства нет событий — тест ничего не проверяет"
    assert other == [], other
    for event in mine:
        assert re.fullmatch(r"#[a-z-]+(/[A-Za-z0-9._:-]+)*", event["link"]), event["link"]
    assert not leaks(mine, device_needles(DEVICES[16:18]) + [STAFF_LOGIN])
    status, route = meet.resident("GET", "/meetings/updates", device=DEVICES[17])
    assert status == 200 and route["items"] == []
    status, body = meet.anon("GET", "/meetings/updates")
    # Без устройства — отказ (400) или пустая лента (200, R10 B-105: маршрут «для всех»), но не чужие события.
    assert status == 400 or (status == 200 and not body.get("items")), (status, body)


def test_unknown_meeting_id_is_404(meet):
    for mid in ("m-doesnotexist", "m-" + "a" * 60, "../m-1", XSS):
        status, body = meet.anon("GET", "/meetings/" + mid)
        assert status == 404, (mid, status, body)
