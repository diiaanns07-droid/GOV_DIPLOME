# K06 round 8 — независимый оракул city-plan-v2 и проверка оптимальности (HANDOFF)

Роль: K06 (не BUILD). Ветка: claude/ecstatic-curie-hzfzn0 (начало раунда от 339fd3935ec4e3b57d8cd743cd02c26aba01c0a7).
Задание: origin/codex/research-import-2026-10-05 @ c3f6c00, research/round-8/tasks/K06.txt, CORE_SPEC.txt.
База прототипа: claude/beautiful-clarke-sbzomj @ a5b5e2ddbe087c4eab8e947748cdf69dbae84a0d (191 файл, blob id сверены).
**В базе нет реализации city-plan-v2** (только what-if v1). Интеграция в BUILD НЕ проверялась; JS сборщика не запускался.
Статус: все три этапа выполнены.

## API модуля `plan_oracle.py` (Python 3, stdlib)
| Функция | Возвращает |
|---|---|
| `parse_strict(text)` | объект; отказ: > 256 KiB, дубликаты ключей, NaN/Infinity/1e999, плохой JSON |
| `validate(scenario, context)` | нормализованный сценарий или `PlanError(code, detail)` |
| `evaluate(context, scenario, selected_ids)` | `rows` (before/after/delta в мм, nearest {kind, id}), `metrics`, `feasible`, `reasons` |
| `optimize(context, scenario)` | `status` (optimal/infeasible + reasons), `objectives.{mean,minimax,coverage}`, `pareto`, `evaluated`, `feasible_count`, `problem_digest`, `metric_version` |
| `sensitivity(context, scenario)` | бюджеты `[0, B//2, B]` без дублей → status + победители |
| `problem_digest(context, scenario, include_selected=False)` | sha256, не зависит от порядка массивов; selected_ids только при include_selected |
`context = {city_id, bbox, source_snapshot, records: [{id, lon, lat, group}]}`.
Метрика `haversine-mm-v1`: R = 6371008.8, clamp [0, 1], мм = floor(d·1000 + 0.5), расстояния предвычисляются один раз.
Решения, где спецификация оставляет выбор: ничья мм → source раньше hypothetical, затем ID; `evaluated` = 2^(число
свободных кандидатов) или 0 при невыполнимых required (не сравнивается между реализациями); Парето — только полные
планы (unknown_count = 0), равные пары → наименьший sorted IDs.

## Этапы
1. **Оракул** — `plan_oracle.py`, `test_plan_oracle.py` (13 тестов; ручной пример на меридиане, расстояния по замкнутой
   формуле R·Δφ). Найдена и исправлена собственная ошибка: ничья source/hypothetical сравнивалась строкой.
2. **Gold** — `gold_bruteforce.py` (независимый решатель, без общего кода), `make_gold.py` → `fixtures/gold_cases.json`:
   96 задач (seed 820261005): 12 именованных SYNTHETIC граничных + 24 перестановки + 24 SYNTHETIC случайных +
   12 SYNTHETIC с расходящимися целями + 24 на РЕАЛЬНЫХ записях Overture (data.js базы a5b5e2d, sha256 bb2a7e66…)
   с синтетическими точками, кандидатами и условными стоимостями. 87 optimal, 9 infeasible. `test_gold.py` (4 теста).
3. **Метаморфные свойства, benchmark, сравнение чужой реализации** — `test_metamorphic.py` (8 свойств: бюджет и
   max_selected монотонны, добавление кандидата, только пустой план без кандидатов, больше исходных записей не
   увеличивает расстояния, дорогой дубликат не выигрывает, Парето недоминируем и покрывает все полные планы,
   масштаб весов, метрики победителя = evaluate); `benchmark.py`; `compare_candidate.py --candidate-json`;
   `run_candidate_node.cjs` (Node-обвязка для модуля с `optimizePlans`); `harness_selftest.py`.

## Реально выполненные проверки (Python 3.11.15, Node 22)
| Команда | Результат |
|---|---|
| `python3 -m unittest test_plan_oracle test_gold test_metamorphic` | 25 OK |
| `python3 compare_candidate.py --problems fixtures/gold_cases.json --self-test` | 96 PASS; 5 внедрённых дефектов пойманы; camelCase-адаптер PASS |
| `python3 harness_selftest.py` | неверная заглушка: 96 FAIL, код 1; эхо верных ответов через Node: 96 PASS, код 0 |
| `python3 benchmark.py --json out/benchmark.json` | moderate (10 канд., 10 точек) ≈ 1 мс; max (16 канд., 25 точек, k=5) ≈ 50 мс, 65 536 подмножеств; max со всеми 6 885 допустимыми наборами ≈ 0,3 с |
| повторная генерация `fixtures/gold_cases.json` | побайтно идентична |
Время — только для этого Python-оракула, не для браузера.

## Как проверить JS сборщика (когда появится)
```
cd research/round-8-results/K06
python3 compare_candidate.py --problems fixtures/gold_cases.json --export /tmp/problems.json
node run_candidate_node.cjs <путь к модулю с optimizePlans> /tmp/problems.json /tmp/js_out.json <SHA сборки>
python3 compare_candidate.py --problems fixtures/gold_cases.json --candidate-json /tmp/js_out.json --json /tmp/report.json
# то же для out/bench_problems.json (размер max)
```
Сравниваются status, feasible_count, metric_version, победители трёх целей и их метрики, Парето. Отсутствующий
случай — MISSING (не PASS). При другом выборе ничьей source/hypothetical отличаться будет только `nearest`, не метрики.

## Пересборка fixture
`python3 research/round-6-results/K06/extract_build.py /tmp/r8 a5b5e2ddbe087c4eab8e947748cdf69dbae84a0d` (из корня),
затем `python3 make_gold.py --app-root /tmp/r8`; без `--app-root` — только синтетика.

## Ограничения
- Полезность — только геометрические расстояния по прямой до выбранных точек в срезе; веса — приоритет пользователя,
  стоимости — условные; это не население, не тенге и не прогноз социальной пользы.
- «Оптимум» — только среди введённых кандидатов и ограничений, не лучший план города.
- Строгий JSON-валидатор оракула покрывает спецификацию, но UI-путь импорта сборщика не проверялся.
- gold-решатель использует ту же формулу из спецификации (иначе это была бы другая метрика); независимость — в переборе,
  метриках, ключах и Парето.
