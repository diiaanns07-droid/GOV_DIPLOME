"""R04 · волна мелочей: сквозная проверка в сборке R01 (настоящий HTTP-сервер, настоящие R02/R09/R07/R04).

п. 8 — житель (и автор) получает текст со звёздочками, сотрудник акимата — оригинал и пометку moderation.rude;
       в карточке цели R07 у сотрудника — оригинал с флагом rude.
п. 9 — см. test_r04_separate_* ниже.

Тесты включаются, когда R01 применил patch шлюза (ui.web_server.public_text) — до этого skip с причиной.
"""

from __future__ import annotations

import json
import secrets
import threading
from http.client import HTTPConnection
from unittest.mock import patch

import pytest

web_server = pytest.importorskip("ui.web_server")
if not hasattr(web_server, "public_text"):
    pytest.skip("patch шлюза R01 (п. 8, research/round-14-results/R04/patches/r01_polish_r04.patch) ещё не применён",
                allow_module_level=True)
pytest.importorskip("ui.civic_store.service")
pytest.importorskip("ui.civic_feedback.v2.integration")

USER, PASSWORD = "r04_operator", "Esil-" + secrets.token_urlsafe(12)
NURA_STOP = [71.4180, 51.0905]
RUDE_TEXT = "Остановка разбита, заебали уже! Мрази, когда почините?"


class App:
    def __init__(self, tmp_path):
        db = tmp_path / "civic.sqlite3"
        self.gateway = web_server.CivicGateway.for_project(tmp_path, db)
        self.gateway.service("store").accounts.create_user(USER, PASSWORD, display_name="Оператор R04",
                                                           public_label="Акимат")
        self.server = web_server.create_server(port=0, civic=self.gateway)
        self.port = self.server.server_address[1]
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.cookie = self.csrf = None

    def stop(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=3)

    def call(self, method, path, payload=None, *, device=None, staff=False):
        headers = {"Origin": f"http://127.0.0.1:{self.port}", "Host": f"127.0.0.1:{self.port}"}
        body = None
        if payload is not None:
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            headers["Content-Type"] = "application/json"
        if device:
            headers["X-Birge-Device"] = device
        if staff:
            headers["Cookie"] = self.cookie
            if method != "GET":
                headers["X-CSRF-Token"] = self.csrf
        conn = HTTPConnection("127.0.0.1", self.port, timeout=20)
        try:
            conn.request(method, path, body=body, headers=headers)
            resp = conn.getresponse()
            raw = resp.read()
            cookies = [v for k, v in resp.getheaders() if k.lower() == "set-cookie"]
            return resp.status, (json.loads(raw) if raw else None), cookies
        finally:
            conn.close()

    def login(self):
        status, data, cookies = self.call("POST", "/api/civic/v1/session/login", {"username": USER, "password": PASSWORD})
        assert status == 200, data
        self.cookie = cookies[0].split(";", 1)[0]
        self.csrf = data["data"]["csrf_token"]

    def complaint(self, text, device, point=NURA_STOP, category="transport", target=None):
        payload = {"text": text, "category": category, "point": point}
        if target:
            payload["target"] = target
        status, data, _ = self.call("POST", "/api/civic/v2/complaints", payload, device=device)
        assert status == 201, data
        return data["data"]["complaint"]


@pytest.fixture()
def app(tmp_path):
    quiet = patch.object(web_server.Handler, "log_message", return_value=None)
    quiet.start()
    running = App(tmp_path)
    yield running
    running.stop()
    quiet.stop()


# --------------------------------------------------------------------------- п. 8
def test_resident_sees_stars_staff_sees_original_with_flag(app):
    created = app.complaint(RUDE_TEXT, "device-author-0001")
    # Автор (не сотрудник) — уже со звёздочками: всё, что уходит на устройство жителя, без мата.
    assert created["text"] == "Остановка разбита, з****** уже! М****, когда почините?"
    status, data, _ = app.call("GET", f"/api/civic/v2/complaints/{created['id']}", device="device-author-0001")
    assert status == 200 and data["data"]["complaint"]["text"].startswith("Остановка разбита, з******")
    assert "moderation" not in data["data"]["complaint"]
    status, data, _ = app.call("GET", "/api/civic/v2/complaints/mine", device="device-author-0001")
    assert status == 200 and "заебали" not in json.dumps(data, ensure_ascii=False)

    app.login()
    status, data, _ = app.call("GET", f"/api/civic/v2/complaints/{created['id']}", staff=True)
    record = data["data"]["complaint"]
    assert status == 200 and record["text"] == RUDE_TEXT                  # оригинал не потерян
    assert record["moderation"]["rude"] is True and record["moderation"]["count"] == 2
    assert set(record["moderation"]["kinds"]) == {"mat", "insult"}


