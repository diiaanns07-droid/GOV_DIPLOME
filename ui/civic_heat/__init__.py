"""R07 · Тепловая карта объектов (раунд 14, Birge).

Что умеет: вес и уровень каждой цели жалоб (объект / участок улицы / двор-квартал), состояние
«исправлено» на 7 дней, сводка по районам для мелкого масштаба, ответ GET /api/civic/v2/heat.
Правила — CONTRACT §6–§7 и engine.py. Подключение к серверу — research/round-14-results/R07/INTEGRATION.txt.
"""
from .config import load_config
from .service import HeatError, HeatService, configure, default_service, invalidate

__all__ = ["HeatError", "HeatService", "configure", "default_service", "invalidate", "load_config"]
