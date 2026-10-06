# resilience.js — устойчивость к допущениям о данных (city-resilience-v1), K05 round 9

Это тонкий модуль поверх `web/plan.js` сборки (city-plan-v2), а не второй движок. Геометрия, округление до миллиметров (`haversine-mm-v1`), ничьи, проверка ограничений, строки и метрики плана, а также mean-оптимум берутся из функций сборки: `PL.validatePlanScenario`, `PL.precompute`, `PL.evaluatePlan`, `PL.feasibility`, `PL.optimizePlans`, `PL.problemDigest`. Строгий JSON — `X.parseStrict` из `whatif.js`, хэши — `F.sha256hex` из `facts.js`.

Модуль проверялся на сборке `d865dd4a124291e10dd0b7bb1d9eada20d34c268`. **В BUILD он не встроен**: новый файл предлагается в `patches/add_web_resilience_js.patch`, интерфейс вкладки делает сборщик.

Случай — это исходные записи категории, которые **условно не учитываются**. Это анализ допущений о данных, а не прогноз закрытия учреждения, риска или потребностей жителей. QA-флаг не исключает запись автоматически. Исходные записи, контекст и `data.js` не меняются.

## Подключение
- Браузер: `<script src="resilience.js">` после `facts.js`, `whatif.js`, `plan.js` даёт `window.CITY_RESILIENCE`.
- Node: `require("./web/resilience.js")` подхватывает зависимости сам, если файл лежит рядом с `plan.js`. Иначе — `require(".../resilience.js").bind(PL, F, X)`.

## API
| Функция | Что делает |
|---|---|
| `parseResilienceJSON(text)` | строгий JSON ≤ 256 KiB (`X.parseStrict`): ошибки `bad_json` и `too_large` |
| `validateResilience(input, ctx)` | возвращает чистую deep-frozen копию или бросает `ResilienceError{code}` |
| `evaluateResilience(ctx, env, selectedIds)` | `{selected_ids, feasible, reasons, cost, per_case[], worst_vector, worst_case_ids, metric_version, objective_version}` |
| `createResilienceSearch(ctx, env, {request_id})` | `{total, examined, step(n) → done, cancel(), result()}` — пошагово, ≤ 4096 подмножеств |
| `optimizeResilience(ctx, env, opts)` | синхронно; это путь для Node и оракула |
| `optimizeResilienceAsync(ctx, env, {chunk, signal, shouldCancel, onProgress, request_id})` | чанки с уступкой event loop |
| `digests(env)` | `plan_problem_digest`, `exclusions_digest`, `resilience_problem_digest`, `resilience_scenario_digest` |
| `isCurrent(result, resilience_problem_digest, request_id)` | `false`, если ответ устарел и его нельзя применять |
| `exportResilience(env)` / `importResilience(text, ctx)` | экспортируется только вход, без производных полей |

Публичные функции принимают и непроверенный объект: тогда он проверяется заново. Проверенный конверт заморожен, поэтому изменить его после проверки и обойти лимиты нельзя.

### Конверт
`{schema_version: "city-resilience-v1", plan: <city-plan-v2 без derived_results>, cases: [{id, label, disabled_source_ids}]}` — от 1 до 7 случаев; `base` добавляется автоматически.

Коды ошибок проверки:
- **конверт:** `bad_shape`, `unknown_field`, `missing_field`, `bad_version`;
- **размер:** `too_many_candidates` — больше 12 кандидатов, проверяется **до** проверки plan и до любых предвычислений; `bad_cases`;
- **случаи:** `bad_id`, `reserved_id` (id `base`), `duplicate_id`, `bad_label` (пустая строка, больше 120 code points, управляющие символы), `bad_exclusions` (меньше 1 или больше числа исходных записей категории), `candidate_not_source`, `unknown_source`;
- **plan:** коды v2 передаются как есть (`foreign_snapshot`, `bad_budget` и т.д.).

ID проверяются по тем же правилам, что в сборке: Unicode в NFC, 1–64 code points, буквы, цифры, `_ . -`.

### Ответ `optimizeResilience`
`{schema_version, status: "optimal"|"infeasible"|"incomplete"|"cancelled", reasons, nominal, robust, same_plan, price_of_resilience_m, price_reason, cases, evaluated, total_subsets, feasible_count, digests…, metric_version: "haversine-mm-v1", objective_version: "worst-lex-v1", request_id}`.
- **Случай:** базовый набор состоит из исходных записей без `disabled_source_ids`. Отфильтрованная копия контекста передаётся в `PL.precompute`; кандидаты и ограничения во всех случаях одинаковы.
- **Потери плана:** `L = (unknown_count, weighted_sum_mm, max_mm)`, неизвестный max внутри сравнения считается +∞. `W` — лексикографический максимум `L` по всем случаям, включая base. `worst_case_ids` перечисляет все случаи, у которых `L = W`, в отсортированном порядке.
- **Обычный план** — `PL.optimizePlans(...).objectives.mean` на base. **Устойчивый план** — минимум по ключу `(W, L_base, cost, sorted ids)` среди допустимых наборов.
- **Цена устойчивости** = (base `weighted_mean_mm` устойчивого − base `weighted_mean_mm` обычного) / 1000 м, только если обе величины известны и обе задачи решены как optimal; иначе `null` и `price_reason`. Цена может быть 0; `same_plan` показывает, что планы совпали.
- **`per_case[]`:** `{case_id, label, disabled_source_ids, same_exclusions_as, n_source_records, loss, metrics: {unknown_count, weighted_mean_mm, max_mm, covered_weight, coverage_fraction, cost}, rows}`. Поле `rows` — это строки `PL.evaluatePlan` внутри случая.
- `incomplete` и `cancelled` никогда не выдаются за optimal: `robust` и `nominal` в этих статусах равны null. Infinity в JSON не попадает.

## Чего модуль не делает
Не даёт вероятностей случаев и «усреднённого риска», не переводит в тенге, не считает население по весам и время пути по расстояниям. Тесты используют синтетические кандидаты, точки и случаи; реальные только записи среза.
