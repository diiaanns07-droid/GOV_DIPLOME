"""R17 · изоляция тестов от общего состояния модуля в одном процессе pytest (просьба R01, STATUS B0.2).

ui.civic_agencies держит на процесс: последний сервис (api_state — для функций соседей), связь с записями R09
(sources.configure — её ставит шлюз R01) и кэш хранилищ R09 по пути базы. В полном прогоне сборки до тестов R17
идут тесты шлюза R01, R10, R15, R16 — они связывают табло с чужими записями; а сервисы, созданные тестами R17,
иначе остались бы «текущими» для тестов соседей (R07 видел лишнюю отметку кризиса). Каждый тест R17 начинает с
чистого состояния, а после него monkeypatch возвращает прежнее — в обе стороны ничего не утекает.
"""

import pytest

from ui.civic_agencies import api_state, sources


@pytest.fixture(autouse=True)
def _isolated_agencies_state(monkeypatch):
    monkeypatch.setattr(api_state, "_state", {"service": None})
    monkeypatch.setattr(sources, "_configured", {"records": None})
    monkeypatch.setattr(sources, "_stores", {})
    yield
