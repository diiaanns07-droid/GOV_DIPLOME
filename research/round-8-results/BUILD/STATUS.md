# BUILD раунд 8 — STATUS

Ветка `claude/beautiful-clarke-sbzomj`; база a5b5e2d (код = проверенный 4e93f30 раунда 7).
Входы: `codex/research-import-2026-10-05 @ c3f6c00` — `research/round-8/CORE_SPEC.txt`, `BUILD.txt`, `snapshots.json`.
Модули других агентов не интегрировались (CORE_SPEC достаточна; работа на собственных synthetic fixtures и существующих срезах).

## Этап 0 — baseline a5b5e2d (Linux, перед изменениями)
check_all 16/16, smoke 24/24, whatif_smoke 32/32, whatif.cjs 66/66 — PASS. Дефектов импорта/подмены source v1 не найдено
(snapshot v1 привязан к release, sha256 файла мест и placesDigest; чужой snapshot отклоняется тестами).

## Этап 1 — многообъектный сценарий: ГОТОВ
- `web/plan.js` — city-plan-v2: makeContext (замороженные копии записей), validatePlanScenario (typed errors), evaluatePlan,
  source_snapshot v2 = sha256(schema, город, release, sha256 файла мест, placesDigest, metric haversine-mm-v1),
  problem_digest (без selected_ids, не зависит от порядка массивов), scenario_digest (+ selected_ids).
- `tools/plan_oracle.py` — независимый Python-оракул (itertools, кортежи, перебор доминирования) → `tests/expected_plans.json`
  (11 синтетических ручных случаев + 4 синтетических набора на реальных срезах, в т.ч. 16×25 в обоих городах).
- `web/plan-ui.js` + хуки в `web/app.js` — переключатель «Один объект (v1) / Несколько объектов (v2)»; v1 не тронут и сохраняет своё состояние.
  Редактор: до 25 точек с весами, до 16 кандидатов со стоимостью, бюджет / максимум / радиус, обязателен/исключён,
  ручной план с допустимостью и причинами, таблица до/после по точкам, перенос/удаление кандидата, синтетический демо-набор с подписью.

Проверки этапа 1 (Linux, Node, Chromium headless, file://): check_all 18/18 PASS (новый шаг plan: оракул свежий + `tests/plan.cjs` 75);
`plan_smoke.cjs` 26/26; `smoke.cjs` 24/24; `whatif_smoke.cjs` 32/32.

## Дальше
Этап 2 — точный оптимизатор (перебор ≤65536, три цели, Парето, отмена/устаревание, применение).
