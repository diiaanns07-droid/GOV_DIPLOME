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

## Этап 2 — точный оптимизатор: ГОТОВ
- `plan.js`: createSearch (предвычисленная матрица мм, перебор всех 2^free ≤ 65 536 подмножеств, отсечение по max_selected и бюджету,
  проверка обязательных до перебора → infeasible с причиной), три цели (mean / minimax / coverage) с лексикографическими ключами и
  ничьей по отсортированным ID, Парето (cost, weighted_sum_mm) только для полных планов, статусы optimal / infeasible / cancelled / incomplete,
  optimizePlans (синхронно, для Node), sensitivity [0, ⌊B/2⌋, B].
- UI: поиск чанками по 2048 наборов через event loop (Web Worker не используется: со страницы file:// он не запускается),
  прогресс «просмотрено N из M», «Отменить поиск», request_id + problem_digest — поздний или устаревший ответ отбрасывается,
  изменение параметров обесценивает результат; таблица «Текущий / Среднее / Худшая точка / Охват» с пометкой одинаковых планов;
  «Применить» только по нажатию, «Вернуть ручной план».
- Длинные списки (25 точек / 16 кандидатов) свёрнуты в разделы.

Проверки этапа 2: `tests/plan.cjs` 141/141 (оптимизатор = оракул на 15 наборах, порядок входа, чувствительность, чанки, отмена,
неполный ≠ optimal, digest); `plan_smoke.cjs` 38/38 (16×25 в браузере ≈0,7 с вместе с чувствительностью на этой машине);
check_all 18/18; smoke 24/24; whatif_smoke 32/32.

## Дальше
Этап 3 — объяснение, Парето/чувствительность в UI, экспорт/импорт v2, HTML-отчёт.
