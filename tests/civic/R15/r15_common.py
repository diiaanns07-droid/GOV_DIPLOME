"""Общие помощники тестов R15: корень проверяемой сборки, находки, живой сервер R01."""

from __future__ import annotations

import http.client
import importlib
import json
import os
import threading
from contextlib import contextmanager
from pathlib import Path

import pytest

ROOT = Path(os.environ.get("R15_ROOT") or Path(__file__).resolve().parents[3]).resolve()

# Каталог находок: ID -> (роль-владелец, важность, кратко). Полное описание — research/round-14-results/R15/SECURITY_REVIEW.md.
FINDINGS = {
    "S01": ("R01", "важно", "CSP без script-src: XSS в любом модуле выполняется без ограничений"),
    "S02": ("R01", "важно", "API v2 без ограничения частоты: голоса, «Я тоже», жалобы, /classify, /similar"),
    "S03": ("R09", "важно", "публичная выдача жалоб отдаёт точную точку жителя (6 знаков ≈ 10 см)"),
    "S04": ("R09", "важно", "подписи цели (label_ru/label_kk) приходят от жителя и показываются всем"),
    "S05": ("R09", "мелочь", "проверка CSRF в _require_staff молча пропускается, если у principal нет check_csrf"),
    "S06": ("R09", "мелочь", "days из «надстрочных» цифр (²) в /complaints/summary -> 500 вместо 422"),
    "S07": ("R02", "важно", "обезличивание пропускает ФИО с отчеством и «Я, Фамилия Имя» и не отправляет их на ручную проверку"),
    "S08": ("R06/R09", "важно", "один голос / одно «Я тоже» на device_id: новый device_id = новый голос"),
    "S09": ("R01/R06", "важно", "cookie сессии Path=/api/civic/v1: маршруты сотрудника /api/civic/v2 её не получают"),
}


def xfail(finding_id: str):
    owner, level, title = FINDINGS[finding_id]
    return pytest.mark.xfail(strict=True, reason=f"R15-{finding_id} ({owner}, {level}): {title}")


def error_code(payload):
    """Код ошибки из ответа v2 ({"error": "код"}) или v1 ({"ok": false, "error": {"code": "код"}})."""
    error = (payload or {}).get("error")
    return error.get("code") if isinstance(error, dict) else error


def need_module(name: str):
    """Модуль роли из проверяемой сборки или skip с понятной причиной."""
    try:
        return importlib.import_module(name)
    except ModuleNotFoundError as exc:
        if exc.name and (name == exc.name or name.startswith(exc.name + ".")):
            pytest.skip(f"в этой сборке нет модуля {name} ({ROOT})")
        raise


@contextmanager
def live_server(tmp_path, **kwargs):
    """Настоящий ui.web_server на 127.0.0.1:<случайный порт> с временной базой."""
    web_server = need_module("ui.web_server")
    srv = web_server.create_server(project=ROOT, port=0, civic_db=tmp_path / "civic.sqlite3", **kwargs)
    thread = threading.Thread(target=srv.serve_forever, daemon=True)
    thread.start()
    try:
        yield srv
    finally:
        srv.shutdown()
        srv.server_close()


def request(srv, method, path, body=None, headers=None, raw=None):
    """-> (status, заголовки в нижнем регистре, тело bytes). raw — тело как есть (bytes)."""
    port = srv.server_address[1]
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=15)
    hdrs = {"Host": f"127.0.0.1:{port}"}
    data = raw
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        hdrs["Content-Type"] = "application/json"
    hdrs.update(headers or {})
    try:
        conn.request(method, path, body=data, headers=hdrs)
        resp = conn.getresponse()
        return resp.status, {k.lower(): v for k, v in resp.getheaders()}, resp.read()
    finally:
        conn.close()
