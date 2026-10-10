"""R08 · «Картина дня» для акима (раунд 14, Birge).

Что умеет: summary(date, district) — новые обращения за день и за 7 дней с изменением,
«в работе», «просрочено» (сроки — deadlines.py), «исправлено за неделю», топ-10 горячих мест,
темы и районы (ровно как тепловая карта R07), объекты с отставанием и устаревшие, новые
предложения и голоса (R06), текстовая сводка ru/kk по шаблону (text.py, без LLM, офлайн).
HTTP: api.handle_get → GET /api/civic/v2/akim/summary. Подключение — research/round-14-results/R08/INTEGRATION.txt.
"""
from .summary import AkimError, AkimService, configure, default_service, summary

__all__ = ["AkimError", "AkimService", "configure", "default_service", "summary"]
