"""Последний созданный сервис R17 — для функций соседей в том же процессе (R06, R07, R08, R03, R12).

Шлюз R01 создаёт сервис один раз на процесс (make_service(db_path)); функции из ui.civic_agencies берут его отсюда,
чтобы читать ту же базу, что и маршруты. Сервиса ещё нет — функции отвечают пустым блоком, а не ошибкой (CONTRACT §7).
"""

from __future__ import annotations

import threading

_lock = threading.Lock()
_state: dict = {"service": None}


def register(service) -> None:
    with _lock:
        _state["service"] = service


def current():
    with _lock:
        return _state["service"]
