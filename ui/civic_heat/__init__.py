"""R07 · Тепловая карта объектов и «Хроника города» (раунды 14–15, Birge).

Что умеет: вес и уровень каждой цели жалоб (объект / участок улицы / двор-квартал), состояние
«исправлено» на 7 дней, сводка по районам для мелкого масштаба, ответ GET /api/civic/v2/heat;
раунд 15 — GET /heat/replay (кадры по дням той же формулой, replay.py), один источник в демо-мире
(world.py: при CIVIC_DEMO_WORLD=1 только база R09) и seed_world — отметки шкалы хроники.
Правила — CONTRACT §6–§7 и engine.py. Подключение к серверу — research/round-15-results/R07/INTEGRATION.txt.
"""
from .config import load_config
from .service import HeatError, HeatService, configure, default_service, invalidate
from .world import seed_world, world_mode

__all__ = ["HeatError", "HeatService", "configure", "default_service", "invalidate", "load_config", "seed_world",
           "world_mode"]
