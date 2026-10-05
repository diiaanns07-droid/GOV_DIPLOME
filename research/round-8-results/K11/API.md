# K11 round 8 — API: поиск планов `city-plan-v2` с Worker, прогрессом и отменой

Модули изолированы в `research/round-8-results/K11/src/`. Общий прототип `prototypes/city-evidence/` не изменён. **В BUILD не интегрировано**: на базе `a5b5e2d` нет `optimizePlans`.

## `src/plan_core.js` — ядро (UMD; `window`/`self.CITY_PLAN_CORE`, `require`)

| Функция | Что делает |
|---|---|
| `validatePlanScenario(input, context)` | Структура, диапазоны и ссылки по CORE_SPEC. Возвращает чистую копию или бросает `PlanError{code, detail}`: `bad_version`, `bad_city`, `bad_snapshot`, `bad_category`, `bad_points`, `bad_candidates`, `bad_id`, `duplicate_id`, `bad_coord`, `outside_bbox`, `bad_weight`, `bad_kind`, `bad_cost`, `bad_budget`, `bad_max_selected`, `bad_radius`, `unknown_candidate`, `required_excluded_overlap`, `unknown_field`, `missing_field`. `derived_results` разрешён и отбрасывается. Строгий разбор текста и байтов файла — `src/plan_export.js`. |
| `prepareProblem(context, sc)` | Все гаверсинусы считаются один раз и переводятся в мм (`haversine-mm-v1`). Внутри перебора гаверсинус не вызывается. |
| `createSearch(pb, {budget?})` / `stepSearch(st, maxMasks)` / `finalizeSearch(st)` | Возобновляемый полный перебор ≤ 2^16 подмножеств мелкими шагами. Статус `optimal` — только после полного перебора; иначе `incomplete` или `cancelled`. |
| `optimizePlansSync(context, scenario, {budget?})` | То же одним вызовом. **Блокирует поток**, для UI использовать runner. |
| `evaluatePlan(context, scenario, selectedIds)` | Ручной план: строки по точкам (`before_mm`, `after_mm`, `delta_mm`, `nearest_after: {kind: "source" \| "hypothetical", id}`), метрики, `feasible` и `reasons`. |
| `problemDigest(sc)` / `scenarioDigest(sc)` | `sha256:` канонического входа задачи; не зависит от порядка массивов. `selected_ids` входит только в `scenarioDigest`. |
| `sensitivityBudgets(B)` | `[0, floor(B/2), B]` без дублей. |

Результат `finalizeSearch` / `optimizePlansSync`:

```
{status: "optimal"|"infeasible"|"cancelled"|"incomplete", reasons?, problem_digest, metric_version, engine, budget,
 evaluated, total, feasible_count,
 objectives: {mean|minimax|coverage: {selected_ids, metrics:{selected_count, cost, unknown_count, weighted_sum_mm,
              weighted_mean_mm|null, max_mm|null, covered_weight, coverage_fraction}, same_as:[...]}},
 pareto: [{selected_ids, cost, weighted_sum_mm}], distinct_objective_plans}
```

Решения K11 там, где CORE_SPEC даёт свободу:
- точки и кандидаты внутри упорядочены по ID в порядке кодовых точек (как `str` в Python);
- при ничьей расстояний ближайшей остаётся исходная запись (ключ source раньше hypothetical), затем меньший ID;
- `problem_digest` содержит `engine` и `metric_version`.

## `src/plan_runner.js` — оркестратор (UMD; `CITY_PLAN_RUNNER`)

```js
const runner = CITY_PLAN_RUNNER.createPlanRunner({
  engine: CITY_PLAN_CORE,               // любой движок с validatePlanScenario/problemDigest/prepareProblem/
                                        // createSearch/stepSearch/finalizeSearch/sensitivityBudgets
  mode: "auto",                         // "worker" | "chunks" | "auto" (worker, при ошибке создания — чанки)
  workerFactory: CITY_PLAN_RUNNER.urlWorkerFactory("plan_worker.js"),   // http(s)
  //   file://: CITY_PLAN_RUNNER.blobWorkerFactory(window.CITY_PLAN_WORKER_SOURCES)
  //   Node:    CITY_PLAN_RUNNER.nodeWorkerFactory(path.join(__dirname, "plan_worker.js"))
  chunkMasks: 4096,   // масок на сообщение прогресса в worker
  sliceMs: 10,        // квант времени главного потока в режиме "chunks"
  cancelGraceMs: 250, // нет подтверждения отмены — worker.terminate() (гарантированное освобождение)
  onProgress: (e) => {},  // {request_id, problem_digest, phase, fraction, done_masks, all_masks}
  onStatus: (e) => {},
});
const job = runner.run(context, scenario, { sensitivity: true });  // job.request_id, job.problem_digest — сразу
const env = await job.promise;
// env = {status, request_id, problem_digest, mode, elapsed_ms, fallback, result?, code?, detail?}
// status: optimal | infeasible | cancelled | superseded | error
if (runner.isCurrent(env)) { /* показать предложение; применить только по кнопке пользователя */ }
runner.cancel();   // активная задача -> "cancelled" сразу; worker получает cancel и подтверждает или будет убит
runner.dispose();  // отмена + terminate + очистка таймеров
runner.state();    // {active, worker_alive, pending_timers, pending_cancels, worker_broken, disposed, stats}
```

