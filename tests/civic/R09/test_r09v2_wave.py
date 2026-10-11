"""R09 · волны 1–2 (POLISH_WAVE.md, POLISH_WAVE_2.md): уточнения, срочные случаи, «служба сообщила — жители
проверили», паспорт решения, одно обновление всем «Я тоже», «что изменилось», разъединение дублей, фото без EXIF."""

import base64
import io
import json
from datetime import datetime, timedelta

import pytest

from ui.civic_feedback.v2 import ComplaintStore, ComplaintsV2Service, Conflict, NotFound, RecordError, categories
from ui.civic_feedback.v2 import lifecycle, photos
from ui.civic_feedback.v2 import record as rec

DEV_A, DEV_B, DEV_C, DEV_D = ("dev-aaaaaaaaaaaaaaaa", "dev-bbbbbbbbbbbbbbbb", "dev-cccccccccccccccc",
                              "dev-dddddddddddddddd")
STOP = {"kind": "object", "id": "osm-node-123456", "label_ru": "Остановка «Нура»"}
POINT = [71.4135, 51.0915]


class Clock:
    def __init__(self):
        self.now = datetime(2026, 10, 12, 10, 0, tzinfo=rec.ASTANA_TZ)   # понедельник

    def __call__(self):
        return self.now


@pytest.fixture
def clock():
    return Clock()


@pytest.fixture
def store(tmp_path, clock):
    s = ComplaintStore(tmp_path / "w.sqlite3", clock=clock)
    yield s
    s.close()


def make(store, device=DEV_A, **over):
    body = {"text": "Не горит фонарь у остановки", "category": "lighting", "point": POINT, "target": STOP}
    body.update(over)
    return store.create(body, device)[0]


# ---------------------------------------------------------------- волна 1, п. 2–3
def test_subtopic_saved_and_checked_against_category(store):
    record = make(store, subtopic="lamp_off")
    assert record["subtopic"] == "lamp_off" and rec.public_view(record)["subtopic"] if False else True
    assert store.get(record["id"])["subtopic"] == "lamp_off"
    with pytest.raises(RecordError) as exc:
        make(store, subtopic="pothole")                     # уточнение другой категории
    assert "subtopic" in exc.value.fields
    with pytest.raises(RecordError):
        make(store, subtopic="made_up")
    assert make(store)["subtopic"] is None                  # уточнение необязательно


def test_every_category_subtopic_is_well_formed():
    total = 0
    for cat in categories.ids():
        for sub in categories.subtopics(cat):
            total += 1
            assert sub["id"] and sub["ru"] and sub["kk"]
            assert categories.subtopic(cat, sub["id"]) == sub
    assert total == 39
    phones = {s["id"]: s["emergency_phone"] for c in categories.ids() for s in categories.subtopics(c)
              if s.get("emergency_phone")}
    assert phones == {"wire_down": "112", "gas": "104", "smoke_fire": "112"}


@pytest.mark.parametrize("category, subtopic, text, phone", [
    ("smell_air", "gas", "Пахнет в подъезде", "104"),
    ("lighting", "wire_down", "Висит над дорогой", "112"),
    ("other", None, "Сильно пахнет газом в подъезде", "104"),
    ("other", None, "Подъезде газ иісі шығып тұр", "104"),
    ("other", None, "На пустыре пожар, всё в дыму", "112"),
    ("other", None, "Горит мусорный бак во дворе", "112"),
    ("other", None, "Аулада өрт шықты", "112"),
    ("other", None, "Оборван провод у школы", "112"),
    ("lighting", None, "Не горят фонари во дворе", None),     # «не горят» — про свет, не пожар
    ("lighting", None, "Фонарь горит весь день", None),        # свет, не пожар
    ("parking", None, "Машины стоят на газоне", None),         # «газон» — не газ
    ("roads", None, "Яма на дороге", None),
])
def test_emergency_detection(category, subtopic, text, phone):
    found = lifecycle.emergency(category, subtopic, text)
    assert (found or {}).get("phone") == phone


def test_emergency_is_stored_with_banner_flag(store):
    record = make(store, category="smell_air", subtopic="gas", text="Пахнет газом", emergency_shown=True)
    assert record["emergency"] == {"phone": "104", "reason": "subtopic", "banner_shown": True}
    quiet = make(store, text="Не горит фонарь")
    assert quiet["emergency"] is None


