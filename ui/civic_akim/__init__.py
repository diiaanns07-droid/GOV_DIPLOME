"""R08 · «Картина дня» для акима (раунд 14, Birge).

Что умеет: summary(date, district) — новые обращения за день и за 7 дней с изменением,
«в работе», «просрочено» (сроки — deadlines.py), «исправлено за неделю», топ-10 горячих мест,
темы и районы (ровно как тепловая карта R07), объекты с отставанием и устаревшие, новые
предложения и голоса (R06), текстовая сводка ru/kk по шаблону (text.py, без LLM, офлайн).
HTTP: api.handle_get → GET /api/civic/v2/akim/summary. Подключение — research/round-14-results/R08/INTEGRATION.txt.
Раунд 15: «Картина дня» 2.0 (блоки соседей R17 / R16 / R13 — blocks.py, neighbors.py), «Ситуационный центр»
board() → GET akim/board, «Картина недели» week() → GET akim/week (только сотрудник). Подключение —
research/round-15-results/R08/INTEGRATION.txt.
"""
from .summary import AkimError, AkimService, board, configure, default_service, summary, week

__all__ = ["AkimError", "AkimService", "board", "configure", "default_service", "summary", "week"]
