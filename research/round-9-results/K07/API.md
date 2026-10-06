# K07 · Раунд 9 · API адаптера и панели «Устойчивость к допущениям»

Оба файла лежат в `web/` и добавляются в BUILD патчем `patch/build_d865dd4_r9_resilience_panel.patch`: два новых файла, а в `index.html` — подключение скриптов и CSS. `plan.js` и `plan-ui.js` не заменяются.

## `web/resilience_k07.js` — адаптер к `plan.js` BUILD

Браузер: `window.CITY_RESILIENCE_K07` (нужны загруженные ранее `facts.js` и `plan.js`). Node: `require(...)(PL)`, где `PL` — модуль `plan.js` BUILD.

Используются функции BUILD: `validatePlanScenario`, `precompute`, `feasibility`, `metricsOf`, `problemDigest`, `METRIC`. Собственное только:
- фильтрация исходных записей по случаю — в новом объекте контекста, исходный не меняется;
- лексикографический перебор худшего случая.

| Функция | Результат |
|---|---|
| `validateResilience(input, ctx)` | Чистый envelope `{schema_version: "city-resilience-v1", plan, cases[{id, label, disabled_source_ids (отсортированы)}]}`, иначе бросает `ResilienceError` с `code`. Ошибки v2-плана приходят с кодами BUILD |
| `evaluateResilience(ctx, envelope, selectedIds?)` | `{selected_ids, cost, feasible, feasibility, per_case[{case_id, label, metrics, loss}], worst_vector, worst_case_ids}` |
| `createResilienceSearch(ctx, envelope, {F})` | `{total, examined, step(n) → done, cancel(), result(), problem_digest}` |
| `optimizeResilience(ctx, envelope, {F})` | Синхронный путь для Node; результат как у `createResilienceSearch(...).result()` |
| `resilienceProblemDigest(env, F)` | `"sha256:"` от `[schema, metric, "worst-lex-v1", problemDigest v2, случаи по id с отсортированными исключениями]`. Без `selected_ids`, от порядка входа не зависит |
| `resilienceScenarioDigest(env, F)` | То же плюс отсортированные `selected_ids` |
| `allCases(env)`, `sourceIds(ctx, category)` | Вспомогательные |

Коды отказов `validateResilience`:
- `bad_shape`, `unknown_field` (в r9 envelope производных полей нет), `bad_schema`;
- `too_many_candidates` (> 12; проверяется до валидации плана и до предвычислений), `bad_count` (1..7 случаев);
- `bad_id`, `reserved_id` (`base`), `duplicate_id`, `bad_label` (пустая, > 120 code points, управляющие символы);
- `bad_exclusions`, `candidate_not_source`, `unknown_source` (запись не той категории или не из этого среза).

Результат `createResilienceSearch(...).result()`:
- `status` ∈ `optimal`, `infeasible`, `cancelled`, `incomplete`; при отмене или незавершённом поиске плана нет.
- `nominal` и `robust` = `{selected_ids, cost, per_case, worst_vector, worst_case_ids}`.
- `same_plan`.
- `price_of_robustness_m`: метры = base weighted_mean устойчивого − обычного; при неизвестной метрике — `null` и `price_reason`.
- `evaluated`, `total_subsets`, `feasible_count`, `reasons`.
- `resilience_problem_digest`, `metric_version`, `objective_version: "worst-lex-v1"`.

Правила расчёта:
- **Вектор потерь** L = `(unknown_count, weighted_sum_mm, max_mm)`; внутри сравнения `null` в `max_mm` считается +∞, наружу выдаётся `null`.
- **Худший вектор** W — лексикографический максимум L по случаям, включая `base`. Перечисляются все случаи с равным L.
- **Обычный план** — v2-ключ mean на `base`: `(L_base, cost, IDs)`.
- **Устойчивый план** — `(W, L_base, cost, IDs)`.

Проверено против Python-оракула `tests/oracle_resilience.py` и против mean-оптимума v2 BUILD (`tests/resilience_k07.test.cjs`).

## `web/resilience_panel_k07.js` — панель в карточке плана BUILD

Подключается к хукам BUILD:
- `CITY_PLAN_UI.OPT.render` — свой раздел в конце карточки;
- `CITY_PLAN_UI.OPT.onProblemChange` — при изменении задачи поиск останавливается, после поиска результат устаревает по digest;
- `CITY_APP.ui.EXT.onCity` — смена города сбрасывает случаи.

Движок: `window.CITY_RESILIENCE` (если BUILD выпустит свой с API CORE_SPEC), иначе `CITY_RESILIENCE_K07`.

Элементы:
- **Выбор записей:** `#rsQa` (фильтр «все» / «с QA» / «без QA»), список `#rsSources`, флажки `#rsSrc_<id записи>`.
- **Случаи:** `#rsLabel`, `#rsAdd`, список `#rsCases`, кнопки `#rsDel_<id случая>`.
- **Сравнение:** `#rsRun`, `#rsCancel`, `#rsProgress`, `#rsMsg` (`role=status`).
- **Результат:** `#rsResultTitle`, `#rsPrice`, карточки `#rsCompare [data-rs-plan=manual|nominal|robust]`, `#rsApply_nominal`, `#rsApply_robust`, `#rsRestore`, таблица `#rsTable` в области `role=region` с `tabindex=0`.

Для тестов: `window.CITY_RESILIENCE_UI = {state, addCase, removeCase, startRun, stopRun, envelope, validEnv, currentDigest}`; `state.runOpts = {chunk, delayMs}` замедляет перебор.