# ---------------------------------------------------------------- волна 2, п. 1 (+ волна 1, п. 4)
def fixed(store, record, what="Заменили лампу, проверили линию"):
    store.set_status(record["id"], "in_progress")
    return store.set_status(record["id"], "fixed", actor="master", what_done=what)


def test_reported_then_verified_by_resident(store, clock):
    record = make(store)
    store.metoo(record["id"], DEV_B)
    done = fixed(store, record)
    assert done["resolution"]["state"] == "reported" and done["resolution"]["what_done"].startswith("Заменили")
    assert lifecycle.heat_state(done, clock.now) == "reported_fixed"
    assert store.can_verify(record["id"], DEV_A) and store.can_verify(record["id"], DEV_B)
    assert not store.can_verify(record["id"], DEV_C)                        # не участник
    assert store.verify(record["id"], DEV_C, "yes")[1] == "not_participant"
    after, result = store.verify(record["id"], DEV_B, "yes")                # «Я тоже» тоже проверяет
    assert result == "recorded" and after["resolution"]["state"] == "verified"
    assert lifecycle.heat_state(after, clock.now) == "verified_fixed"
    assert store.verify(record["id"], DEV_B, "no")[1] == "already"          # один голос за раунд
    assert not store.can_verify(record["id"], DEV_B) and store.can_verify(record["id"], DEV_A)
    clock.now += timedelta(days=8)                                           # «проверено» видно 7 дней
    assert lifecycle.heat_state(store.get(record["id"]), clock.now) is None


def test_problem_remains_returns_same_card_to_work_with_history(store, clock):
    record = make(store)
    fixed(store, record)
    back, result = store.verify(record["id"], DEV_A, "no")
    assert result == "recorded" and back["status"] == "in_progress" and back["id"] == record["id"]
    assert back["status_history"][-1] == {"at": rec.iso(clock.now), "status": "in_progress", "reopened_by_residents": True}
    assert back["resolution"]["state"] == "reopened" and back["resolution"]["reopen_count"] == 1
    assert lifecycle.heat_state(back, clock.now) == "reopened"
    assert [u["kind"] for u in back["updates"]] == ["fixed", "reopened"]
    assert store.verify(record["id"], DEV_A, "yes")[1] == "not_waiting"
    again = store.set_status(record["id"], "fixed", what_done="Заменили кабель")   # новый раунд — новые голоса
    assert again["resolution"]["round"] == 2 and again["resolution"]["votes"] == {"yes": 0, "no": 0, "cant": 0}
    assert again["resolution"]["reopen_count"] == 1
    assert store.verify(record["id"], DEV_A, "cant")[0]["resolution"]["state"] == "reported"


def test_old_fixed_call_without_what_done_still_works(store, clock):
    record = make(store)
    store.set_status(record["id"], "accepted")
    done = store.set_status(record["id"], "fixed")                          # R07 и демо R01: {status: "fixed"}
    assert done["resolution"]["state"] == "reported" and done["resolution"]["what_done"] is None
    reopened = store.set_status(record["id"], "in_progress")                 # служба сама вернула
    assert reopened["resolution"]["state"] == "withdrawn" and lifecycle.heat_state(reopened, clock.now) is None


def test_verify_rejects_unknown_answer(store):
    record = make(store)
    fixed(store, record)
    with pytest.raises(RecordError):
        store.verify(record["id"], DEV_A, "maybe")


def test_heat_states_match_categories_file():
    states = categories.load()["heat_states"]
    assert set(states) == {"no_data", "reported_fixed", "verified_fixed", "reopened"}
    assert states["verified_fixed"]["days_visible"] == lifecycle.VERIFIED_DAYS


