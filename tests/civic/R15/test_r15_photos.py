"""R15: фото к жалобе (POLISH_WAVE п. 5 и волна 2 п. 1, владелец R09) — метаданные, тип, размер, доступ;
проверка ремонта жителями (волна 2 п. 1) — кто может вернуть ремонт в работу.

Модуль R09 вызывается так же, как его вызывает шлюз R01 (handle на временной SQLite): тесты работают и в ветке R09,
и в сборке R01. Нет модуля фото — skip. Фото-образцы встроены (base64), Pillow не нужен.
"""

from __future__ import annotations

import base64
import struct
import types
import zlib

import pytest

from r15_common import ROOT, need_module, xfail

# Чистый JPEG 32×24 и сразу за ним второй JPEG с EXIF: модель телефона SECRETPHONE и GPS (51°07', 71°25').
# Так телефоны хранят MPF-превью и «живое фото» — после маркера конца первой картинки.
JPEG_WITH_TAIL = base64.b64decode("/9j/4AAQSkZJRgABAQAAAQABAAD/2wBDAAgGBgcGBQgHBwcJCQgKDBQNDAsLDBkSEw8UHRofHh0aHBwgJC4nICIsIxwcKDcpLDAxNDQ0Hyc5PTgyPC4zNDL/2wBDAQkJCQwLDBgNDRgyIRwhMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjL/wAARCAAYACADASIAAhEBAxEB/8QAHwAAAQUBAQEBAQEAAAAAAAAAAAECAwQFBgcICQoL/8QAtRAAAgEDAwIEAwUFBAQAAAF9AQIDAAQRBRIhMUEGE1FhByJxFDKBkaEII0KxwRVS0fAkM2JyggkKFhcYGRolJicoKSo0NTY3ODk6Q0RFRkdISUpTVFVWV1hZWmNkZWZnaGlqc3R1dnd4eXqDhIWGh4iJipKTlJWWl5iZmqKjpKWmp6ipqrKztLW2t7i5usLDxMXGx8jJytLT1NXW19jZ2uHi4+Tl5ufo6erx8vP09fb3+Pn6/8QAHwEAAwEBAQEBAQEBAQAAAAAAAAECAwQFBgcICQoL/8QAtREAAgECBAQDBAcFBAQAAQJ3AAECAxEEBSExBhJBUQdhcRMiMoEIFEKRobHBCSMzUvAVYnLRChYkNOEl8RcYGRomJygpKjU2Nzg5OkNERUZHSElKU1RVVldYWVpjZGVmZ2hpanN0dXZ3eHl6goOEhYaHiImKkpOUlZaXmJmaoqOkpaanqKmqsrO0tba3uLm6wsPExcbHyMnK0tPU1dbX2Nna4uPk5ebn6Onq8vP09fb3+Pn6/9oADAMBAAIRAxEAPwCvRRRX1B5YUUUUAFFFFABRRRQB/9n/2P/gABBKRklGAAEBAAABAAEAAP/hAKBFeGlmAABNTQAqAAAACAACAQ8AAgAAAAwAAAAmiCUABAAAAAEAAAAyAAAAAFNFQ1JFVFBIT05FAAAEAAEAAgAAAAJOAAAAAAIABQAAAAMAAABoAAMAAgAAAAJFAAAAAAQABQAAAAMAAACAAAAAAAAAADMAAAABAAAABwAAAAEAAAAeAAAAAQAAAEcAAAABAAAAGQAAAAEAAAApAAAAAf/bAEMACAYGBwYFCAcHBwkJCAoMFA0MCwsMGRITDxQdGh8eHRocHCAkLicgIiwjHBwoNyksMDE0NDQfJzk9ODI8LjM0Mv/bAEMBCQkJDAsMGA0NGDIhHCEyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMv/AABEIABgAIAMBIgACEQEDEQH/xAAfAAABBQEBAQEBAQAAAAAAAAAAAQIDBAUGBwgJCgv/xAC1EAACAQMDAgQDBQUEBAAAAX0BAgMABBEFEiExQQYTUWEHInEUMoGRoQgjQrHBFVLR8CQzYnKCCQoWFxgZGiUmJygpKjQ1Njc4OTpDREVGR0hJSlNUVVZXWFlaY2RlZmdoaWpzdHV2d3h5eoOEhYaHiImKkpOUlZaXmJmaoqOkpaanqKmqsrO0tba3uLm6wsPExcbHyMnK0tPU1dbX2Nna4eLj5OXm5+jp6vHy8/T19vf4+fr/xAAfAQADAQEBAQEBAQEBAAAAAAAAAQIDBAUGBwgJCgv/xAC1EQACAQIEBAMEBwUEBAABAncAAQIDEQQFITEGEkFRB2FxEyIygQgUQpGhscEJIzNS8BVictEKFiQ04SXxFxgZGiYnKCkqNTY3ODk6Q0RFRkdISUpTVFVWV1hZWmNkZWZnaGlqc3R1dnd4eXqCg4SFhoeIiYqSk5SVlpeYmZqio6Slpqeoqaqys7S1tre4ubrCw8TFxsfIycrS09TV1tfY2dri4+Tl5ufo6ery8/T19vf4+fr/2gAMAwEAAhEDEQA/AK9FFFfUHlhRRRQAUUUUAFFFFAH/2Q==")
SECOND = JPEG_WITH_TAIL.index(b"\xff\xd8\xff", 3)
JPEG_GPS = JPEG_WITH_TAIL[SECOND:]          # обычный JPEG с EXIF/GPS в APP1
AUTHOR, STRANGER, NEIGHBOUR = "device-r15-photo-author1", "device-r15-photo-strngr1", "device-r15-photo-neighb1"


