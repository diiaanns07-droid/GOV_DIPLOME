"""Birge · ML-API (R04, раунд 14): подсказка категории и поиск похожих обращений, без сети и видеокарты.

Функции для шлюза R01 (ui/web_server.py, таблица V2_HANDLERS — имена уже совпадают):
    classify(text)                         -> POST /api/civic/v2/classify
    similar(text, point=None, days=None)   -> POST /api/civic/v2/similar
Подключение при старте сервера (INTEGRATION.txt):
    connect_store(store)    — хранилище жалоб R09 для similar();
    warmup()                — загрузить модели заранее (в фоне), чтобы первый запрос жителя был быстрым.
Диагностика: status() — какие модели загружены и почему нет остальных.
"""

from __future__ import annotations

import threading

from ml.civic_dedup import deduper_info
from ml.civic_dedup import reset as _reset_dedup
from ui.civic_ml_api import classify_chain as _classify_mod
from ui.civic_ml_api.classify_chain import classify
from ui.civic_ml_api.errors import MLServiceUnavailable
from ui.civic_ml_api.similar_search import connect_store, records_source, set_complaint_source, similar, source_kind

__all__ = ["MLServiceUnavailable", "classify", "connect_store", "records_source", "reset", "set_complaint_source",
           "similar", "status", "warmup"]


def status() -> dict:
    """Состояние для R01/R10: цепочка classify, метод поиска дублей, подключён ли источник жалоб."""
    return {"classify": {"model_version": _classify_mod.CHAIN.version(), "models": _classify_mod.CHAIN.status()},
            "similar": {**deduper_info(), "source": source_kind() or "not_connected"}}


def warmup(background: bool = True):
    """Загрузить модели и прогнать по одному тексту. background=True — в отдельном потоке (не задерживает старт)."""
    def run():
        classify("Во дворе не горят фонари")
        deduper_info()

    if not background:
        run()
        return None
    thread = threading.Thread(target=run, name="civic-ml-warmup", daemon=True)
    thread.start()
    return thread


def reset() -> None:
    """Для тестов: забыть загруженные модели и источник жалоб."""
    _classify_mod.CHAIN = _classify_mod._Chain()
    _reset_dedup()
    set_complaint_source(None)