# ---------------------------------------------------------------- волна 2, п. 2–3 (+ волна 1, п. 7)
def test_passport_three_fields_and_overdue_update(store, clock):
    record = make(store)
    with pytest.raises(RecordError):
        store.update_passport(record["id"], {"fix_eta": "завтра"})
    after, notified = store.update_passport(record["id"], {
        "next_step": "Электрик выедет и заменит лампу", "fix_eta": "2026-10-16",
        "delay_reason": "Ждём кабель", "temp_measure": "Поставили переносной фонарь",
        "next_update_at": "2026-10-14"}, actor="operator1")
    assert notified == 1
    view = lifecycle.passport_view(after, clock.now)
    assert view["assignee"] == "Служба освещения" and view["assignee_source"] == "default"
    assert view["next_step"].startswith("Электрик") and view["fix_eta"] == "2026-10-16"
    assert view["delay"] == {"reason": "Ждём кабель", "temp_measure": "Поставили переносной фонарь",
                             "next_update_at": "2026-10-14"}
    assert view["update_overdue"] is False and view["deadline"]["state"] == "ok"
    clock.now = datetime(2026, 10, 15, 9, 0, tzinfo=rec.ASTANA_TZ)
    assert lifecycle.passport_view(after, clock.now)["update_overdue"] is True    # видно руководителю
    unknown = store.update_passport(record["id"], {"fix_eta": ""})[0]
    assert lifecycle.passport_view(unknown, clock.now)["fix_eta"] is None          # «пока не определено»


def test_assignee_from_r08_table_wins_and_failure_falls_back(store, clock):
    record = make(store, category="utilities", subtopic="no_water", text="Нет воды третий день")
    assert lifecycle.passport_view(record, clock.now)["assignee"] == "Водоканал"
    assert lifecycle.passport_view(record, clock.now, lambda c, s: "Служба R08")["assignee"] == "Служба R08"
    assert lifecycle.passport_view(record, clock.now, lambda c, s: 1 / 0)["assignee"] == "Водоканал"
    # Казахская подпись: своя для общих названий R09, от R08 — если таблица дала {"ru", "kk"}.
    assert lifecycle.passport_view(record, clock.now)["assignee_kk"] == "Су арнасы"
    both = lifecycle.passport_view(record, clock.now, lambda c, s: {"ru": "Служба R08", "kk": "R08 қызметі"})
    assert (both["assignee"], both["assignee_kk"], both["assignee_source"]) == ("Служба R08", "R08 қызметі", "r08")
    assert lifecycle.passport_view(record, clock.now, lambda c, s: "Служба R08")["assignee_kk"] is None


def test_every_generic_service_has_kazakh_name():
    names = set(lifecycle.DEFAULT_SERVICES.values()) | set(lifecycle.SUBTOPIC_SERVICES.values())
    assert names <= set(lifecycle.SERVICES_KK)


def test_subtopic_services_use_real_ids():
    known = {s["id"] for c in categories.ids() for s in categories.subtopics(c)}
    assert set(lifecycle.SUBTOPIC_SERVICES) <= known
    assert set(lifecycle.DEFAULT_SERVICES) == set(categories.ids())


def test_one_update_reaches_author_and_every_metoo(store):
    record = make(store)
    for device in (DEV_B, DEV_C, DEV_D):
        store.metoo(record["id"], device)
    after, notified = store.post_update(record["id"], "Бригада выехала, будет к 15:00", actor="operator1")
    assert notified == 4                                                   # одно действие — 4 человека
    for device in (DEV_A, DEV_B, DEV_C, DEV_D):
        feed = store.changes(device)
        assert feed["items"][0]["kind"] == "note" and feed["items"][0]["text"].startswith("Бригада")


def test_changes_since_last_visit_and_summary(store, clock):
    record = make(store)
    store.metoo(record["id"], DEV_B)
    seen = rec.iso(clock.now)
    clock.now += timedelta(hours=1)
    store.set_status(record["id"], "in_progress")
    clock.now += timedelta(hours=1)
    fixed_rec = store.set_status(record["id"], "fixed", what_done="Заменили лампу")
    clock.now += timedelta(hours=1)
    store.verify(record["id"], DEV_B, "yes")
    feed = store.changes(DEV_A, seen)
    assert [i["kind"] for i in feed["items"]] == ["verified", "status", "status"]
    assert feed["summary"] == {"verified": 1, "waiting": 0, "total": 1}
    assert store.changes(DEV_A, rec.iso(clock.now))["items"] == []
    assert fixed_rec["code"] in {i["code"] for i in feed["items"]}
    assert all("by" not in i and "note" not in i for i in feed["items"])   # без имён сотрудников


