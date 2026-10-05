# HANDOFF — K09, раунд 8: «Эксперимент для диплома на оптимизации»

- **Задание:** `research/round-8/tasks/K09.txt` и `CORE_SPEC.txt` (ветка `codex/research-import-2026-10-05`, коммит `c3f6c00`).
- **Ветка:** `claude/save-work-handoff-qho6eq`. Результаты только в `research/round-8-results/K09/`.
- **Не менялось:**
  - общий прототип `prototypes/city-evidence`;
  - T1 (`research/round-3-results/K09`);
  - main и чужие ветки.
- **Статус:** все три этапа выполнены, состояние — ready_for_review.
- **Интеграция в BUILD не проверялась и не утверждается.** На базе `a5b5e2d` кода city-plan-v2 нет. Модуль — независимый Python-оракул.

## Что сделано (по этапам)

| Этап | Результат | Коммит |
|---|---|---|
| 1 | Дизайн (`EXPERIMENT_DESIGN.md`), предрегистрация v1 (`config/experiment_config.json`), метрика haversine-mm-v1 (`k09plan/metric.py`), загрузка среза (`k09plan/data.py`), ручная фикстура, тесты | `ed3bd66` |
| 2 | exact, G1/G2, разрыв, seeded suite, валидатор, адаптер API, тесты (exact против наивного перебора на 60 задачах) | `df53f1b` |
| 3 | Раннер (запушен до прогона), прогон v1 на 2610 сценариях | `befadfa`, `e5cd96f` |
| 3 | RESULTS, таблицы | `145654b` |
| 3 | Скрипт сверки со слепыми реализациями | `6cc2a1f` |
| 3 | Независимая проверка: 4 агента, 0 расхождений | `d5bcc0b` |
| 3 | Исправления по обзору и предрегистрация v2 (до прогона v2) | `8aadb10` |
| 3 | Прогоны v1 (после исправлений) и v2 (3420 сценариев), таблицы, итоговые RESULTS и HANDOFF | этот коммит (см. `git log`) |

## Главные выводы (о методе, не о городе)

Подробно — в `RESULTS.md`.
- **G1 (жадный по ключу цели)** совпадает с точным оптимумом в 84 / 72–75 / 93–95% задач (mean / minimax / coverage).
- **G2 (выгода/стоимость)** — 52–63 / 26–34 / 33–43% по полному ключу. По первичной метрике minimax G2 близок к G1.
- **Бюджет** (парно, v2): жёсткий бюджет резко улучшает G2 (mean 86.4% против 49.4%). G1 хуже всего при среднем бюджете.
- **Отсутствие исходных записей** (парно, v2): G1/minimax 94.9% против 36.9%.
- **Время.** При ≤16 кандидатах точный перебор занимает миллисекунды-десятки миллисекунд (полный выход CORE_SPEC до ≈125 мс в Python). Эвристику в продукте называть оптимумом нельзя.

## API модуля `k09plan` (Python ≥ 3.11, только stdlib)

**Константы.** `k09plan.METRIC_VERSION = "haversine-mm-v1"`.

**Расстояния** (`k09plan.metric`):
- `metric.dist_mm(lon1, lat1, lon2, lat2) -> int` — гаверсинус с R = 6371008.8, clamp, ⌊d·1000 + 0.5⌋.

**Задача** — `metric.Problem(points, sources, candidates, radius_m)`:
- предвычисляет миллиметры; порядок входов не важен;
- `.evaluate(idx)` — метрики плана: `unknown_count, weighted_sum_mm, weighted_mean_mm|null, max_mm|null, covered_weight, coverage_fraction, cost, selected_ids`;
- `.rows(idx)` — построчно `before_mm/after_mm/delta_mm` и `nearest_after {kind: source|hypothetical, id}`.

**Ключи целей.** `metric.OBJECTIVES = {"mean", "minimax", "coverage"}` — функции ключей CORE_SPEC (null max = ∞).

**Точный поиск** (`k09plan.exact`):
- `exact.optimize(pr, budget, max_selected, required_ids=(), excluded_ids=(), with_pareto=True)`:
  - возвращает `{status: optimal|infeasible|too_large, reason?, objectives{mean,minimax,coverage}, pareto[{cost, weighted_sum_mm, selected_ids}], evaluated, feasible_count, free_n, subsets_total}`;
  - больше 16 свободных кандидатов → `too_large` (не optimal);
  - причины infeasible: `required_count_exceeds_max_selected`, `required_cost_exceeds_budget`.
- `exact.budget_sensitivity(pr, budget, max_selected, req, exc)` — перебор по бюджетам [0, ⌊B/2⌋, B] без дублей.
- `exact.problem_digest(context, scenario)` — `"sha256:…"`:
  - не зависит от порядка массивов и от записи чисел;
  - selected_ids не входит.

**Жадные алгоритмы** (`k09plan.greedy`):
- `greedy.greedy_key(pr, objective, budget, max_selected, req, exc)` — G1.
- `greedy.greedy_ratio(..., unknown_tie="cost"|"id")` — G2 (по умолчанию) или G2id.
- Оба возвращают `{status: heuristic|infeasible, plan, steps, replaced_by_best_single?}`.

**Разрыв** (`k09plan.gap`):
- `gap.gap(objective, greedy_metrics, exact_metrics)` → `{hit, unknown_worse, abs, rel|null, greedy_better_than_exact}`;
- rel = null, если знаменатель равен 0.

**Генерация** (`k09plan.suite`):
- `suite.make_context(slice_data, data_sha256, city, category, baseline)`;
- `suite.make_scenario(...)` — генератор v1;
- `suite.make_scenario_v2(...)` — парный вложенный генератор v2.