def test_heat_card_texts_staff_original_with_rude_flag(app):
    created = app.complaint(RUDE_TEXT, "device-author-0002")
    target = created["target"]
    query = f"/api/civic/v2/heat/target?kind={target['kind']}&id={target['id']}&days=14"
    status, data, _ = app.call("GET", query)
    assert status == 200
    assert "заебали" not in json.dumps(data, ensure_ascii=False)            # жителю — без мата
    app.login()
    status, data, _ = app.call("GET", query, staff=True)
    groups = data["item"]["texts"]["groups"]
    assert [g["text"] for g in groups] == [RUDE_TEXT] and groups[0]["rude"] is True


def test_clean_complaint_has_no_flag_and_is_unchanged(app):
    created = app.complaint("Не горит фонарь у остановки третий день", "device-author-0003")
    assert created["text"] == "Не горит фонарь у остановки третий день"
    app.login()
    status, data, _ = app.call("GET", f"/api/civic/v2/complaints/{created['id']}", staff=True)
    assert status == 200 and "moderation" not in data["data"]["complaint"]


# --------------------------------------------------------------------------- п. 9
FAR_POINT = [71.4400, 51.1000]       # ~1,8 км от остановки: другая цель


def _heat_counts(app, staff=False):
    status, data, _ = app.call("GET", "/api/civic/v2/heat?bbox=71.40,51.08,71.46,51.11&days=14&zoom=16", staff=staff)
    assert status == 200, data
    return {item["target"]["id"]: item["count"] for item in data["items"] if item.get("count")}


def test_wrong_metoo_is_separated_in_one_action_and_heat_recounts(app):
    if not hasattr(__import__("ui.civic_feedback.v2.store", fromlist=["x"]).ComplaintStore, "separate"):
        pytest.skip("patch R09 п. 9 (r09_polish_r04.patch) ещё не применён")
    original = app.complaint("Разбит павильон остановки, стекло на земле", "device-author-0009")
    here = original["target"]["id"]
    # Житель написал о другой проблеме в другом месте, «Похоже на» ошиблось, он нажал «Я тоже» (текст ушёл с ним).
    note = {"text": "Не горит фонарь во дворе, очень темно вечером", "point": FAR_POINT, "category": "lighting"}
    status, data, _ = app.call("POST", f"/api/civic/v2/complaints/{original['id']}/metoo", {"note": note},
                               device="device-metoo-00000009")
    assert status == 200 and data["data"]["result"] == "added"
    counts = _heat_counts(app)
    assert counts.get(here) == 2 and len(counts) == 1

    # Житель не видит чужих объединений; сотрудник видит и разделяет одним действием.
    status, _, _ = app.call("GET", f"/api/civic/v2/complaints/merged?target_id={here}")
    assert status == 403
    app.login()
    status, data, _ = app.call("GET", f"/api/civic/v2/complaints/merged?target_id={here}", staff=True)
    assert status == 200 and [i["text"] for i in data["data"]["items"]] == [note["text"]]
    item_id = data["data"]["items"][0]["id"]
    status, data, _ = app.call("POST", f"/api/civic/v2/complaints/{item_id}/separate", {}, staff=True)
    assert status == 200, data
    separated = data["data"]["complaint"]
    assert separated["text"] == note["text"] and separated["category"] == "lighting"
    assert separated["target"]["id"] != here and data["data"]["original"]["metoo"] == 0

    counts = _heat_counts(app)                       # обе цели пересчитаны сразу (кэш R07 сброшен событием)
    assert counts == {here: 1, separated["target"]["id"]: 1}
    status, data, _ = app.call("GET", "/api/civic/v2/complaints/mine", device="device-metoo-00000009")
    assert [(i["id"], i["relation"]) for i in data["data"]["items"]] == [(separated["id"], "author")]
    status, data, _ = app.call("POST", f"/api/civic/v2/complaints/{item_id}/separate", {}, staff=True)
    assert status == 409                            # повтор — не вторая жалоба


def test_staff_duplicate_mark_is_undone(app):
    if not hasattr(__import__("ui.civic_feedback.v2.store", fromlist=["x"]).ComplaintStore, "separate"):
        pytest.skip("patch R09 п. 9 (r09_polish_r04.patch) ещё не применён")
    a = app.complaint("Разбит павильон остановки", "device-author-0010")
    b = app.complaint("Не горит фонарь у дома 5", "device-author-0011", point=FAR_POINT, category="lighting")
    app.login()
    status, data, _ = app.call("POST", f"/api/civic/v2/complaints/{b['id']}/duplicate", {"of": a["id"]}, staff=True)
    assert status == 200 and data["data"]["complaint"]["metoo"] == 1
    assert _heat_counts(app) == {a["target"]["id"]: 2}
    status, data, _ = app.call("POST", f"/api/civic/v2/complaints/{b['id']}/separate", {}, staff=True)
    assert status == 200 and data["data"]["complaint"]["duplicate_of"] is None
    assert _heat_counts(app) == {a["target"]["id"]: 1, b["target"]["id"]: 1}