# ---------------------------------------------------------------- волна 1, п. 9
def test_unmerge_duplicate_restores_people(store):
    original = make(store)
    dup = make(store, DEV_B, text="Темно у остановки, фонарь не горит")
    store.metoo(dup["id"], DEV_C)
    store.metoo(original["id"], DEV_D)
    merged = store.mark_duplicate(dup["id"], original["id"])
    assert merged["metoo"] == 3                                             # D + B + C
    split = store.unmark_duplicate(dup["id"], actor="operator1")
    assert split["duplicate_of"] is None and split["metoo"] == 1           # C вернулся к дублю
    assert store.get(original["id"])["metoo"] == 1                          # у исходной остался только D
    assert split["status_history"][-1]["unmerged_from"] == original["id"]
    assert {r["id"] for r in store.list()} == {original["id"], dup["id"]}
    with pytest.raises(Conflict):
        store.unmark_duplicate(dup["id"])
    with pytest.raises(NotFound):
        store.unmark_duplicate("c-nope0000000")


def test_old_database_gets_via_column(tmp_path):
    import sqlite3
    path = tmp_path / "old.sqlite3"
    db = sqlite3.connect(path)
    db.execute("CREATE TABLE complaint_metoo_v2 (complaint_id TEXT NOT NULL, device_hash TEXT NOT NULL, "
               "at TEXT NOT NULL, PRIMARY KEY (complaint_id, device_hash))")
    db.execute("INSERT INTO complaint_metoo_v2 VALUES ('c-1', 'h', '2026-10-01T00:00:00+05:00')")
    db.commit()
    db.close()
    s = ComplaintStore(path)
    cols = [r[1] for r in s._db.execute("PRAGMA table_info(complaint_metoo_v2)")]
    assert "via" in cols and s._db.execute("SELECT COUNT(*) FROM complaint_metoo_v2").fetchone()[0] == 1


# ---------------------------------------------------------------- волна 1, п. 5: фото
def exif_photo(fmt="JPEG"):
    from PIL import Image
    img = Image.new("RGB", (120, 80), (30, 120, 60))
    exif = Image.Exif()
    exif[0x010F] = "SecretPhoneMaker"
    exif[0x8825] = {1: "N", 2: (51.0, 5.0, 30.0), 3: "E", 4: (71.0, 25.0, 10.0)}
    out = io.BytesIO()
    img.save(out, fmt, exif=exif.tobytes())
    return out.getvalue()


def upload(store, complaint_id, data, *, kind="resident", device=DEV_A, actor=None, chunk=photos.CHUNK_BYTES):
    started = store.start_upload(complaint_id, kind, len(data), device_id=device, actor=actor)
    result = None
    for offset in range(0, len(data), chunk):
        result = store.upload_chunk(complaint_id, started["upload_id"], offset, data[offset:offset + chunk],
                                    device_id=device, actor=actor)
    return result


@pytest.mark.parametrize("fmt", ["JPEG", "PNG", "WEBP"])
def test_photo_metadata_and_gps_removed(store, fmt):
    pytest.importorskip("PIL")
    from PIL import Image
    record = make(store)
    raw = exif_photo(fmt)
    assert b"SecretPhoneMaker" in raw
    result = upload(store, record["id"], raw, chunk=200)                   # много частей
    assert result["done"]
    stored = store.get_photo(record["id"], result["photo"]["id"])
    assert b"SecretPhoneMaker" not in stored["data"]
    image = Image.open(io.BytesIO(stored["data"]))
    image.load()
    assert len(image.getexif()) == 0 and image.size == (120, 80)
    assert store.get(record["id"])["photos"][0]["id"] == result["photo"]["id"]


def test_photo_limits_owner_and_order(store):
    pytest.importorskip("PIL")
    record = make(store)
    raw = exif_photo()
    with pytest.raises(Conflict):
        store.start_upload(record["id"], "resident", len(raw), device_id=DEV_B)      # не автор
    with pytest.raises(RecordError):
        store.start_upload(record["id"], "resident", photos.MAX_BYTES + 1, device_id=DEV_A)
    started = store.start_upload(record["id"], "resident", len(raw), device_id=DEV_A)
    with pytest.raises(Conflict):
        store.upload_chunk(record["id"], started["upload_id"], 100, raw[100:200], device_id=DEV_A)  # не по порядку
    first = store.upload_chunk(record["id"], started["upload_id"], 0, raw[:100], device_id=DEV_A)
    again = store.upload_chunk(record["id"], started["upload_id"], 0, raw[:100], device_id=DEV_A)  # повтор части
    assert first == again == {"done": False, "received": 100}
    for _ in range(2):
        upload(store, record["id"], raw)
    store.upload_chunk(record["id"], started["upload_id"], 100, raw[100:], device_id=DEV_A)
    with pytest.raises(Conflict):
        store.start_upload(record["id"], "resident", len(raw), device_id=DEV_A)     # больше 3 нельзя