**Валидация** (`k09plan.validate`):
- `validate.parse_import(raw)` — strict JSON:
  - не больше 256 KiB;
  - без дубликатов ключей, NaN, Infinity и 1e999;
  - typed `PlanError(code, path)`.
- `validate.validate(scenario, context) -> [{code, path}]` — проверки полей, bbox, snapshot, ID и ограничений.

**Адаптер CORE_SPEC** (`k09plan.api`):
- `api.validate_plan_scenario(input, context) -> (scenario|None, errors)`;
- `api.evaluate_plan(context, scenario, selected_ids) -> {rows, metrics, feasibility}`;
- `api.optimize_plans(context, scenario) -> {... , problem_digest, metric_version, budget_sensitivity}`;
- `api.scenario_digest(context, scenario)` — включает selected_ids.

**Эксперимент:**
- `k09plan.experiment` — план сетки, `run_one`, `summarize` (Wilson, точный McNemar и log10 p, парные контрасты);
- `scripts/run_experiment.py` — CLI.

Сверка с будущей сборкой: `results/crosscheck_tasks.json` (3 задачи с ожидаемыми objectives, Парето, чувствительностью и digest) и `results/independent/inputs.json` (34 задачи). Digest — Python-специфичный (sha256 канонического JSON) и с JS-реализацией не обязан совпадать. Сравнивать нужно планы и метрики.

## Точные команды, реально выполненные в этой сессии

Из `research/round-8-results/K09`:

```
python3 -m unittest discover -s tests -v                                     # 50 tests OK на Python 3.11.15 и 3.12.3 (venv)
python3 scripts/run_experiment.py                                            # v1: 2610 сценариев, 15660 строк, ~152 с
python3 scripts/run_experiment.py --config config/experiment_config_v2.json  # v2: 3420 сценариев, 30780 строк, ~151 с
python3 scripts/make_tables.py ; python3 scripts/make_tables.py results_v2
python3 scripts/g2_tie_variant_v1.py
python3 scripts/compare_blind.py results/independent                         # 0 mismatches (578 полей, 28 Парето, 34 чувствительности, 204 жадных)
python3 scripts/compare_recompute.py                                         # 0 mismatches (220 значений)
node results/independent/blind_exact/exact.js inputs.json out.json           # побайтно = blind_exact_out.json (Node v22.22.0)
node results/independent/blind_greedy/greedy.js inputs.json out.json         # побайтно = blind_greedy_out.json
повтор v1 и v2 с --repeats 1 на Python 3.11.15 и 3.12.3 → DETERMINISTIC_SHA256 совпадают
```

## PASS / FAIL / SKIP

**PASS:**
- 50 юнит-тестов на Python 3.11.15 и 3.12.3.
- exact совпадает с наивным перебором: 60 seeded задач в тестах и 3000 fuzz-экземпляров в обзоре.
- Слепой JS exact и G1/G2 — 0 расхождений.
- Слепой пересчёт агрегатов — 0 расхождений.
- Побайтная воспроизводимость v1 и v2 на двух версиях Python.
- После исправлений `runs.csv` v1 побайтно равен коммиту `e5cd96f`.
- Assert «greedy никогда не лучше exact» на 46 440 строках.
- Assert гарантии при размере точного плана ≤ 1.

**FAIL:** нет. Две ошибки в ожиданиях тестов этапа 2 исправлены в тестах, модуль при этом не менялся (см. STATUS этапа 2 в истории).

**SKIP:**
- Интеграция и сверка с BUILD: кода city-plan-v2 в базе нет.
- Время JS и браузера.
- Задачи больше 16 кандидатов.
- Реальные пользовательские точки.
- Библиографическая проверка гарантий жадных схем: научные хосты недоступны, сеть не использовалась.

## Источники и версии

| Что | Значение |
|---|---|
| Данные среза | `prototypes/city-evidence/web/data.js` @ `a5b5e2ddbe087c4eab8e947748cdf69dbae84a0d`; sha256 `bb2a7e6673ff4f9e46ef40df2db7830521603fd0a548ae6a581608a27e9d7d72`; читается через `git show`, проверяется в `data.load_slice` |
| Записи | shymkent/school — 15, astana/outpatient_clinic — 16 (поле group, внутри bbox) |
| Спецификация | CORE_SPEC @ `c3f6c00` |
| Среда | Python 3.11.15 (stdlib); venv Python 3.12.3 для повтора; Node v22.22.0 для слепых реализаций |
| Сеть | не использовалась |

## Ограничения

- **Synthetic-данные.** Точки, кандидаты и стоимости — synthetic, равномерные в bbox. Веса — приоритет, а не население. Радиус — параметр.
- **Срезы.** Различия срезов — это плотность записей Overture в bbox, а не свойства городов. Условие nobase — synthetic.
- **v2.** Предрегистрирован после прогона и обзора v1. Отклонения v1 перечислены в `RESULTS.md` §8.
- **Независимая проверка.** Её выполняли модели того же семейства. Аудит путей в транскриптах чистый.
- **ID.** Валидатор строже CORE_SPEC в наборе символов ID.

## Следующий шаг

1. Когда BUILD добавит city-plan-v2, прогнать его на `results/crosscheck_tasks.json` и `results/independent/inputs.json` и сравнить планы и метрики, а не digest.
2. Получить реальные или кластеризованные пользовательские точки и повторить v2.
3. Добавить в сравнение частичный перебор (пары или тройки плюс жадное дополнение) и задачи больше 16 кандидатов, явно подписанные как эвристика.
