"""R16: тесты шлюза R01 (test_r16_gateway.py) поднимают настоящий CivicV2Gateway. В полном прогоне pytest сборки R01
модули ролей живут в одном процессе, и настройка уровня модуля R17 (ui.civic_agencies.configure(records=…)) не должна
доставаться тестам соседей, которые идут следом (просьба R01 в STATUS раунда 15, как conftest R01). После каждого теста
R16 связь снимается; R17 в сборке нет — ничего не делаем."""
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
        except Exception:  # noqa: BLE001 — чужой модуль; сбой сброса не должен ронять тест R16
            pass
