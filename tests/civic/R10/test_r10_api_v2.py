"""R10 · раунд 15 · pytest-обёртка над api_v2.py (CONTRACT §7) + самопроверка проверки на поддельном сервере.

    python3 -m pytest -q tests/civic/R10/test_r10_api_v2.py              # текущее дерево (сборка R01)
    R10_ROOT=<папка сборки> python3 -m pytest -q tests/civic/R10/test_r10_api_v2.py

Жёсткие правила сборки (любая сборка R01 с маршрутами раунда 15):
  - прежние маршруты FINAL-4 на месте и подключены;
  - ни одного 500 и ни одного Traceback модуля на примерах из интерфейса и на пустом теле;
  - маршрут сотрудника без входа и без CSRF закрыт (401/403);
  - без модуля — 503 module_not_ready с ролью и понятным текстом;
  - приватность §10: в ответах жителю нет устройств, телефонов, ИИН, e-mail; «Я приду» — число.
Отступления от форматов §5 и отказы на примерах — в отчёте api_v2.py (FAIL владельцу), здесь не валят сборку.
"""
from __future__ import annotations

import json
import os
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import api_v2 as A  # noqa: E402
from stand import Client, Reply  # noqa: E402

ROOT = Path(os.environ.get("R10_ROOT") or Path(__file__).resolve().parents[3])


# ------------------------------------------------------------------ правила проверки (без сервера)
def test_routes_table_matches_contract():
    pairs = {(r.method, r.path) for r in A.ROUTES}
    assert len(pairs) == len(A.ROUTES) == 46
    assert {r.role for r in A.ROUTES} == {"R03", "R04", "R06", "R07", "R08", "R09", "R12", "R13", "R16", "R17"}
    assert all(r.who in ("all", "resident", "staff", "author") for r in A.ROUTES)


def test_initiative_format_and_privacy():
    good = {"id": "i-1", "kind": "cleanup", "title": "Субботник", "target": {"kind": "area", "id": "yard-1"},
            "status": "published", "joined": 15, "point": [71.41, 51.10], "starts_at": "2026-10-17T10:00:00+05:00",
            "demo": True, "support": {"pickup_service": "waste"}}
    assert A.check_initiative(good, world=True) == []
    bad = dict(good, kind="party", joined="15", starts_at="2026-10-17T10:00:00", point=[37.6, 55.7],
               support={"pickup_service": "garbage"})
    errors = " ".join(A.check_initiative(bad))
    for part in ("kind=", "joined", "без пояса", "вне Астаны", "pickup_service"):
        assert part in errors
    assert A.privacy_issues({"items": [good]}) == []
    leaks = A.privacy_issues({"items": [dict(good, author_device="dev-123", text="Звоните +7 701 123 45 67"),
                                        {"members": ["dev-1", "dev-2"]}]})
    assert any("устройство" in x for x in leaks) and any("телефон" in x for x in leaks)
    assert any("список людей" in x for x in leaks)
    # id объектов OSM с длинными числами — не ИИН
    assert A.privacy_issues({"target": {"id": "osm-node-123456789012"}, "label": "Двор у дома 5"}) == []
    assert A.privacy_issues({"text": "Мой ИИН 900101300123 пишу сюда"})


def test_incident_meeting_conflict_formats():
    inc = {"id": "inc-1", "kind": "blizzard", "title_ru": "Буран", "title_kk": "Боран",
           "zone": {"kind": "district", "district": "nura"}, "started_at": "2026-10-12T06:00:00+05:00",
           "status": "active", "tasks": [{"service": "street_cleaning", "status": "doing"}],
           "updates": [{"public": True, "text_ru": "…"}], "demo": True}
    assert A.check_incident(inc, world=True) == []
    assert "public: false" in " ".join(A.check_incident(dict(inc, updates=[{"public": False}])))
    assert "не из" in " ".join(A.check_incident(dict(inc, tasks=[{"service": "snow_team", "status": "doing"}])))
    meeting = {"id": "m-1", "title_ru": "Встреча", "title_kk": "Кездесу", "at": "2026-10-20T18:00:00+05:00",
               "registered": 54, "orders": [{"service": "lighting", "status": "todo", "text_ru": "…", "text_kk": "…"}]}
    assert A.check_meeting(meeting) == []
    conflict = {"id": "cf-1", "kind": "dig_after_surface", "works": ["w-1", "w-2"], "severity": "high",
                "advice_ru": "Сначала сети, потом асфальт", "advice_kk": "Алдымен желілер, сосын асфальт"}
    assert A.check_conflict(conflict) == []
    assert A.check_conflict(dict(conflict, works=["w-1"]))


