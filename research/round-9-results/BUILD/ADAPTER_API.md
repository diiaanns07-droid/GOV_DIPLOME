# city-resilience-v1 — API модуля `web/resilience.js` (для адаптеров коллег)

Модуль работает в Node (`require("web/resilience.js")`, рядом `plan.js`, `whatif.js`) и в браузере (`window.CITY_RESILIENCE`).
Контекст — `CITY_PLAN.makeContext(data, city, F)` (замороженные копии записей; `F` = `facts.js`).

| Функция | Вход | Выход / ошибки |
|---|---|---|
| `validateResilience(input, ctx)` | envelope `{schema_version:"city-resilience-v1", plan:<city-plan-v2>, cases:[{id,label,disabled_source_ids}]}` | чистая копия; `PlanError(code)`: `too_many_candidates` (>12, до предвычислений), `bad_cases` (0 или >7), `reserved_id` (`base`), `duplicate_id`, `bad_id`, `bad_label`, `bad_exclusions`, `candidate_not_source`, `unknown_source`, `unknown_field`, `derived_not_allowed`, `wrong_version` (v1/v2-файл), `bad_version`, + все коды `validatePlanScenario` |
| `evaluateResilience(ctx, env, selectedIds)` | непроверенный envelope допустим | `{selected_ids, feasibility, cost, per_case:[{case_id,label,disabled_count,source_records,metrics,rows,loss}], worst_vector:{unknown_count,weighted_sum_mm,max_mm|null}, worst_case_ids, base_weighted_mean_mm}` |
| `createResilienceSearch(ctx, env, {F, request_id})` | — | `{total, examined, step(n)→done, cancel(), result()}`; ≤ 4096 подмножеств |
| `optimizeResilience(ctx, env, {F})` | — | `{status: optimal|infeasible|cancelled|incomplete, reasons, nominal, robust, same_plan, evaluated, total_subsets, feasible_count, duplicate_case_groups, price_of_robustness_m|null, price_reason, resilience_problem_digest, exclusions_digest, source_snapshot, metric_version:"haversine-mm-v1", objective_version:"worst-lex-v1", request_id, cases}` |
| `exportResilience(ctx, env)` / `importResilience(text, ctxFor)` | строгий JSON ≤256 KiB | экспорт — только вход; импорт → `{envelope, ctx}` или ошибка без побочных эффектов |
| `resilienceProblemDigest`, `resilienceScenarioDigest`, `exclusionsDigest` | — | не зависят от порядка случаев/ID; `selected_ids` только в scenario-digest |

Правила: случай `base` (без исключений) добавляется автоматически; потери L=(unknown_count, weighted_sum_mm, max_mm→+∞ при неизвестных) сравниваются
лексикографически; W = максимум L по случаям; нормальный план = mean-оптимум v2 на base; устойчивый = min (W, L_base, cost, ID).
Цена устойчивости = (среднее base устойчивого − среднее base обычного)/1000 м, иначе `null` + `price_reason`.
Сравнивать с независимыми реализациями математику (ID планов, векторы, метрики), а не внутренние digest.
