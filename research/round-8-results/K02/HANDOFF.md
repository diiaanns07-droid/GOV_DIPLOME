# K02 r8 HANDOFF — факты и объяснение выбора для city-plan-v2

Изолированный пакет в `research/round-8-results/K02/`. Общий прототип не менялся. В BUILD он не интегрирован, поэтому интеграция **не проверена**.

**Проверено на:** `prototypes/city-evidence` @ `a5b5e2ddbe087c4eab8e947748cdf69dbae84a0d` (`claude/beautiful-clarke-sbzomj`).
- Папка прототипа совпадает с кандидатом `4e93f30`.
- Извлечено 191 файл, git blob каждого сверен.
- Из сборки используются `web/facts.js` (`sha256hex`, `PlanError`, `validatePlan`, `formatValue`), `web/whatif.js` (`haversine`, `sourceSnapshot`, `FORMULA`) и `web/data.js`, `web/evidence.js`.

## Модули и API (JS, без DOM, Node и браузер)

### `plan_engine.js` (`CITY_PLAN_ENGINE`)
Точная реализация интерфейса CORE_SPEC: опорный движок, по которому строятся факты. Если сборщик сделает свой движок, каталог примет его результат той же формы.
- **`contextFromData(data, city, category, deps)`** → `{city, category, bbox, release, source_snapshot, sources, versions}`.
  - `source_snapshot` берётся из `whatif.sourceSnapshot` сборки.
- **`validatePlanScenario(input, ctx)`** → очищенный сценарий или `PlanScenarioError(code)`. Коды:
  - `bad_version`, `bad_city`, `bad_category`, `stale_snapshot`;
  - `unexpected_field`, `missing_field`;
  - `bad_id`, `duplicate_id`, `unknown_candidate`, `required_excluded_overlap`;
  - `bad_coordinates`, `outside_bbox`;
  - `bad_weight`, `bad_cost`, `bad_budget`, `bad_max_selected`, `bad_radius`, `too_many_candidates`.

  Поле `derived_results` допускается и игнорируется.
- **`evaluatePlan(ctx, sc, selectedIds, deps)`** → `{selected_ids, rows[{point_id, weight, before_mm, before_key, after_mm, after_key, delta_mm}], metrics, feasible, infeasible_reasons, metric_version}`.
  - `metrics`: `unknown_count`, `weighted_sum_mm`, `weighted_mean_mm|null`, `max_mm|null`, `covered_weight`, `total_weight`, `coverage_fraction`, `cost`, `count`.
  - Причины недопустимости: `over_budget`, `too_many_selected`, `missing_required`, `excluded_selected`.
- **`optimizePlans(ctx, sc, deps, {sensitivity})`** → `{status: optimal|infeasible, objectives{mean,minimax,coverage}, pareto, evaluated, feasible_count, infeasible_reasons, sensitivity[{budget,status,feasible_count,objectives}], problem_digest, metric_version, exact:true}`.
  - Полный перебор до 16 кандидатов, расстояния предвычислены.
  - Ключи лексикографические, как в CORE_SPEC; неизвестный max внутри поиска считается +∞.
  - Парето строится только для планов без неизвестных точек; равные пары сворачиваются к одному представителю.
  - Бюджеты чувствительности: [0, ⌊B/2⌋, B] без повторов.
- **`problemDigest` / `scenarioDigest`** — sha256 канонического ввода, не зависят от порядка массивов. `selected_ids` входят только в `scenarioDigest`.

### `plan_facts.js` (`CITY_PLAN_FACTS`) — основной результат K02
**`buildPlanCatalog(ctx, sc, evalManual, evalBaseline, opt, deps, {problem_digest}?)`** → `{catalog, city, scenario, digest, problem_digest, meta}`. Формат совместим с `facts.validatePlan`.
- Факты:
  - `plan.<baseline|manual|mean|minimax|coverage>.{weighted_mean, max, covered_weight, coverage_fraction, cost, count, unknown_count, selection}` и `plan.manual.feasible`;
  - `constraint.*`;
  - `compare.*` — разности между разными наборами;
  - `sensitivity.sN.*`;
  - `pareto.pN.*`.
- У каждого факта обязательны:
  - `kind`: `derived`, `user_input` или `unknown`;
  - `unit`: mm, m, conditional_units, weight, share, count, flag или text;
  - `scope`: selected_control_points, user_input, search_space или analysis_parameter;
  - `hypothetical`.
- Неизвестное значение — `null` с `missing_reason`, а не 0.
- Подписи ru/kk без цифр.
- Если передан `{problem_digest}` и он не совпадает с результатом, → `stale_problem`.