def png_of_size(width, height):
    """PNG одного цвета нужного размера: сжимается в десятки КБ при любых сторонах."""
    co = zlib.compressobj(9)
    row = b"\x00" * (1 + width * 3)
    idat = b"".join(co.compress(row) for _ in range(height)) + co.flush()

    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", idat) + chunk(b"IEND", b""))


@pytest.fixture()
def photos():
    return need_module("ui.civic_feedback.v2.photos")


# --- метаданные, тип, размер ----------------------------------------------------------------

def test_exif_gps_removed_from_jpeg(photos):
    assert b"SECRETPHONE" in JPEG_GPS and b"Exif" in JPEG_GPS
    mime, clean = photos.sanitize(JPEG_GPS)
    assert mime == "image/jpeg" and b"SECRETPHONE" not in clean and b"Exif" not in clean


@xfail("S22")
def test_data_after_jpeg_end_is_dropped(photos):
    """Второе изображение / видео после конца JPEG (MPF, «живое фото») уходило в базу вместе со своим EXIF/GPS."""
    mime, clean = photos.sanitize(JPEG_WITH_TAIL)
    assert mime == "image/jpeg"
    assert b"SECRETPHONE" not in clean and b"Exif" not in clean
    assert clean.endswith(b"\xff\xd9") and len(clean) <= SECOND + 2


@xfail("S23")
def test_photo_bomb_dimensions_are_refused(photos):
    """PNG 5000×5000 весит ~70 КБ; 16000×16000 — < 1 МБ, а в браузере сотрудника это ~1 ГБ памяти."""
    data = png_of_size(5000, 5000)
    assert len(data) < 200_000
    with pytest.raises(photos.PhotoError):
        photos.sanitize(data)


def test_normal_photo_size_is_accepted(photos):
    mime, _clean = photos.sanitize(png_of_size(1600, 1200))
    assert mime == "image/png"


@pytest.mark.parametrize("data", [b"<svg xmlns='http://www.w3.org/2000/svg' onload='alert(1)'/>",
                                  b"<!doctype html><script>alert(1)</script>", b"GIF89a\x01\x00\x01\x00",
                                  b"%PDF-1.7\n", b"\xff\xd8\xff\xe0broken", b""])
def test_type_is_by_signature_only(photos, data):
    with pytest.raises(photos.PhotoError):
        photos.sanitize(data)


def test_size_limit(photos):
    with pytest.raises(photos.PhotoError):
        photos.sanitize(b"\xff\xd8\xff" + b"\x00" * (photos.MAX_BYTES + 1))


# --- доступ: фото жителя видит только акимат и автор -----------------------------------------------

@pytest.fixture()
def svc(tmp_path, photos):
    integration = need_module("ui.civic_feedback.v2.integration")
    service = integration.make_service(str(tmp_path / "civic.sqlite3"))
    yield service
    service.store.close()


def ctx(device=None, csrf=None):
    headers = {}
    if device:
        headers["X-Birge-Device"] = device
    if csrf:
        headers["X-CSRF-Token"] = csrf
    return {"headers": headers, "host_allowed": True, "is_same_origin": True}


STAFF = types.SimpleNamespace(is_staff=True, username="r15-photo-staff", role="editor", check_csrf=lambda v: v == "csrf-r15")


def call(svc, method, path, body=None, principal=None, context=None):
    reply = svc.handle(method, "/api/civic/v2" + path, "", body, principal, context or ctx())
    return reply["status"], reply["body"]


def upload(svc, complaint_id, data, kind="resident", device=AUTHOR, principal=None):
    context = ctx(device, "csrf-r15" if principal else None)
    status, body = call(svc, "POST", "/complaints/%s/photos" % complaint_id, {"kind": kind, "size": len(data)},
                        principal, context)
    assert status == 201, body
    up = body["data"]
    status, body = call(svc, "POST", "/complaints/%s/photos/%s" % (complaint_id, up["upload_id"]),
                        {"offset": 0, "data": base64.b64encode(data).decode()}, principal, context)
    assert status in (200, 201) and body["data"]["done"], body
    return body["data"]["photo"]["id"]


def complaint(svc):
    status, body = call(svc, "POST", "/complaints", {"text": "Не горит фонарь у подъезда", "category": "lighting",
                                                     "point": [71.41, 51.11]}, context=ctx(AUTHOR))
    assert status in (200, 201), body
    return body["data"]["complaint"]["id"]


