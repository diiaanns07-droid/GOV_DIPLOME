"""Последний созданный сервис R17 — для функций соседей в том же процессе (R06, R07, R08, R03, R12).

Шлюз R01 создаёт сервис один раз на процесс (make_service(db_path)); функции из ui.civic_agencies берут его отсюда,
чтобы читать ту же базу, что и маршруты. Сервиса ещё нет — функции отвечают пустым блоком, а не ошибкой (CONTRACT §7).
Ссылка сильная: make_service(db) без сохранения результата тоже делает сервис текущим (так зовут R03 и R08).

Тестам в одном процессе pytest: сервис, созданный тестом (свой шлюз R01/R16 или make_service), остаётся текущим для
следующих тестов. Изоляция — как в tests/civic/R17/conftest.py (monkeypatch _state) или reset() до и после теста.
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


def reset() -> None:
    """Для conftest соседей: забыть текущий сервис R17 (после тестов со своим шлюзом)."""
    register(None)