**`explain(built, lang, deps, {problem_digest})`** → `{text, selector, problem_digest, catalog_digest}`. Внутри:
- **проверка:** `StubSelector` (детерминированная заглушка, **не LLM**) выбирает факты, `facts.validatePlan` их проверяет (`stale_catalog`, `duplicate_id`, `null_as_fact`), затем `render`;
- **таблица:** без объектов, ручной план (с пометкой «недопустим»), три оптимума;
- **совпадения:** совпавшие победители выводятся одним набором;
- **компромиссы:** берутся только из фактов `compare.*`;
- **невыполнимость:** причины задачи и ручного плана, ограничения не снимаются молча;
- **бюджет и Парето:** изменение бюджета, Парето «стоимость → среднее»;
- **данные:** пометка о пустом срезе;
- **ограничения:** без социальных эффектов.

Если `{problem_digest}` от старой задачи → `stale_problem`.

## Фикстуры (`fixtures/`, генератор `make_fixtures.cjs`)
| файл | вид | исходных записей | точек | кандидатов | sha256 |
|---|---|---|---|---|---|
| `fixtures/real_astana_clinic.json` | real_slice_with_synthetic_candidates | 16 | 5 | 5 | `124571cdc5858aa4…` |
| `fixtures/real_shymkent_school.json` | real_slice_with_synthetic_candidates | 15 | 6 | 6 | `91d6c1a0ea039e20…` |
| `fixtures/synthetic_empty_sources.json` | synthetic | 0 | 3 | 3 | `002b89b5bdd6df6f…` |
| `fixtures/synthetic_infeasible_required.json` | synthetic | 1 | 2 | 2 | `6fbf9d4a83828038…` |
| `fixtures/synthetic_radius_boundary.json` | synthetic | 1 | 2 | 1 | `486107ce88580981…` |
| `fixtures/synthetic_tie_same_winners.json` | synthetic | 1 | 1 | 2 | `1a66fb798ea2161a…` |

- **Реальные срезы** (`real_*`): исходные записи — Overture places среза сборки (`provenance.build_sha`, `data_js_sha256`, `release`). Это не полный реестр города.
- **Синтетика в реальных срезах:** кандидаты, веса, стоимости и бюджет — synthetic demo, не тенге и не население.
- **`synthetic_*`:** полностью условная геометрия в квадрате [10,10,10.02,10.02]. `city_id` нужен только схеме.

## Независимые ожидаемые факты
- `oracle/plan_oracle.py`: Python stdlib, своя реализация. Перебор через `itertools.combinations`, кортежные ключи, свой гаверсинус и `floor(x+0.5)`. Это не трансляция JS.
- `variants.json` задаёт 14 вариантов на 6 фикстурах: radius 600/100/150, вес центральной точки 10, required/excluded, бюджет 600, граница радиуса.
- Ожидаемые факты лежат в `expected/*.json`.

## Команды
```bash
APP=<извлечённая prototypes/city-evidence @ a5b5e2d>
node research/round-8-results/K02/make_fixtures.cjs --app-root $APP --build-sha a5b5e2ddbe087c4eab8e947748cdf69dbae84a0d   # детерминированно
python3 research/round-8-results/K02/oracle/plan_oracle.py
node research/round-8-results/K02/tests/stage1_catalog.cjs --app-root $APP
node research/round-8-results/K02/tests/stage2_render.cjs  --app-root $APP
node research/round-8-results/K02/tests/stage3_oracle.cjs  --app-root $APP
node research/round-8-results/K02/demo.cjs --app-root $APP --fixture real_shymkent_school --lang ru
```
Тесты запускаются из каталога `research/round-8-results/K02/` или из корня репозитория: пути разрешаются относительно файлов.

## Интеграция для BUILD (не сделана)
1. Подключить `plan_engine.js` (или свой движок той же формы) и `plan_facts.js` после `facts.js` и `whatif.js`.
2. Запускать поиск в Worker или чанками. Ответ принимать, только если его `problem_digest` совпадает с текущим. Объяснение вызывать с `{problem_digest}` текущей задачи.
3. При смене города или категории сбрасывать сценарий; старый `problem_digest` отклонится сам.
4. Повторить тесты этапов 1–3 с `--app-root prototypes/city-evidence` на новом SHA.

## Ограничения
- **Что считается.** Это расстояние по прямой до записей среза. Нет пешего времени, населения, вместимости, трафика и прогноза социальной пользы. Вес — приоритет пользователя, радиус — параметр анализа, стоимость и бюджет условные.
- **Ничьи между исходными записями.** Они меняют только `after_key`, но не длины, поэтому сравнение фактов с оракулом их не различает. Мутация правила ничьей источников не ловится, и это ожидаемо. Ничья кандидатов покрыта фикстурой `synthetic_tie_same_winners`.
- **Казахские тексты** — черновик для проверки носителем.
- **LLM не вызывалась**, точность LLM не заявляется.
