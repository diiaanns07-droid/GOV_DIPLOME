# BUILD раунд 9 — STATUS

Ветка `claude/beautiful-clarke-sbzomj`; стартовая база `d865dd4` (код = `3e1302a`); входы `codex/research-import-2026-10-05 @ 0ab1667`
(`research/round-9/START_HERE, REVIEW, CORE_SPEC, BUILD, snapshots.json`). Пины чужих пакетов — по `snapshots.json`.

## Этап 1 — дефекты r8 и сверка сборки: ГОТОВ (код `e990f01`)
- Прочитаны K07 r8 (STATUS, REVIEW_BUILD, патч), K12 r8 (FIX_PROPOSALS, патч), K11 r8 (INTEGRATION, патч MIME), K06 r8 (HANDOFF, gold), K10 r8 (HANDOFF, packs).
- Все находки воспроизведены на своём коде до исправления; исправлены — см. `ISSUE_LOG.md` (9 пунктов + намеренные различия политики).
  - Патч K07 применён после чтения (`git apply`, sha256 14335f10…), дополнен: фокус при скрытой цели и переполнение карточки на 390 px.
  - K12: вместо 3-строчной заглушки — валидация во всех публичных входах (требование r9 CORE_SPEC).
  - K11: явные MIME + понятное сообщение о занятом порте; Windows — только модель.
- Независимые оракулы подключены собственным адаптером `adapters/r8_independent.cjs` (их код не исполнялся; байтовые копии и sha256 — `review_inputs/MANIFEST.json`):
  K06 gold 96/96 PASS; K10 packs 288 PASS + 4 INFO (намеренные различия политики), 0 FAIL — `r8_independent_result.json`.

| Проверка (Linux, Node 22, Chromium headless) | Результат |
|---|---|
| `check_all.py` (venv shapely/pyproj) | 18/18 PASS (unittest включает новый `test_serve.py`) |
| `tests/plan.cjs` | 164/164 |
| `tests/whatif.cjs` | 71/71 |
| `tests/plan_keyboard.cjs` (новый) | 14/14 (на базе d865dd4: 9 FAIL — `repro_k07_on_d865dd4.txt`) |
| `plan_smoke` / `whatif_smoke` / `smoke` | 52/52 · 32/32 · 24/24 |

## Дальше
Этап 2 — ядро устойчивости `web/resilience.js` (city-resilience-v1) + независимый Python-оракул.
