# plan.js — точный оптимизатор и оценка плана (city-plan-v2), K05 round 8

Это изолированный модуль, готовый к подключению. В сборку **не встроен**, общий прототип не менялся. Спецификация — `research/round-8/CORE_SPEC.txt` @ `c3f6c00`. Проверен на данных сборки `a5b5e2ddbe087c4eab8e947748cdf69dbae84a0d` (`prototypes/city-evidence/web/data.js`, `evidence.js`, `facts.js`, `whatif.js`).

Модуль измеряет только расстояния **по прямой** до выбранных контрольных точек в срезе. Это не время пути, не население, не вместимость и не прогноз пользы. Стоимость и бюджет — условные единицы пользователя, не тенге и не смета. Найденный оптимум — лучший только среди введённых кандидатов и условий, а не лучший план для города.

## Файлы
| Файл | Назначение |
|---|---|
| `plan.js` | модуль: UMD, браузер (`window.CITY_PLAN`) и Node (`require`), без DOM и сети |
| `tests/helpers.cjs` | загрузка сборки по `--app-root`, синтетические фикстуры с seed |
| `tests/test_stage1.cjs` | этап 1: проверка сценария, оценка, перебор, ограничения, ничьи, порядок, гаверсинус один раз |
| `tests/test_stage2.cjs` | этап 2: три цели и граница Парето против наивного перебора, статусы, прогресс, отмена, async |
| `tests/test_stage3.cjs` | этап 3: граничные случаи |
| `tests/dump_cases.cjs` + `oracle/oracle.py` | независимый Python-оракул (itertools, свои ключи, Парето O(N²)) |
| `tests/bench.cjs` | бенчмарк максимального размера |
| `runs/*.json` | фактические результаты прогонов на a5b5e2d |

## Команды
```bash
A=<checkout a5b5e2d или новее>/prototypes/city-evidence
node research/round-8-results/K05/tests/test_stage1.cjs --app-root $A
node research/round-8-results/K05/tests/test_stage2.cjs --app-root $A
node research/round-8-results/K05/tests/test_stage3.cjs --app-root $A
node research/round-8-results/K05/tests/dump_cases.cjs --app-root $A --out /tmp/cases.json
python3 research/round-8-results/K05/oracle/oracle.py --cases /tmp/cases.json
node research/round-8-results/K05/tests/bench.cjs --app-root $A --repeat 5
```
Нужны Node ≥ 18 и Python 3 (только stdlib); сеть не нужна.

## API
```js
const PL = window.CITY_PLAN;                       // или require("./plan.js")
const ctx = PL.contextFromCityData(city, window.CITY_EVIDENCE.cities[city],
            CITY_WHATIF.sourceSnapshot(window.CITY_EVIDENCE, city, window.CITY_FACTS)); // отпечаток считает сборка
const obj = PL.parsePlanJSON(text);                // строгий JSON ≤ 256 KiB; бросает PlanError{code}
const v = PL.validatePlanScenario(obj, ctx);       // {ok:true, scenario} | {ok:false, error:{code, message, path}}
const e = PL.evaluatePlan(ctx, v.scenario, ids);   // ручной план: rows + metrics + feasibility{feasible, reasons[]}
const r = PL.optimizePlans(ctx, v.scenario, {onProgress, shouldCancel, maxEvaluations, chunk, request_id, sensitivity});
const r2 = await PL.optimizePlansAsync(ctx, v.scenario, {signal, onProgress, chunk, request_id}); // не блокирует UI
PL.isCurrent(r2, PL.problemDigest(currentScenario), currentRequestId); // false → ответ устарел, не применять
PL.toStrictJSON(r);                                // JSON без NaN/Infinity
```
- `context`: `{city_id, bbox, source_snapshot, records: [{id, lon, lat, group}], versions}`. Отпечаток среза модуль сам не вычисляет, а сверяет с `scenario.source_snapshot`.
- В сценарии: все поля CORE_SPEC обязательны. Разрешено одно дополнительное поле `derived_results`: оно игнорируется и в результат не попадает. Любое другое поле даёт `unknown_field`.
- Коды ошибок: `bad_json`, `too_large`, `bad_type`, `unknown_field`, `missing_field`, `bad_version`, `bad_city`, `foreign_city`, `foreign_snapshot`, `bad_category`, `bad_number`, `bad_count`, `bad_coord`, `outside_bbox`, `bad_id`, `duplicate_id`, `unknown_candidate`, `category_mismatch`, `bad_kind`, `required_excluded_overlap`.

