# K05 round 10 — сравнение мест и понятное обоснование (HANDOFF)

Роль: K05. Ветка: claude/optimistic-davinci-1oiqs9 (продолжено от закреплённого eb4ad7bdacc96d0207a5b17f9ee59eb0db7e6724;
роль передана владельцем этой сессии; после закрепления в ветку никто не писал; push только fast-forward, без force).
Пакет заданий: origin/codex/govtech-main-interface @ 7c6fb75ec66c50627af62b9d0d8e94c1f09bee16, research/round-10/.
Кодовая база: d2ff344c5ec9b9a729ea59df50ec81f981e619de (web/govtech/core/plan.js, whatif.js, facts.js).
Основной код не менялся: всё — patch/модуль/тесты в этой папке; интегрирует BUILD (K04).

## Этап 1 — минимальный patch + адаптер + независимая проверка (готово)
- `patch/plan_matrix.patch` (47 строк) к `web/govtech/core/plan.js`:
  1. `precomputeFromMatrix(sc, lookup)` — та же структура P, что у `precompute()`, но расстояния из готовой матрицы
     (geodesic или pedestrian-v1); неизвестное (status ≠ ok) остаётся null, без подстановки прямой или 0.
  2. одна строка в `evaluateInternal`: путь кандидата null пропускается. Без неё в JS `null < n` = true и неизвестный
     путь стал бы «ближайшей целью» (проверено: удаление строки → 4 FAIL).
  3. экспорт `precomputeFromMatrix`. Формулы, поиск, эталоны и учебный Score не меняются.
- `module/school-compare.js` (предлагаемый путь `web/govtech/school-compare.js`) — адаптер CONTRACT, не оптимизатор:
  `validateCase`, `validateMatrix`, `caseDigest`, `compareCase(case, matrix)` →
  `{schema_version: school-access-compare-v1, case_digest, method, policy_id, threshold_mm, plans, facts, limitations, cost_mode}`.
  Планы: `current`, `candidate:<id>` для каждого выбранного A/B, `auto:contract-lex` (unknown_count → sum → max → ID,
  пустой набор первым), `auto:minimax` (отдельная цель). Строки по точкам берёт из `plan.js` (evaluate + матрица).
  Метрики CONTRACT: total/known/unknown, sum, mean среди известных, max среди известных, within_threshold_count,
  доля от ВСЕХ точек. Точки равновесные; исключить точку нельзя (API не принимает такой параметр).
  Стоимость: null хотя бы у одного кандидата → `no_cost_data` (географическое сравнение работает, деньги не оптимизируются);
  однородные единицы → справочная сумма; разные → `mixed_units_not_comparable`. Фальшивой стоимости нет.
  Политика K05 (в digest): школы `known_restricted` не цели; `unknown` — цели с пометкой строки.
- `ref/school_compare_ref.py` — независимая Python-реализация CONTRACT (без plan.js/модуля).
- `fixtures/make_hand_cases.py` → `fixtures/hand_cases.json`: 7 SYNTHETIC ручных кейсов, ожидания записаны вручную:
  неизвестные пути + школа с неизвестным доступом + ограниченная школа; правило контракта ≠ minimax; ничьи (A1/A2,
  кандидат равен школе → школа ближайшая, бесполезный кандидат → пустой набор); нет точек; unknown_count решает первым;
  pedestrian-v1 со всеми неизвестными.

## Проверки (Python 3.11.15, Node 22)
| Команда | Результат |
|---|---|
| `python3 ref/test_ref.py` | Python-реализация = ручные ожидания (7 кейсов) |
| `python3 run_tests.py --app-root <d2ff344 tree>` | patch применяется; `test_school_compare.cjs` 966 passed 0 failed (ручные ожидания, сверка с Python по всем строкам, 3 перестановки на кейс + digest, чувствительность digest, стоимость, 21 отказ валидации, неизменность входов); тесты BUILD plan/resilience/whatif на пропатченной копии — все PASS |
| удаление строки null-skip во временной копии | 4 FAIL (patch необходим) |
`<d2ff344 tree>`: `git archive d2ff344c5ec9b9a729ea59df50ec81f981e619de web/govtech tests/govtech | tar -x -C /tmp/d2`.

## Дальше
2. Кейс Шымкента и Астаны на реальных записях data.js (geodesic-матрица, синтетические точки/кандидаты A/B),
   `compare.json` + fact catalog для K02/K08, пояснение компромисса и источника каждой метрики.
3. Инструкция интеграции для BUILD, повторная проверка; интеграция в сайт 8501 — NOT_RUN до SHA сборщика.
