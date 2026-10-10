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
    "S10": ("R01", "мелочь", "журнал сервера пишет строку запроса с точкой жителя (/targets, /complaints/place)"),
    "S11": ("R07", "важно", "подпись цели из записи жалобы главнее названия OSM: житель переименовывает объект на карте и в «Картине дня»"),
    "S12": ("R09", "важно", "цель жалобы не сверяется с точкой: можно привязать жалобу к любому объекту города"),
    "S13": ("R04", "важно", "/similar отдаёт distance_m до 0,1 м: три запроса восстанавливают точку жителя"),
    "S14": ("R02", "важно", "llm_label отправляет настоящие тексты во внешний API; ФИО, пропущенные обезличиванием, уходят за рубеж"),
    "S15": ("R06", "мелочь", "простые пароли сотрудника «password12345», «Astana2026!!!» проходят: список — 10 точных строк"),
    "S16": ("R05", "мелочь", "id устройства R05 = время + Math.random; R07 перенимает его как ключ к «Мои обращения» R09"),
}
# Исправленные находки: ID -> где исправлено. Их тесты — обычные (регрессия), без xfail: в сборке без исправления
# тест падает — это сигнал, что исправление потеряно.
FIXED = {
    "S09": "R06 ef35fb6 (COOKIE_PATH=/api/civic) и сборка R01 d3c33d9",
    # Ночь 10→11 окт: R01 применил patches R15 в FINAL-кандидат 2b9e837 (ветка claude/sharp-dijkstra-0t87gl);
    # файлы побайтно совпадают с patches/*.diff R15 (проверено R15 на 13ae790).
    **{fid: "FINAL-кандидат R01 2b9e837, patch R15 " + patch for fid, patch in (
        ("S01", "P-R01"), ("S02", "P-R01"), ("S08", "P-R01 (голоса — ещё и R06 681a4ef)"), ("S10", "P-R01"),
        ("S03", "P-R09"), ("S04", "P-R09 + P-R01 (target_lookup)"), ("S05", "P-R09"), ("S06", "P-R09"),
        ("S12", "P-R09 + P-R01 (target_lookup)"), ("S11", "P-R07 (= R07 597ec4f)"), ("S13", "P-R04"),
        ("S07", "P-R02"), ("S14", "P-R02"))},
    "S16": "R05 7f42cb3 (crypto); в сборке R01 с ef1ef44 (R05 169c56b)",
}
# Исправлено в ветке роли, но ещё не в сборке R01: xfail НЕстрогий — в сборке без исправления тест xfail, с ним
# xpass (не падение). Когда R01 возьмёт поставку и тест пройдёт на сборке — ID переезжает в FIXED.
PENDING = {
    "S15": "ветке R06 7b99e6c (P-R06, ночь 10→11 окт)",
}


def xfail(finding_id: str, pending: str | None = None):
    """Открытая находка — xfail(strict); исправленная (FIXED) — обычный тест; PENDING — нестрогий xfail."""
    if finding_id in FIXED:  # исправлено: обычный тест-регрессия (так же в копии R01)
        return lambda test: test
    owner, level, title = FINDINGS[finding_id]
    where = pending or PENDING.get(finding_id)
    if where:
        return pytest.mark.xfail(strict=False, reason=f"R15-{finding_id} ({owner}, {level}): {title} — "
                                                      f"исправлено в {where}, ждёт сборки R01")
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
