"""R15 раунд 15 · R16 «Мой двор» и «Сделаем вместе» (ui.civic_together) — THREATS_R15 §5.

Сервис проверяется напрямую (make_service(db).handle — kind="service" шлюза R01), автопубликация выключена:
- состав двора и «Я приду» — только числа: без устройств, хэшей и времени; id устройства в SQLite — хэшем (T-R16-01/02, P6);
- автор не раскрывается; поля сервера из тела создания не берутся (T-R16-04, T-R16-08);
- «на проверке» и «снято» не видны никому, кроме автора и сотрудника (T-R16-07);
- личные данные в тексте не публикуются даже после «Опубликовать» (маска text_public) (T-R16-05);
- «Я приду» — один раз с устройства, не ниже 0; только опубликованная инициатива (T-R16-09/10);
- действия акимата — сотрудник с CSRF и своим Origin (T-R16-12); отчёт — только автор или сотрудник (T-R16-13);
- фото «после» без EXIF/GPS, только JPEG/PNG/WebP (T-R16-14); «старший по двору» — сосед, без телефона, после
  проверки, снимается одним действием (T-R16-16); лента — только своему устройству, ссылки внутренние (T-R16-17).
Нет ui.civic_together в сборке — NOT_RUN.
"""

from __future__ import annotations

import base64
import re

import pytest

from r15_common import xfail
from r15_round15 import (CSRF, DEVICES, PII, STAFF_LOGIN, Svc, XSS, YARD_ID, YARD_POINT, data, db_contains,
                         device_needles, dump, iso_in, leaks, module, staff_principal, xmarks)

AUTHOR, OTHER = DEVICES[20], DEVICES[21]


@pytest.fixture()
def tg(tmp_path, monkeypatch):
    for name in ("CIVIC_DEMO", "CIVIC_DEMO_WORLD", "CIVIC_TOGETHER_AUTOPUBLISH"):
        monkeypatch.delenv(name, raising=False)
    return Svc(module("ui.civic_together", "R16"), tmp_path / "civic.sqlite3", demo=False, autopublish=False)


def _body(**extra):
    body = {"kind": "cleanup", "title": "Субботник во дворе", "text": "Уберём двор и детскую площадку вместе",
            "point": list(YARD_POINT), "target": {"kind": "area", "id": YARD_ID}, "starts_at": iso_in(days=2),
            "bring": ["перчатки", "мешки"]}
    body.update(extra)
    return body


def _create(tg, device=AUTHOR, **extra):
    status, body = tg.resident("POST", "/together/initiatives", _body(**extra), device=device)
    assert status in (200, 201), (status, body)
    return data(body)["initiative"]


def _publish(tg, iid):
    status, body = tg.staff("POST", f"/together/initiatives/{iid}/moderate", {"action": "publish"})
    assert status == 200, (status, body)
    return data(body)["initiative"]


def _public_reads(tg, iid, device=OTHER):
    reads = [tg.anon("GET", "/together/initiatives"), tg.anon("GET", "/together/initiatives/" + iid),
             tg.resident("GET", "/together/initiatives", device=device),
             tg.resident("GET", "/together/initiatives", query="yard=" + YARD_ID, device=device),
             tg.anon("GET", "/together/yards/" + YARD_ID), tg.anon("GET", "/together/yards")]
    return [body for _status, body in reads]


def test_create_ignores_server_fields(tg):
    """T-R16-08: статус, «Я приду», поддержка акимата, отчёт, «Пример», автор — только сервер ставит."""
    item = _create(tg, status="published", joined=500, support={"by_akimat": True, "inventory": True},
                   report={"text": "Сделано вместе", "status": "published"}, demo=True,
                   author_device=OTHER, published_at=iso_in(-1), done_at=iso_in(-1))
    assert item["status"] == "on_review" and item["joined"] in (0, 1), item
    assert not item.get("support") and not item.get("report") and item["demo"] is False, item
    published = _publish(tg, item["id"])
    assert published["joined"] in (0, 1) and not (published.get("support") or {}).get("by_akimat"), published


