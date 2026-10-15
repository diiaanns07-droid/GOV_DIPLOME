"""Birge · ML-API (R04): подсказка категории, похожие обращения, службы, черновик ответа, модерация. Без сети и GPU.

Функции для шлюза R01 (ui/web_server.py, таблица V2_HANDLERS):
    classify(text)                         -> POST /api/civic/v2/classify                 (раунд 14)
    similar(text, point=None, days=None)   -> POST /api/civic/v2/similar                  (раунд 14)
    route(text?, category?, subtopic?, point?, body?)  -> POST /api/civic/v2/route        (раунд 15, все)
    moderate(text, lang?, body?)           -> POST /api/civic/v2/moderate                 (раунд 15, предпросмотр, все)
Для соседей — вызов в процессе (раунд 15):
    moderate(text) -> {text_public, flags, clean, action}  — R16 инициативы, R13 вопросы, R17 обновления кризиса;
    route_hint(route(...)) -> поле route_hint жалобы R09 (CONTRACT §5.1);
    similar_initiatives(text, point, days) -> {items:[{id, score, distance_m, …}]} — R16 «Присоединиться к существующей».
Подключение при старте сервера (INTEGRATION.txt):
    connect_store(store)    — хранилище жалоб R09 для similar() (+ фоновый прогрев кэша признаков);
    warmup()                — загрузить модели заранее (в фоне), чтобы первый запрос жителя был быстрым.
Диагностика: status() — какие модели загружены и почему нет остальных; журнал решений акимата о дублях (п. 9).
Фильтр мата для публичных выводов (п. 8): ui.civic_ml_api.profanity (mask, check, mask_json, moderation).
"""

from __future__ import annotations

import threading

from ml.civic_dedup import deduper_info
from ml.civic_dedup import reset as _reset_dedup
from ui.civic_ml_api import classify_chain as _classify_mod
from ui.civic_ml_api.classify_chain import classify
from ui.civic_ml_api.errors import MLServiceUnavailable
from ui.civic_ml_api.initiatives import set_initiative_source, similar_initiatives
from ui.civic_ml_api.moderation import moderate, moderation_record, public_text
from ui.civic_ml_api.routing import route, route_hint
from ui.civic_ml_api.similar_search import (connect_store, feedback_stats, records_source, set_complaint_source,
                                            similar, source_kind, warm_cache)

__all__ = ["MLServiceUnavailable", "classify", "connect_store", "moderate", "moderation_record", "public_text",
           "records_source", "reset", "route", "route_hint", "set_complaint_source", "set_initiative_source", "similar",
           "similar_initiatives", "status", "warm_cache", "warmup"]


def status() -> dict:
    """Состояние для R01/R10: цепочка classify, метод поиска дублей, подключён ли источник жалоб."""
    return {"classify": {"model_version": _classify_mod.CHAIN.version(), "models": _classify_mod.CHAIN.status()},
            "similar": {**deduper_info(), "source": source_kind() or "not_connected",
                        "feedback": feedback_stats()}}


def warmup(background: bool = True):
    """Загрузить модели и прогнать по одному тексту. background=True — в отдельном потоке (не задерживает старт)."""
    def run():
        classify("Во дворе не горят фонари")
        route(text="Яма после раскопок водоканала")
        moderate("Проверка модерации")
        deduper_info()
        warm_cache()  # если хранилище уже подключено

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