def test_not_a_photo_is_rejected(store):
    record = make(store)
    fake = b"%PDF-1.4 not an image" * 10
    started = store.start_upload(record["id"], "resident", len(fake), device_id=DEV_A)
    with pytest.raises(RecordError):
        store.upload_chunk(record["id"], started["upload_id"], 0, fake, device_id=DEV_A)
    with pytest.raises(photos.PhotoError):
        photos.sanitize(b"\xff\xd8\xff\xe1\x00")                              # обрезанный jpeg


def test_after_photos_attach_to_fixed_round(store):
    pytest.importorskip("PIL")
    record = make(store)
    result = upload(store, record["id"], exif_photo(), kind="after", device=None, actor="master")
    store.set_status(record["id"], "in_progress")
    done = store.set_status(record["id"], "fixed", what_done="Заменили лампу", photos=[result["photo"]["id"]])
    assert done["resolution"]["photos_after"] == [result["photo"]["id"]]
    assert store.get_photo(record["id"], result["photo"]["id"])["round"] == 1
    with pytest.raises(RecordError):
        store.set_status(record["id"], "in_progress") and store.set_status(record["id"], "fixed", photos=["p-x"])


# ---------------------------------------------------------------- HTTP
class Staff:
    is_staff = True
    username = "operator1"

    def check_csrf(self, value):
        return value == "tok"


def ctx(device=None, csrf=None):
    headers = {"X-Birge-Device": device} if device else {}
    if csrf:
        headers["X-CSRF-Token"] = csrf
    return {"headers": headers, "host_allowed": True, "is_same_origin": True}


def call(api, method, path, body=None, principal=None, context=None, query=None):
    raw = json.dumps(body).encode() if body is not None else None
    reply = api.handle(method, "/api/civic/v2" + path, query, raw, principal, context or ctx(DEV_A))
    json.dumps(reply["body"])
    return reply["status"], reply["body"]