def test_understandable_error():
    reply = lambda body: Reply(400, body)  # noqa: E731
    assert A.understandable(reply({"error": "not_found", "message": "Запись не найдена."}))[0]
    assert not A.understandable(reply({"error": "internal", "message": "Traceback (most recent call last)"}))[0]
    assert not A.understandable(reply({"error": "bad_request", "message": "field required"}))[0]
    assert A.understandable(reply({"ok": False, "error": {"code": "forbidden", "message": "Нет прав."}}))[0]


# ------------------------------------------------------------------ самопроверка на поддельном сервере
class _Fake(BaseHTTPRequestHandler):
    """Шлюз раунда 15 «как надо» для R16 и R04 и «как не надо» для одного маршрута R17 (открыт без входа)."""

    joined = {"dev": set()}

    def log_message(self, *a):
        pass

    def _send(self, status, body, allow=None):
        raw = json.dumps(body, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        if allow:
            self.send_header("Allow", allow)
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def _route(self):
        path = self.path.split("?")[0]
        rel = path[len(A.V2) + 1:] if path.startswith(A.V2 + "/") else None
        return path, rel

    def do_DELETE(self):
        path, rel = self._route()
        if rel is None:
            return self._send(404, {"error": "not_found", "message": "Адрес API не найден."})
        if rel.startswith("together/") or rel in ("route", "moderate", "agencies/board"):
            return self._send(405, {"error": "method_not_allowed", "message": "Метод не поддерживается."},
                              allow="GET,POST")
        if rel.startswith("incidents"):
            return self._send(405, {"error": "method_not_allowed", "message": "Метод не поддерживается."},
                              allow="GET,POST")
        return self._send(404, {"error": "not_found", "message": "Адрес API не найден."})

    def _initiative(self):
        return {"id": "i-1", "kind": "cleanup", "title": "Субботник", "target": {"kind": "area", "id": "yard-1"},
                "status": "published", "joined": 14 + len(self.joined["dev"]), "demo": True}

    def do_GET(self):
        path, rel = self._route()
        if path == A.V2 + "/modules":
            base = json.loads(A.FINAL4_MODULES.read_text(encoding="utf-8"))["modules"]
            return self._send(200, {"modules": {k: {"status": v} for k, v in base.items()}})
        if rel == "together/initiatives":
            return self._send(200, {"items": [self._initiative()]})
        if rel == "together/initiatives/i-1":
            return self._send(200, {"initiative": self._initiative()})
        if rel and rel.startswith("together/initiatives/"):
            return self._send(404, {"error": "not_found", "message": "Инициатива не найдена."})
        if rel and rel.startswith("together/yards/"):
            return self._send(200, {"id": "yard-1", "label_ru": "Двор", "label_kk": "Аула", "members": 37,
                                    "captain": None})
        if rel == "together/updates":
            if not self.headers.get("X-Birge-Device"):
                return self._send(400, {"error": "device_required", "message": "Нужно устройство жителя."})
            return self._send(200, {"events": []})
        if rel == "agencies/board":  # дефект для самопроверки: табло сотрудника открыто всем
            return self._send(200, {"rows": [{"service": "water", "open": 3}]})
        if rel and rel.startswith("incidents"):
            return self._send(503, {"error": "module_not_ready", "message": "Эта часть ещё не подключена в сборке.",
                                    "module": "ui.civic_agencies", "role": "R17"})
        return self._send(404, {"error": "not_found", "message": "Адрес API не найден."})

    def do_POST(self):
        path, rel = self._route()
        length = int(self.headers.get("Content-Length") or 0)
        body = json.loads(self.rfile.read(length) or b"{}")
        device = self.headers.get("X-Birge-Device")
        staff = "r10" in (self.headers.get("Cookie") or "")
        if rel == "complaints":
            return self._send(503, {"error": "module_not_ready", "message": "Эта часть ещё не подключена.",
                                    "module": "x", "role": "R09"})
        if rel and rel.startswith("incidents"):
            return self._send(503, {"error": "module_not_ready", "message": "Эта часть ещё не подключена в сборке.",
                                    "module": "ui.civic_agencies", "role": "R17"})
        if rel in ("route", "moderate"):
            if not body.get("text"):
                return self._send(400, {"error": "bad_request", "message": "Нужен текст."})
            if rel == "route":
                return self._send(200, {"services": [{"service": "water"}, {"service": "road"}], "joint": True})
            return self._send(200, {"flags": ["phone", "iin", "email"]})
        if rel and rel.startswith("together/"):
            if rel.endswith(("/support", "/moderate", "/report")):
                if not staff:
                    return self._send(401, {"error": "unauthenticated", "message": "Войдите как сотрудник."})
                if not self.headers.get("X-CSRF-Token"):
                    return self._send(403, {"error": "csrf_failed", "message": "Неверный CSRF-токен."})
                return self._send(400, {"error": "bad_request", "message": "Неверные данные."})
            if not device:
                return self._send(400, {"error": "device_required", "message": "Нужно устройство жителя."})
            if rel == "together/initiatives/i-1/join":
                self.joined["dev"].add(device)
                return self._send(200, {"joined": 14 + len(self.joined["dev"])})
            if rel == "together/initiatives/i-1/leave":
                self.joined["dev"].discard(device)
                return self._send(200, {"joined": 14 + len(self.joined["dev"])})
            if rel == "together/initiatives":
                return self._send(201, {"initiative": dict(self._initiative(), id="i-2", status="on_review")})
            return self._send(200, {"ok": True, "data": {"members": 38}})
        if path == "/api/civic/v1/session/login":
            raw = json.dumps({"ok": True, "data": {"csrf_token": "t"}}).encode()
            self.send_response(200)
            self.send_header("Set-Cookie", "civic_session=r10; Path=/")
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            return self.wfile.write(raw)
        return self._send(404, {"error": "not_found", "message": "Адрес API не найден."})


class _FakeStand:
    def __init__(self):
        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), _Fake)
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()
        self.base = f"http://127.0.0.1:{self.httpd.server_address[1]}"
        self.staff = ("r10", "pw")
        self.log = ""

    def client(self, device=None):
        return Client(self.base, device=device)

    def tracebacks(self, since=0):
        return []