### Строка ручного плана (`evaluatePlan().rows[]`)
`{point_id, weight, before_mm, before_ref:{ns:"source", id, kind:"observed_secondary"}|null, after_mm, after_ref:{ns:"source"|"candidate", id, kind}|null, delta_mm, covered}`.
`delta_mm = null`, если неизвестно «до» или «после». Пустой набор объектов даёт `null`, а не 0.

### Метрики
`unknown_count, weighted_sum_mm, weighted_mean_mm` (null при unknown), `max_mm` (null при unknown), `covered_weight, total_weight, coverage_fraction, cost`. Это `metric_version = "haversine-mm-v1"`: каждое расстояние один раз округляется до целых миллиметров через `Math.round`, а Python-оракул использует `floor(x + 0.5)`.

### Ответ `optimizePlans` (`city-plan-result-v2`)
`{status: "optimal"|"infeasible"|"incomplete", objectives: {mean, minimax, coverage}|null, best_so_far (только при incomplete), same_plan_as, pareto: [{ids, cost, weighted_sum_mm, metrics}]|null, pareto_excluded_partial, sensitivity: [{budget, status, objectives}], evaluated, total, feasible_count, canceled, reasons (при infeasible), problem_digest, request_id, metric_version, haversine_calls, n_source_records, …}`.
- `optimal` ставится только после полного перебора всех 2^n масок. При отмене или лимите статус `incomplete`, `objectives = null`, а лучший найденный план лежит отдельно в `best_so_far`. Эвристики нет.
- Ключи (меньше — лучше): mean `(unknown, sum, max, cost, ids)`, minimax `(unknown, max, sum, cost, ids)`, coverage `(−covered, unknown, sum, max, cost, ids)`. Неизвестный max внутри считается +∞, наружу отдаётся `null`. Массивы ids сравниваются поэлементно, более короткий — раньше.
- Ничьи по расстоянию: исходная запись выигрывает у кандидата, среди кандидатов — меньший id. Порядок входных массивов на результат и digest не влияет.
- Граница Парето строится только по планам без unknown. Равные пары (cost, sum) сворачиваются к плану с меньшими ids, список упорядочен по cost.
- Чувствительность: бюджеты `[0, floor(B/2), B]` без дублей, остальное не меняется.
- `problem_digest` не зависит от порядка массивов и от `selected_ids`; `scenarioDigest` учитывает и `selected_ids`.

## Бенчмарк (a5b5e2d, Node v22.22.0, Intel Xeon 2.1 GHz, 4 ядра)
16 кандидатов × 25 точек, `max_selected = 5`, бюджет 1e6: перебор 65 536 масок, из них 6 885 допустимых. По двум прогонам: синхронно 14–18 мс без чувствительности и 44–66 мс с ней (это четыре полных перебора). В асинхронном режиме с чанком 2048 самый долгий чанк — 3,6–9,5 мс; результат async побайтно равен sync. Последний прогон — `runs/benchmark_a5b5e2d.json`. Время зависит от машины.

## Ограничения
- Кандидаты, стоимости, веса и бюджеты во всех тестах — **синтетические** (`syn_*`, seed). Реальные только исходные записи среза Overture (`observed_secondary`).
- Интерфейс (карта, «Применить», таблицы) и шаблонное объяснение не сделаны: это работа сборщика. Модуль даёт для них `same_plan_as`, ссылки `ns`/`kind` и метрики.
- Web Worker не используется: неблокирующий режим сделан чанками в event loop (`optimizePlansAsync`); worker-обёртку может добавить сборщик.
- Перенос city-whatif-v1 → v2 не делается: режимы остаются раздельными, как допускает CORE_SPEC.