def test_unreviewed_and_hidden_are_invisible(tg):
    """T-R16-07: «на проверке» и «снято» — 404 и нет в списках; автор и сотрудник видят."""
    item = _create(tg)
    iid = item["id"]
    for query in ("", "status=published", "status=done", "status=active", "view=public", "kind=cleanup",
                  "yard=" + YARD_ID, "district=nura"):
        assert iid not in dump(tg.anon("GET", "/together/initiatives", query=query)[1]), query
    for status_query in ("status=on_review", "status=hidden", "status=all", "view=staff"):
        status, body = tg.anon("GET", "/together/initiatives", query=status_query)
        assert status in (400, 401, 403) or iid not in dump(body), (status_query, status)
    assert tg.anon("GET", "/together/initiatives/" + iid)[0] == 404
    assert tg.resident("GET", "/together/initiatives/" + iid, device=OTHER)[0] == 404
    assert tg.resident("POST", f"/together/initiatives/{iid}/join", {}, device=OTHER)[0] == 404
    assert tg.resident("GET", "/together/initiatives/" + iid, device=AUTHOR)[0] == 200
    assert tg.staff("GET", "/together/initiatives/" + iid, csrf=None)[0] == 200
    status, body = tg.staff("POST", f"/together/initiatives/{iid}/moderate", {"action": "hide", "reason": "spam"})
    assert status == 200, body
    assert tg.anon("GET", "/together/initiatives/" + iid)[0] == 404
    assert iid not in dump(_public_reads(tg, iid))


PII_CASES = [pytest.param(kind, marks=[]) for kind in sorted(PII)] + [
    # Обход запасного фильтра R16 (пока нет R04 moderate): ИИН с пробелами, мобильный без +7/8 — S46.
    pytest.param("iin_spaced", marks=xmarks("S46")), pytest.param("phone_no_prefix", marks=xmarks("S46"))]
EXTRA_PII = {"iin_spaced": ("ИИН 900101 300 125 — помогите, я пожилая", ("900101 300 125", "900101300125")),
             "phone_no_prefix": ("Звоните 701 123 45 67, отвезу мусор", ("701 123 45 67",))}


@pytest.mark.parametrize("kind", PII_CASES)
def test_personal_data_never_public_even_after_publish(tg, kind):
    """T-R16-05: телефон, ИИН, e-mail, карта в тексте не видны публично и после «Опубликовать» (маска text_public)."""
    text, needles = PII.get(kind) or EXTRA_PII[kind]
    item = _create(tg, text=text)
    _publish(tg, item["id"])
    reads = _public_reads(tg, item["id"])
    assert not leaks(reads, needles), (kind, dump(reads)[:500])


@xfail("S47")
@pytest.mark.parametrize("kind", sorted(PII))
def test_bring_items_are_moderated(tg, kind):
    """S47 / T-R16-05: «что взять» — тоже текст жителя: телефон в пункте списка не публикуется и виден сотруднику флагом."""
    text, needles = PII[kind]
    item = _create(tg, bring=["перчатки", text[:40]])
    staff = data(tg.staff("GET", "/together/initiatives", query="view=staff&tab=queue", csrf=None)[1])
    flagged = [i for i in staff.get("items") or [] if i["id"] == item["id"] and i.get("flags")]
    _publish(tg, item["id"])
    reads = _public_reads(tg, item["id"])
    assert not leaks(reads, needles) and flagged, (kind, dump(reads)[:300], flagged)


def test_author_is_never_disclosed(tg):
    """T-R16-04, P1/P6: в публичных ответах нет устройства и хэша автора, логина сотрудника, времени создания."""
    item = _create(tg)
    _publish(tg, item["id"])
    tg.resident("POST", f"/together/initiatives/{item['id']}/join", {}, device=OTHER)
    reads = _public_reads(tg, item["id"])
    assert not leaks(reads, device_needles([AUTHOR, OTHER]) + [STAFF_LOGIN]), dump(reads)[:500]
    assert not re.search(r'"(author|author_device|author_hash|device_hash|created_by|actor|created_at)"',
                         dump(reads)), dump(reads)[:500]
    assert not db_contains(tg.db_path, [AUTHOR, OTHER]), "сырой id устройства в SQLite"


@pytest.mark.xfail(strict=False, reason="R15-S45 (R16, низкий): точка инициативы публично с 6 знаками (≈ 10 см) — "
                                        "рекомендация 4 знака (≈ 10 м); решает R16")
def test_public_point_is_not_doorstep_precise(tg):
    """T-R16-04: место дела публично — не точнее 4 знаков (≈ 10 м): «помощь соседям» не указывает дверь подъезда."""
    item = _create(tg, kind="help", point=[71.4047391, 51.1111749], title="Помощь пожилой соседке",
                   text="Поможем донести покупки")
    _publish(tg, item["id"])
    status, body = tg.anon("GET", "/together/initiatives/" + item["id"])
    lon, lat = body["initiative"]["point"]
    assert round(lon, 4) == lon and round(lat, 4) == lat, body["initiative"]["point"]