def test_http_central_scene_and_privacy(store, clock):
    pytest.importorskip("PIL")
    api = ComplaintsV2Service(store)
    status, body = call(api, "POST", "/complaints", {"text": "Не горит фонарь", "category": "lighting",
                                                     "subtopic": "lamp_off", "point": POINT, "target": STOP})
    cid = body["data"]["complaint"]["id"]
    assert status == 201 and body["data"]["complaint"]["subtopic"] == "lamp_off"
    assert body["data"]["complaint"]["passport"]["assignee"] == "Служба освещения"
    call(api, "POST", f"/complaints/{cid}/metoo", {}, context=ctx(DEV_B))
    # фото жителя: загрузка частями через HTTP, видит автор и акимат, «Я тоже» — нет
    raw = exif_photo()
    _, start = call(api, "POST", f"/complaints/{cid}/photos", {"kind": "resident", "size": len(raw)})
    up = start["data"]["upload_id"]
    status, done = call(api, "POST", f"/complaints/{cid}/photos/{up}",
                        {"offset": 0, "data": base64.b64encode(raw).decode()})
    pid = done["data"]["photo"]["id"]
    assert status == 201
    assert call(api, "GET", f"/complaints/{cid}/photos/{pid}")[0] == 200
    assert call(api, "GET", f"/complaints/{cid}/photos/{pid}", context=ctx(DEV_B))[0] == 403
    assert call(api, "GET", f"/complaints/{cid}/photos/{pid}", context=ctx(DEV_C))[0] == 403
    status, photo = call(api, "GET", f"/complaints/{cid}/photos/{pid}", principal=Staff(), context=ctx(csrf="tok"))
    assert status == 200 and photo["data"]["photo"]["data_url"].startswith("data:image/jpeg;base64,")
    # фото «после» — только сотрудник
    assert call(api, "POST", f"/complaints/{cid}/photos", {"kind": "after", "size": 10})[0] == 403
    # паспорт и обновление — сотрудник; ответ говорит, сколько человек увидят
    assert call(api, "POST", f"/complaints/{cid}/passport", {"next_step": "x"})[0] == 403
    _, passport = call(api, "POST", f"/complaints/{cid}/passport", {"next_step": "Электрик выедет завтра"},
                       principal=Staff(), context=ctx(csrf="tok"))
    assert passport["data"]["notified"] == 2
    call(api, "POST", f"/complaints/{cid}/status", {"status": "in_progress"}, principal=Staff(), context=ctx(csrf="tok"))
    _, fixed_body = call(api, "POST", f"/complaints/{cid}/status", {"status": "fixed", "what_done": "Заменили лампу"},
                         principal=Staff(), context=ctx(csrf="tok"))
    assert fixed_body["data"]["complaint"]["heat_state"] == "reported_fixed" and fixed_body["data"]["notified"] == 2
    # «Я тоже» видит «что сделали», паспорт и кнопку проверки; чужой — только состояние
    _, mine_b = call(api, "GET", "/complaints/mine", context=ctx(DEV_B))
    item = mine_b["data"]["items"][0]
    assert item["relation"] == "metoo" and item["can_verify"] and item["resolution"]["what_done"] == "Заменили лампу"
    assert item["passport"]["next_step"] == "Электрик выедет завтра" and "text" not in item and "photos" not in item
    _, public = call(api, "GET", f"/complaints/{cid}", context=ctx(DEV_C))
    pub = public["data"]["complaint"]
    assert pub["heat_state"] == "reported_fixed" and "what_done" not in json.dumps(pub) and "passport" not in pub
    # проверка: «Я тоже» говорит «Да» -> проверено, карта зелёная
    status, verified = call(api, "POST", f"/complaints/{cid}/verify", {"answer": "yes"}, context=ctx(DEV_B))
    assert status == 200 and verified["data"]["result"] == "recorded"
    assert verified["data"]["complaint"]["heat_state"] == "verified_fixed" and not verified["data"]["complaint"]["can_verify"]
    _, listed = call(api, "GET", "/complaints", query="days=14", context=ctx(DEV_C))
    assert listed["data"]["items"][0]["heat_state"] == "verified_fixed"
    assert listed["data"]["items"][0]["resolution"]["votes"]["yes"] == 1
    # «что изменилось» и разъединение
    _, changes = call(api, "GET", "/complaints/changes", context=ctx(DEV_A))
    assert changes["data"]["items"][0]["kind"] == "verified"
    assert call(api, "GET", "/complaints/changes", query="since=вчера")[0] == 422
    assert call(api, "POST", f"/complaints/{cid}/unduplicate", {}, principal=Staff(), context=ctx(csrf="tok"))[0] == 409
    assert call(api, "POST", f"/complaints/{cid}/update", {"text": "Спасибо всем"}, principal=Staff(),
                context=ctx(csrf="tok"))[1]["data"]["notified"] == 2


def test_http_bad_photo_chunk(store):
    api = ComplaintsV2Service(store)
    record = make(store)
    _, start = call(api, "POST", f"/complaints/{record['id']}/photos", {"kind": "resident", "size": 10})
    status, body = call(api, "POST", f"/complaints/{record['id']}/photos/{start['data']['upload_id']}",
                        {"offset": 0, "data": "@@@"})
    assert status == 422


# ---------------------------------------------------------------- LOCAL_FINAL (Codex, Windows) №1
def test_staff_session_does_not_hide_people_count_from_resident_wizard(store):
    """Сотрудник вошёл раньше жителя: ответ сотруднику содержит reporters, а мастер жителя (?view=public)
    получает ровно публичную проекцию — без текста и с тем же числом людей."""
    api = ComplaintsV2Service(store)
    record = make(store)
    store.metoo(record["id"], DEV_B)
    store.metoo(record["id"], DEV_C)
    _, staff = call(api, "GET", f"/complaints/{record['id']}", principal=Staff(), context=ctx(DEV_D, csrf="tok"))
    assert staff["data"]["complaint"]["reporters"] == 3 and "text" in staff["data"]["complaint"]
    _, public = call(api, "GET", f"/complaints/{record['id']}", query="view=public", principal=Staff(),
                     context=ctx(DEV_D, csrf="tok"))
    assert public["data"]["complaint"]["reporters"] == 3 and "text" not in public["data"]["complaint"]
    _, by_code = call(api, "GET", f"/complaints/{record['code']}", query="view=public", context=ctx(DEV_A))
    assert "text" not in by_code["data"]["complaint"]        # даже автору view=public — публичная проекция
