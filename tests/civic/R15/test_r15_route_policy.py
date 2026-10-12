"""R15: правила таблицы маршрутов шлюза R01 — сторож для новых разделов (идеи R06, «Вопрос акиму» R13 и следующих).

Тест читает ui.web_server.V2_ROUTES / V2_HANDLERS / V2_RATE_LIMITS сборки и проверяет правила, которые раньше
нарушались по одному (S02, S08, S17, S29):
1. Запись жителя (POST/PUT/DELETE без пометки staff) — с лимитом запросов по адресу: голос, подписка, вопрос, идея.
   Модуль-«сервис» (R09) проверяет сотрудника сам; его запись жителя тоже должна быть в V2_RATE_LIMITS,
   кроме безвредных действий над своей записью (ALLOW_UNLIMITED).
2. Решения и модерация — только сотрудник (staff=True: сессия R02 + CSRF): approve, reject, decide, moderate, hide,
   answer, publish, stage, routing и т. п. Для «сервиса» R09 это проверяют HTTP-тесты test_r15_gateway_wave2.py.
3. Чтение очередей модерации и скрытого — только сотрудник.
Новые маршруты попадают под проверку сами, как только R01 добавит их в таблицу.
"""

from __future__ import annotations

import re

import pytest

from r15_common import need_module

# Действия жителя над своей записью без усиления (не голос, не текст, не файл): лимит не обязателен.
ALLOW_UNLIMITED = {"complaints.unsubscribe"}
# Статус, дубль, паспорт, обновление, разъединение у R09 — «сервис» сам требует сотрудника (тест через HTTP).
SERVICE_STAFF_CHECKED = {"complaints.status", "complaints.duplicate", "complaints.passport", "complaints.update",
                         "complaints.unduplicate", "complaints.separate"}
STAFF_WORDS = re.compile(r"approve|reject|withdraw|decid|decision|moderat|hide|hidden|block|ban|answer|publish|stage"
                         r"|routing\.update|feasib|merge|separate|unduplicate|passport|status|duplicate|update")
STAFF_READ_WORDS = re.compile(r"moderat|queue|hidden|inbox|staff|pending")


@pytest.fixture()
def table():
    web_server = need_module("ui.web_server")
    if not hasattr(web_server, "V2_ROUTES"):
        pytest.skip("в этой сборке нет шлюза /api/civic/v2 (R01)")
    return web_server


def _routes(ws, methods):
    for method, pattern, key in ws.V2_ROUTES:
        if method in methods:
            yield method, "/".join(pattern), key, ws.V2_HANDLERS.get(key)


def test_resident_writes_are_rate_limited(table):
    missing = [f"{m} {p} ({k})" for m, p, k, h in _routes(table, {"POST", "PUT", "PATCH", "DELETE"})
               if h is not None and not h.staff and k not in SERVICE_STAFF_CHECKED and k not in ALLOW_UNLIMITED
               and k not in table.V2_RATE_LIMITS]
    assert not missing, "запись жителя без лимита по адресу (V2_RATE_LIMITS):\n" + "\n".join(missing)


def test_decisions_and_moderation_are_staff_only(table):
    open_routes = [f"{m} {p} ({k})" for m, p, k, h in _routes(table, {"POST", "PUT", "PATCH", "DELETE"})
                   if h is not None and STAFF_WORDS.search(k) and not h.staff
                   and not (h.kind == "service" and k in SERVICE_STAFF_CHECKED)]
    assert not open_routes, "решение/модерация без staff=True (сессия + CSRF):\n" + "\n".join(open_routes)


def test_moderation_queues_are_staff_only(table):
    open_reads = [f"GET {p} ({k})" for _m, p, k, h in _routes(table, {"GET"})
                  if h is not None and STAFF_READ_WORDS.search(k) and not h.staff and h.kind != "service"
                  and not getattr(h, "staff_view", False)]
    assert not open_reads, "очередь модерации/скрытое читается без входа:\n" + "\n".join(open_reads)


def test_every_route_has_a_handler(table):
    """Маршрут без обработчика — 500 вместо понятного 503; и правила выше его бы не увидели."""
    assert not [k for _m, _p, k in table.V2_ROUTES if k != "modules" and k not in table.V2_HANDLERS]