def test_join_once_per_device_never_negative(tg):
    """T-R16-09/10: повтор «Я приду» не считается; «Не приду» без «Я приду» не уводит в минус."""
    iid = _publish(tg, _create(tg)["id"])["id"]
    for _ in range(5):
        status, body = tg.resident("POST", f"/together/initiatives/{iid}/join", {}, device=OTHER)
        assert status == 200, body
    for dev in DEVICES[22:26]:
        tg.resident("POST", f"/together/initiatives/{iid}/leave", {}, device=dev)
    status, body = tg.anon("GET", "/together/initiatives/" + iid)
    assert body["initiative"]["joined"] == 1, body["initiative"]["joined"]
    assert tg.resident("GET", "/together/initiatives/" + iid, device=OTHER)[1]["initiative"]["my_join"] is True
    assert tg.resident("GET", "/together/initiatives/" + iid, device=DEVICES[30])[1]["initiative"]["my_join"] is False


def test_yard_membership_is_only_a_number(tg):
    """T-R16-01/02: «Я живу здесь» — число; кто и когда — нигде; «моё» — только запросившему устройству."""
    for dev in DEVICES[31:34]:
        status, body = tg.resident("POST", f"/together/yards/{YARD_ID}/join", {}, device=dev)
        assert status == 200, body
    status, page = tg.anon("GET", "/together/yards/" + YARD_ID)
    assert status == 200 and data(page)["yard"]["members"] >= 3, page
    status, mine = tg.resident("GET", "/together/yards/" + YARD_ID, device=DEVICES[31])
    status, other = tg.resident("GET", "/together/yards/" + YARD_ID, device=DEVICES[35])
    assert data(mine)["me"]["member"] is True and data(other)["me"]["member"] is False
    reads = [page, other, tg.anon("GET", "/together/yards")[1],
             tg.resident("GET", "/together/updates", device=DEVICES[35])[1]]
    assert not leaks(reads, device_needles(DEVICES[31:34])), dump(reads)[:500]
    assert not re.search(r'"(joined_at|member_since|members_list|devices|device_hash)"', dump(reads))
    assert not db_contains(tg.db_path, DEVICES[31:34])
    status, body = tg.resident("POST", f"/together/yards/{YARD_ID}/leave", {}, device=DEVICES[31])
    assert status == 200 and data(tg.anon("GET", "/together/yards/" + YARD_ID)[1])["yard"]["members"] == \
        data(page)["yard"]["members"] - 1


@pytest.mark.parametrize("who", ["anon", "resident", "no_csrf", "bad_csrf", "cross_origin", "resident_role"])
def test_akimat_actions_need_staff_with_csrf(tg, who):
    """T-R16-12: «Поддержать», модерация, снятие, имя старшего — только сотрудник с CSRF со своего сайта."""
    iid = _publish(tg, _create(tg)["id"])["id"]
    queued = _create(tg, device=DEVICES[36], title="Ещё одно дело во дворе")["id"]
    calls = [(f"/together/initiatives/{iid}/support", {"inventory": True, "pickup_service": "waste"}),
             (f"/together/initiatives/{queued}/moderate", {"action": "publish"}),
             (f"/together/initiatives/{iid}/moderate", {"action": "hide", "reason": "spam"}),
             (f"/together/yards/{YARD_ID}/moderate", {"action": "publish"})]
    for path, body in calls:
        if who == "anon":
            status, reply = tg.anon("POST", path, body)
        elif who == "resident":
            status, reply = tg.resident("POST", path, body, device=DEVICES[37])
        elif who == "no_csrf":
            status, reply = tg.staff("POST", path, body, csrf=None)
        elif who == "bad_csrf":
            status, reply = tg.staff("POST", path, body, csrf="z" * len(CSRF))
        elif who == "cross_origin":
            status, reply = tg.staff("POST", path, body, origin=False)
        else:
            status, reply = tg.staff("POST", path, body, principal=staff_principal(role="resident"))
        assert status in (401, 403), (who, path, status, reply)
    status, body = tg.anon("GET", "/together/initiatives/" + iid)
    assert status == 200 and not (body["initiative"].get("support") or {}).get("by_akimat")
    assert tg.anon("GET", "/together/initiatives/" + queued)[0] == 404


