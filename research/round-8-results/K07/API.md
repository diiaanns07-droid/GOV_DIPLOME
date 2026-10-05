# K07 · Раунд 8 · API модулей city-plan-v2 (K07)

Все модули — обычные скрипты без сборки и без сети. В браузере они создают `window.*`, в Node экспортируются через `module.exports`. Строки выводятся только как текст.

## `web/plan_calc.js` → `window.CITY_PLAN_CALC`

Расчётный адаптер по `research/round-8/CORE_SPEC.txt`. Чистые функции без DOM.

| Функция | Что делает |
|---|---|
| `makeContext(data, city, F)` | Контекст среза `{city_id, bbox, source_snapshot, release, places_sha256, places, hash, versions}`. `F` — API `facts.js` (`sha256hex`, `placesDigest`). `source_snapshot` = sha256 от `["city-plan-v2", city, release, sha256 файла мест, placesDigest, "haversine-mm-v1"]`; совпадает с BUILD `plan.js` (проверено `build_engine_crosscheck.cjs`, X01) |
| `validatePlanScenario(input, ctx, {allowEmptyPoints})` | Возвращает `{ok: true, scenario}` (нормализованная копия; `derived_results` отброшен и не используется) или `{ok: false, error: {code, path, detail}}`. Коды: `bad_schema`, `bad_city`, `bad_snapshot`, `bad_category`, `bad_kind`, `bad_type`, `unknown_field`, `missing_field`, `bad_id`, `duplicate_id`, `unknown_reference`, `required_excluded_overlap`, `bad_count`, `bad_coordinate`, `outside_bbox`, `not_integer`, `out_of_range`. ID — ASCII `[A-Za-z0-9_-]{1,64}` (BUILD допускает и буквы любого алфавита в NFC) |
| `evaluatePlan(ctx, scenario, selectedIds?)` | Возвращает `{metric_version, selected_ids, rows, metrics, baseline_records, feasibility, scenario_digest}`. Подробности ниже |
| `createSearch(ctx, scenario)` | Пошаговый точный перебор: `{total, problem_digest, evaluated, done, step(n), result(interrupted?)}`. `result()` до конца перебора даёт `partial`, с аргументом `"cancelled"` — `cancelled`; в обоих случаях без победителей |
| `optimizePlans(ctx, scenario)` | Возвращает `{status, problem_digest, metric_version, calc_version, evaluated, total_subsets, feasible_count, infeasible_reasons, objectives, pareto, pareto_excluded_unknown, sensitivity}`. Подробности ниже |
| `problemDigest(ctx, sc)` / `scenarioDigest(ctx, sc)` | sha256 канонического JSON (ключи отсортированы, массивы — по ID). `problemDigest` без `selected_ids`, `scenarioDigest` — с ними |

`evaluatePlan`:
- `rows[]` = `{control_point_id, weight, before_mm, after_mm, delta_mm, nearest_before, nearest_after, covered}`; `nearest_*` = `{kind: "source"|"hypothetical", id}`. Если `before = null`, то `delta = null`. При ничьей по мм ближайшим считается запись среза, а не место.
- `metrics` = `{unknown_count, weighted_sum_mm, weighted_mean_mm, max_mm, covered_weight, total_weight, coverage_fraction, cost, selected_count}`.
- `feasibility.reasons[].code` ∈ `over_budget`, `too_many`, `missing_required`, `has_excluded`.

`optimizePlans`:
- `status` ∈ `optimal`, `infeasible`, `cancelled`, `partial`.
- `infeasible_reasons[].code` ∈ `required_over_budget`, `required_over_count`.
- `objectives.mean|minimax|coverage` = `{selected_ids, metrics}`. Ключи сравнения — как в CORE_SPEC; неизвестный `max` внутри сравнения равен ∞, наружу — `null`.
- `pareto[]` = `{selected_ids, cost, weighted_sum_mm, weighted_mean_mm, max_mm}`: только полные планы; равные пары свёрнуты к меньшим ID.
- `sensitivity[]` = `{budget, feasible_count, objectives}` для бюджетов `[0, ⌊B/2⌋, B]` без повторов, за один проход перебора.

Метрика: `haversine-mm-v1` (R = 6371008.8, `Math.round(d·1000)` один раз). Перебор проходит `2^n` масок с отсечением по `max_selected`, ограничениям и бюджету.

## `web/plan_runner.js` → `window.CITY_PLAN_RUNNER`

`start(engine, ctx, scenario, {chunk = 2048, delayMs = 0, onProgress, onDone})` → `{request_id, problem_digest, finished, cancel()}`.

- `onProgress({request_id, evaluated, total})` вызывается между ходами event loop (`setTimeout`).
- `onDone(result + request_id)` вызывается ровно один раз.
- `cancel()` даёт результат `status: "cancelled"`.
- Движок без `createSearch` выполняется одним вызовом `optimizePlans`, без промежуточного прогресса (это сказано в `note`).
- Worker не используется, потому что страница открывается с `file://`.

## `web/plan_demo.js` → `window.CITY_PLAN_DEMO`

`syntheticDemo(bbox, category)` → 12 точек и 8 мест на сетке внутри bbox, бюджет 150, максимум 2, радиус 300. `LABEL` — подпись SYNTHETIC. Это не данные города.

## `web/planner_ui.js` → `window.CITY_PLAN_UI` (предложение для базы `a5b5e2d`)

Хуки, которые вызывает `app.js` (патч `patch/city_evidence_planner.patch`):
- `init(CITY_APP)`
- `drawLayer(g, {toScreen})`
- `placing()`
- `onMapClick(lonlat, event)`
- `onMapEnter(lonlat)`
- `onCitySwitch(city)`
- `onOtherMode()`
- `statusText()`

Для подключения другого движка: `setCalculator(engine, {makeContext})`. Тестам доступны `_state` (`runOpts` замедляет поиск) и `_validated()`.

> **Конфликт имён:** BUILD `d865dd4` сам экспортирует `window.CITY_PLAN_UI` (`plan-ui.js`). Поэтому этот UI-модуль — альтернатива для `a5b5e2d`, а не дополнение к `d865dd4`. Патч `city_evidence_planner.patch` на `d865dd4` не применяется: `git apply --check` отказывает, так что тихой перезаписи не будет.

## Адаптер тестов к BUILD (`tests/k07r8_build_planner.cjs`)

Используются публичные элементы BUILD:
- кнопки `#toolSeg [data-tool=v2]`, `#plModePoints`, `#plModeCands`;
- поля `#plBudget`, `#plMax`, `#plRadius`, `#plW_<id>`, `#plC_<id>`, `#plS_<id>`, `#plSel_<id>`;
- поиск и применение `#plRun`, `#plCancel`, `#plApply_<k>`, `#plRestore`;
- импорт через `#plFile`;
- объект `window.CITY_PLAN_UI` (`state`, `opt`, `rawScenario()`, `exportText()`).

Если BUILD переименует их, проверка `P0` даст `TEST_INCOMPATIBLE`, а не PASS.