def test_resident_photo_only_for_akimat_and_author(svc):
    cid = complaint(svc)
    photo = upload(svc, cid, JPEG_GPS)
    assert call(svc, "POST", "/complaints/%s/metoo" % cid, {}, context=ctx(NEIGHBOUR))[0] == 200
    path = "/complaints/%s/photos/%s" % (cid, photo)
    assert call(svc, "GET", path, context=ctx())[0] == 403                       # аноним
    assert call(svc, "GET", path, context=ctx(STRANGER))[0] == 403               # чужое устройство
    assert call(svc, "GET", path, context=ctx(NEIGHBOUR))[0] == 403              # «Я тоже» — не фото жителя
    status, body = call(svc, "GET", path, context=ctx(AUTHOR))
    assert status == 200 and body["data"]["photo"]["data_url"].startswith("data:image/jpeg;base64,")
    status, body = call(svc, "GET", path, principal=STAFF, context=ctx(csrf="csrf-r15"))
    assert status == 200
    assert b"SECRETPHONE" not in base64.b64decode(body["data"]["photo"]["data_url"].split(",", 1)[1])


def test_photo_ids_are_not_in_public_views(svc):
    cid = complaint(svc)
    photo = upload(svc, cid, JPEG_GPS)
    for path in ("/complaints", "/complaints/%s" % cid):
        status, body = call(svc, "GET", path, context=ctx(STRANGER))
        assert status == 200 and photo not in str(body), path


def test_only_author_adds_resident_photos(svc):
    cid = complaint(svc)
    status, _body = call(svc, "POST", "/complaints/%s/photos" % cid, {"kind": "resident", "size": 100},
                         context=ctx(STRANGER))
    assert status in (403, 409)
    status, _body = call(svc, "POST", "/complaints/%s/photos" % cid, {"kind": "after", "size": 100},
                         context=ctx(AUTHOR))
    assert status == 403                                                        # фото «после» — только служба


# --- проверка ремонта: «Проблема осталась» -------------------------------------------------------

def fixed(svc, cid):
    status, body = call(svc, "POST", "/complaints/%s/status" % cid, {"status": "fixed", "what_done": "Заменили лампу"},
                        principal=STAFF, context=ctx(csrf="csrf-r15"))
    assert status == 200, body
    return body["data"]["complaint"]


def test_author_and_earlier_metoo_can_reopen(svc):
    cid = complaint(svc)
    call(svc, "POST", "/complaints/%s/metoo" % cid, {}, context=ctx(NEIGHBOUR))
    fixed(svc, cid)
    status, body = call(svc, "POST", "/complaints/%s/verify" % cid, {"answer": "no"}, context=ctx(NEIGHBOUR))
    assert status == 200 and body["data"]["result"] == "recorded"
    assert body["data"]["complaint"]["status"] == "in_progress"


@xfail("S24")
def test_outsider_cannot_reopen_verified_fix(svc):
    """Посторонний: «Я тоже» ПОСЛЕ «служба сообщила об устранении» -> «Проблема осталась» -> проверенный ремонт снова
    «в работе», цель на карте снова красная. Повторяется каждый раунд."""
    cid = complaint(svc)
    fixed(svc, cid)
    assert call(svc, "POST", "/complaints/%s/verify" % cid, {"answer": "yes"}, context=ctx(AUTHOR))[0] == 200
    assert call(svc, "POST", "/complaints/%s/metoo" % cid, {}, context=ctx(STRANGER))[0] == 200
    status, body = call(svc, "POST", "/complaints/%s/verify" % cid, {"answer": "no"}, context=ctx(STRANGER))
    assert status == 200 and body["data"]["result"] != "recorded"
    assert body["data"]["complaint"]["status"] == "fixed"


# B-056 (R10, важно): строгая CSP сборки (S01: connect-src без blob:) запрещает fetch(blob:…). Фото «после» у сотрудника
# читалось так — «Сообщить жителям» с фото молча не отправлялось. Правка — сам Blob из shrink() (patch P-R09-3), а не
# расширение CSP. Не находка безопасности, поэтому не в FINDINGS; strict: когда R01 возьмёт P-R09-3, снять xfail.
STAFF_JS = ROOT / "web" / "civic" / "feedback" / "complaint-staff.js"


# P-R09-3 применил R01 в FINAL-3 (на R09 8a1d390): обычный тест-регрессия, xfail снят (так просит INTEGRATION R15).
def test_staff_after_photo_is_not_read_through_blob_fetch():
    if not STAFF_JS.is_file():
        pytest.skip("в этой сборке нет web/civic/feedback/complaint-staff.js (R09 волна 2)")
    import re
    code = STAFF_JS.read_text(encoding="utf-8")
    assert not re.search(r"fetch\(\s*photo\.url", code), "fetch(blob:…) — CSP connect-src его запрещает (B-056)"