def test_report_only_by_author_or_staff_and_reviewed(tg):
    """T-R16-13: отчёт «Сделано вместе» чужого устройства — 403; отчёт автора — на проверке, публично не виден."""
    iid = _publish(tg, _create(tg, starts_at=iso_in(hours=0.2))["id"])["id"]
    status, body = tg.resident("POST", f"/together/initiatives/{iid}/report",
                               {"text": "Подделанный отчёт: всё убрали сами"}, device=OTHER)
    assert status in (403, 404), (status, body)
    status, body = tg.resident("POST", f"/together/initiatives/{iid}/report",
                               {"text": "Убрали двор и посадили 6 саженцев"}, device=AUTHOR)
    if status == 409:
        pytest.skip("NOT_RUN: отчёт автора до начала дела закрыт (409) — проверено только «чужой — 403»")
    assert status == 200, body
    status, public = tg.anon("GET", "/together/initiatives/" + iid)
    assert "Убрали двор" not in dump(public) and public["initiative"]["status"] != "done", public


def test_after_photo_is_clean_and_only_images(tg):
    """T-R16-14: фото «после» публично без EXIF/GPS (S22); SVG и не-картинка — отказ."""
    from test_r15_photos import JPEG_GPS
    iid = _publish(tg, _create(tg, starts_at=iso_in(hours=0.2))["id"])["id"]
    url = "data:image/jpeg;base64," + base64.b64encode(JPEG_GPS).decode()
    status, body = tg.staff("POST", f"/together/initiatives/{iid}/report",
                            {"text": "Убрали двор вместе с соседями", "photo": {"data_url": url}})
    if status == 422 and "проверки фото" in dump(body):
        pytest.skip("NOT_RUN: в сборке нет проверки фото R09 (ui.civic_feedback.v2.photos)")
    assert status == 200, body
    status, public = tg.anon("GET", "/together/initiatives/" + iid)
    photos = ((public["initiative"].get("report") or {}).get("photos") or [])
    assert photos and photos[0].get("data_url"), public
    raw = base64.b64decode(photos[0]["data_url"].split(",", 1)[1])
    assert b"SECRETPHONE" not in raw and b"Exif" not in raw
    svg = "data:image/svg+xml;base64," + base64.b64encode(b"<svg onload='alert(1)'/>").decode()
    fake = "data:image/jpeg;base64," + base64.b64encode(b"<html><script>alert(1)</script></html>").decode()
    for bad in (svg, fake, "javascript:alert(1)", {"x": 1}):
        status, reply = tg.staff("POST", f"/together/initiatives/{iid}/report",
                                 {"text": "Ещё одно фото после", "photo": {"data_url": bad} if isinstance(bad, str)
                                  else bad})
        assert status == 422, (bad if isinstance(bad, str) else "obj", status, reply)


def test_yard_captain_rules(tg):
    """T-R16-16: старший — только сосед, без телефона в имени, после проверки; второй — не перехватит; снять — одним
    действием; до проверки имени публично нет."""
    status, _b = tg.resident("POST", f"/together/yards/{YARD_ID}/captain", {"display_name": "Айгуль"}, device=OTHER)
    assert status in (403, 404, 409), status                    # не сосед (двор модулю ещё не известен — 404)
    tg.resident("POST", f"/together/yards/{YARD_ID}/join", {}, device=DEVICES[45])
    status, _b = tg.resident("POST", f"/together/yards/{YARD_ID}/captain", {"display_name": "Айгуль"}, device=OTHER)
    assert status in (403, 409), status                         # двор известен, но OTHER — не сосед
    tg.resident("POST", f"/together/yards/{YARD_ID}/join", {}, device=OTHER)
    tg.resident("POST", f"/together/yards/{YARD_ID}/join", {}, device=DEVICES[38])
    status, body = tg.resident("POST", f"/together/yards/{YARD_ID}/captain",
                               {"display_name": "Айгуль +7 701 123 45 67"}, device=OTHER)
    assert status == 422, (status, body)
    status, body = tg.resident("POST", f"/together/yards/{YARD_ID}/captain", {"display_name": "Айгуль"}, device=OTHER)
    assert status == 200, body
    assert "Айгуль" not in dump(tg.anon("GET", "/together/yards/" + YARD_ID)[1])   # на проверке
    status, _b = tg.resident("POST", f"/together/yards/{YARD_ID}/captain", {"display_name": "Захватчик"},
                             device=DEVICES[38])
    assert status == 409
    assert tg.staff("POST", f"/together/yards/{YARD_ID}/moderate", {"action": "publish"})[0] == 200
    assert "Айгуль" in dump(tg.anon("GET", "/together/yards/" + YARD_ID)[1])
    status, _b = tg.resident("POST", f"/together/yards/{YARD_ID}/captain", {"remove": True}, device=OTHER)
    assert status == 200 and "Айгуль" not in dump(tg.anon("GET", "/together/yards/" + YARD_ID)[1])