Гарантии, проверенные в `tests/harness.cjs`:
- новый `run()` переводит предыдущий в `superseded`;
- сообщения с другим `request_id` или чужим `problem_digest` игнорируются (счётчик `stale_messages_ignored`);
- после `cancel` в режиме чанков вычисления прекращаются;
- worker без подтверждения отмены убивается, а более новая задача перезапускается на свежем worker (`redispatched`);
- невалидный сценарий даёт `error` с кодом, работа не начинается;
- `optimal` только после полного перебора.

## `src/plan_worker.js` — сторона worker

Один файл для Web Worker (`importScripts("plan_core.js")`), Blob-worker из встроенных исходников и Node `worker_threads`. Протокол:

- вход: `start` / `cancel`;
- выход: `accepted`, `progress`, `result`, `cancelled`, `error`.

Все сообщения несут `request_id`, а `progress`/`result` — ещё и `problem_digest`.

Worker считает квантами по `slice_ms` (8 мс). Между квантами он уступает цикл событий через `MessageChannel` (браузер) или `setImmediate` (Node), а не через `setTimeout(0)`: тот зажимается до 4 мс. Поэтому `cancel` обрабатывается не позже чем через один квант. `cancel` для запроса, который уже не выполняется, подтверждается сразу.

## `src/plan_export.js` — файл сценария (UMD; `CITY_PLAN_EXPORT`)

| Функция | Что делает |
|---|---|
| `exportPlanFile(scenario, env?, label?)` | Сериализует проверенный сценарий в `{filename, text, mime}`. Текст UTF-8 без BOM, только LF, буквы без `\u`-экранов, фиксированный порядок ключей. `derived_results` с пометкой «never trusted» добавляются, только если `env.status === "optimal"`. NaN/Infinity и непарный суррогат → `ExportError` (`non_finite_number`, `lone_surrogate`), а не `null` или `\ud800` в файле. Больше 256 КиБ → `too_large`. |
| `importPlanBytes(bytes, context, engine)` | **Основной путь импорта.** UTF-8 строго (`TextDecoder fatal`); BOM UTF-8 пропускается; UTF-16 LE/BE читается только с BOM. Windows-1251/ANSI → `not_utf8`. Дальше как `importPlanText`. Возвращает `{scenario, derived_ignored, bom, encoding}`. |
| `importPlanText(text, context, engine)` | Для уже декодированного текста: BOM, ≤ 256 КиБ UTF-8, U+FFFD → `replacement_char` (признак чтения не в той кодировке), `parseStrict`, затем `engine.validatePlanScenario`. `derived_results` никогда не используются. |
| `readPlanFile(file, context, engine)` | Браузер: `File` из `<input type=file>` → `arrayBuffer()` → `importPlanBytes`. Не `File.text()`: тот молча заменяет байты. |
| `parseStrict(text)` | JSON без расширений, линейный. Ошибки: `duplicate_key`, `non_finite_number` (`1e999`), `lone_surrogate`, `bad_json` (NaN/Infinity, хвост, комментарии, висячая запятая, ведущий ноль, управляющий символ в строке, вложенность > 64). `__proto__` остаётся обычным ключом данных. |
| `suggestFilename(scenario, label?)` / `safeFilename(name)` | Читаемое имя, например `план_Шымкент_школы.json`. NFC; символы `<>:"/\?*`, вертикальная черта и управляющие символы → `_`; без точек и пробелов в конце; зарезервированные имена Windows (`CON`, `NUL`, `COM1`, `LPT¹`… также с расширением) получают префикс `_`; ≤ 120 UTF-16 единиц, обрезка по границе кодовой точки. |
| `downloadPlanFile(file, doc?)` | Браузер: Blob + `<a download>`, URL освобождается через 1 с. |
| `decodePlanBytes(bytes)`, `utf8Length(s)`, `MAX_BYTES`, `ExportError{code, detail}` | Вспомогательное. |

Ошибки проверки содержимого приходят из движка как `PlanError` (`bad_city`, `bad_snapshot`, …). Пример UI переводит коды на русский (`example/index.html`).
