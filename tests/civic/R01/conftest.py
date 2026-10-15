"""R01: тесты шлюза связывают модули ролей так же, как сервер (CivicV2Gateway.wire). Часть связей — настройка уровня
модуля: R17 ui.civic_agencies.configure(records=…) запоминает записи R09 шлюза. После теста шлюза эта настройка не
должна доставаться тестам ролей, которые идут следом в том же процессе pytest (B0.2: тест R17 agencies_week видел
записи тестового хранилища R01 вместо своей фикстуры). Поэтому после каждого теста R01 связь снимается."""
import sys

import pytest


@pytest.fixture(autouse=True)
def _release_neighbor_wiring():
    yield
    agencies = sys.modules.get("ui.civic_agencies")
    configure = getattr(agencies, "configure", None)
    if callable(configure):
        try:
            configure(records=None)
        except Exception:  # noqa: BLE001 — чужой модуль; сбой сброса не должен ронять тест R01
            pass