def test_updates_only_for_own_device(tg):
    """T-R16-17, T-R06-01/03: лента — своему устройству (двор, «Я приду», автор); чужому — пусто; без вступлений
    соседей; ссылки — #together/…"""
    item = _create(tg)
    tg.resident("POST", f"/together/yards/{YARD_ID}/join", {}, device=DEVICES[39])
    _publish(tg, item["id"])
    tg.resident("POST", f"/together/initiatives/{item['id']}/join", {}, device=DEVICES[40])
    tg.resident("POST", f"/together/yards/{YARD_ID}/join", {}, device=DEVICES[41])   # вступление соседа — не событие
    status, author = tg.resident("GET", "/together/updates", device=AUTHOR)
    status2, member = tg.resident("GET", "/together/updates", device=DEVICES[39])
    status3, stranger = tg.resident("GET", "/together/updates", device=DEVICES[42])
    assert status == status2 == status3 == 200
    assert data(author)["items"] and data(member)["items"], (author, member)
    assert data(stranger)["items"] == [] and data(stranger).get("yards") in (None, [])
    for event in data(author)["items"] + data(member)["items"]:
        assert re.fullmatch(r"#[a-z-]+(/[A-Za-z0-9._:-]+)*", event["link"]), event
        assert "join" not in event["kind"] and "member" not in event["kind"], event
    assert not leaks([author, member], device_needles(DEVICES[39:42] + (AUTHOR,)) + [STAFF_LOGIN])
    status, body = tg.anon("GET", "/together/updates")
    assert status == 400 or (status == 200 and not data(body).get("items")), (status, body)   # без устройства — ничего


@pytest.mark.parametrize("change", [{"target": {"kind": "area", "id": "yard-999999999999"}},
                                    {"point": [71.62, 51.20]},
                                    {"point": [37.61, 55.75]},
                                    {"target": {"kind": "object", "id": "osm-node-1"}},
                                    {"target": {"kind": "area", "id": YARD_ID, "label_ru": "Двор «Акимат берёт взятки»"}}])
def test_target_must_be_real_yard_near_point(tg, change):
    """T-R16-18, S04/S11/S12: несуществующий двор, точка далеко от двора или вне города — отказ; подпись двора —
    только с карты R12, не из запроса."""
    status, body = tg.resident("POST", "/together/initiatives", _body(**change), device=DEVICES[43])
    if "label_ru" in change.get("target", {}):
        assert status in (200, 201), body
        assert "взятки" not in dump(body), body
        return
    assert status in (400, 404, 422), (change, status, body)


def test_resident_writes_from_foreign_site_are_refused(tg):
    """S17/S37 раунда 14 для новых маршрутов: запись жителя с чужого сайта — 403."""
    iid = _publish(tg, _create(tg)["id"])["id"]
    for path, body in (("/together/initiatives", _body()), (f"/together/initiatives/{iid}/join", {}),
                       (f"/together/yards/{YARD_ID}/join", {}), (f"/together/yards/{YARD_ID}/captain",
                                                                 {"display_name": "Айгуль"})):
        status, reply = tg.resident("POST", path, body, device=DEVICES[44], origin=False)
        assert status == 403, (path, status, reply)


def test_html_is_stored_as_text(tg):
    """T-R16-06: HTML в названии/тексте/«что взять» — обычный текст в JSON (не исполнение — это браузерная проба)."""
    item = _create(tg, title="Дело " + XSS[:60], text="Текст " + XSS, bring=[XSS[:40]])
    assert "<img" in dump(item) or "&lt;img" in dump(item) or "***" in dump(item)


def test_unknown_ids_are_404(tg):
    for iid in ("i-doesnotexist", "../../etc/passwd", XSS, "i-" + "a" * 80):
        assert tg.anon("GET", "/together/initiatives/" + iid)[0] == 404, iid
    for yid in ("yard-999999999999", XSS, "../yard-1"):
        assert tg.anon("GET", "/together/yards/" + yid)[0] == 404, yid
