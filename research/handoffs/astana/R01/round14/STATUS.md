# R01 — раунд 14 (Birge): интегратор

Роль: R01 Интегратор. Аккаунт b1 (s10), продолжение — b12 (s4).
Ветка: `claude/sharp-dijkstra-0t87gl` (ветка сессии). База: `claude/round-14-package` @ af77b78.
Свои пути: web/index.html, web/style.css, web/map.js, web/interface.js, web/civic/shell/, ui/web_server.py,
tests/civic/R01/; результаты research/round-14-results/R01/; этот файл.

## Checkpoint 1 — PARTIAL: перенос модулей раунда 13 (без патчей)
- DONE: перенесены пути с закреплённых SHA CONTRACT §1 (path-scoped `git checkout <sha> -- <пути>`, без merge).
  Таблица — research/round-14-results/R01/BUILD_LOG.md.
- Проверено: у R06/R07/R09 (ветки от старого main) пути побитно равны `56538a3 + их *_vs_56538a3.patch`.

## Checkpoint 2 — DONE: база I0
- I0 = коммит «R01 r14 I0» (SHA — в сообщении коммита/следующем checkpoint; ищите `git log --grep "R01 r14 I0"`).
- Патчи раунда 13 перенесены (2 как есть, 5 вручную, 4 устарели) — BUILD_LOG.md, раздел «шаг 2».
- Проверки на I0: pytest 1384 passed / 12 skipped / 0 failed; браузер P0 59/0/2 NOT_RUN, сценарии 16/0,
  город 81/0, пустой реестр 15/0; node-наборы PASS.
- Договор функций API v2 для ролей — research/round-14-results/R01/INTEGRATION.txt (§1).

## Важно про ветку
Сессия R01 запущена до правила «claude/r14-<роль>» (пакет 7ff639a). Инструкция этой сессии — работать и пушить
только в `claude/sharp-dijkstra-0t87gl`. Поэтому ветка R01 сейчас — `claude/sharp-dijkstra-0t87gl`; зеркало в
`claude/r14-R01` — только по разрешению владельца.

- Дальше: каркас API v2 (маршруты + 503 module_not_ready) → шапка Birge (ҚАЗ/РУС, Акимат/Житель, Карта/Картина дня).