def test_checker_on_fake_gateway():
    stand = _FakeStand()
    try:
        check = A.ApiCheck(stand, world=True).run()
    finally:
        stand.httpd.shutdown()
    rows = check.rows
    fail = [r for r in rows if r["status"] == "FAIL"]
    names = " | ".join(r["name"] for r in fail)
    # маршрутов R09/R12/R07/R08(часть)/R13/R03/R06 в поддельном шлюзе нет — FAIL владельцу R01
    assert any(r["owner"] == "R01" and "complaints/{complaint}/handoff" in r["name"] for r in fail)
    # табло служб открыто без входа — FAIL доступа
    assert "GET agencies/board: без входа" in names
    # R17 кризисы без модуля — 503 module_not_ready: PASS
    assert any(r["status"] == "PASS" and "incidents" in r["name"] and "503" in r["name"] for r in rows)
    # «Я приду» дважды с одного устройства → +1, «Не приду» → обратно
    assert any(r["status"] == "PASS" and "дважды с одного устройства" in r["name"] for r in rows)
    assert any(r["status"] == "PASS" and "обратно" in r["name"] for r in rows)
    # житель без устройства — отказ с понятным текстом
    assert any(r["status"] == "PASS" and "без X-Birge-Device" in r["name"] for r in rows)
    # формат инициатив и маршрутизации проверен
    assert any(r["status"] == "PASS" and r["area"] == "формат" and "together/initiatives" in r["name"] for r in rows)
    assert any(r["status"] == "PASS" and r["area"] == "формат" and "POST route" in r["name"] for r in rows)
    assert check.state[("GET", "incidents")] == "not_ready"
    assert check.state[("GET", "together/initiatives")] == "ready"


# ------------------------------------------------------------------ сборка
@pytest.fixture(scope="module")
def result():
    return A.run(ROOT, world=True)


def _fails(result, *areas):
    return [r for r in result["rows"] if r["status"] == "FAIL" and (not areas or r["area"] in areas)]


def test_final4_routes_kept(result):
    bad = [r for r in result["rows"] if r["area"] == "FINAL-4" and r["status"] == "FAIL"]
    assert not bad, bad


def _need_round15(result):
    if all(v["not_registered"] == v["routes"] for v in result["by_role"].values()):
        pytest.skip("маршрутов раунда 15 нет в шлюзе этой сборки (FINAL-4 или R01 ещё не добавил) — NOT_RUN")


def test_round15_routes_registered(result):
    _need_round15(result)
    missing = [r["name"] for r in _fails(result, "§7") if r["owner"] == "R01" and "нет в шлюзе" in str(r["detail"])]
    assert not missing, missing


def test_no_crash_and_no_traceback(result):
    _need_round15(result)
    crash = [r for r in _fails(result, "ошибки", "ответ", "журнал")
             if r["area"] == "журнал" or any(f"→ {c}" in r["name"] for c in range(500, 600)) or "→ 0" in r["name"]]
    assert not crash, crash


def test_staff_routes_closed(result):
    _need_round15(result)
    opened = _fails(result, "доступ")
    assert not opened, opened


def test_module_not_ready_answer(result):
    _need_round15(result)
    bad = [r for r in _fails(result, "§7") if "503" in r["name"] or "упал" in r["name"]]
    assert not bad, bad


def test_privacy_in_public_answers(result):
    _need_round15(result)
    leaks = [r for r in _fails(result, "формат", "поведение")
             if any(w in json.dumps(r["detail"], ensure_ascii=False) for w in ("устройство", "телефон", "ИИН", "e-mail",
                                                                                 "список людей"))
             or "дважды с одного устройства" in r["name"]]
    assert not leaks, leaks
