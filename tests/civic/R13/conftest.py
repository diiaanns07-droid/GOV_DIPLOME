"""R13: тесты со шлюзом R01 (qa/test_r13_qa.py, meetings/test_r13_meetings_gateway.py, test_r13_gateway_r01.py) вызывают
CivicV2Gateway с wire(). Шлюз делает сервисы ролей текущими для процесса и настраивает модули соседей на временную базу теста:
карта R07 (civic_heat), «Картина дня» R08 (civic_akim), табло и сервис R17 (civic_agencies: sources, api_state), привязка R06
(civic_store.v2), поиск похожих R04 (civic_ml_api). В одном процессе pytest это доставалось тестам, которые идут следом
(R01 B0.20: 6 FAIL у tests/civic/R03/round15, если тесты R13 шли раньше). Поэтому после каждого теста R13 состояние соседей
возвращается к тому, что было до него (модуль не был загружен — к начальному), как советует ui/civic_agencies/api_state.py."""
import sys

import pytest

# (модуль, атрибут) — объект по умолчанию, который заменяет configure(): None — начальное состояние модуля.
_DEFAULTS = (("ui.civic_heat.service", "_default"), ("ui.civic_akim.summary", "_default"), ("ui.civic_store.v2", "_BOUND"))
# (модуль, атрибут-словарь) -> начальное содержимое словаря (если до теста модуль не был загружен).
_DICTS = {("ui.civic_agencies.sources", "_configured"): {"records": None},
          ("ui.civic_agencies.api_state", "_state"): {"service": None}}


def _snapshot():
    state = {key: getattr(sys.modules.get(key[0]), key[1], None) for key in _DEFAULTS}
    for key, initial in _DICTS.items():
        current = getattr(sys.modules.get(key[0]), key[1], None)
        state[key] = dict(current) if isinstance(current, dict) else dict(initial)
    similar = sys.modules.get("ui.civic_ml_api.similar_search")
    state["similar"] = dict(getattr(similar, "_source", None) or {})
    return state


def _restore(state):
    for name, attr in _DEFAULTS:
        module = sys.modules.get(name)
        if module is not None and hasattr(module, attr):
            setattr(module, attr, state[(name, attr)])
    for name, attr in _DICTS:
        current = getattr(sys.modules.get(name), attr, None)
        if isinstance(current, dict) and current != state[(name, attr)]:
            current.clear()
            current.update(state[(name, attr)])
    similar = sys.modules.get("ui.civic_ml_api.similar_search")
    source = getattr(similar, "_source", None)
    if isinstance(source, dict) and source.get("src") is not state["similar"].get("src"):
        unsubscribe = source.get("unsubscribe")
        if callable(unsubscribe) and unsubscribe is not state["similar"].get("unsubscribe"):
            try:
                unsubscribe()  # отписка от временного хранилища теста
            except Exception:  # noqa: BLE001 — чужой модуль; сбой отписки не должен ронять тест R13
                pass
        source.clear()
        source.update(state["similar"])


@pytest.fixture(autouse=True)
def _restore_neighbor_wiring():
    state = _snapshot()
    yield
    _restore(state)
