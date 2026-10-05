# HANDOFF — K12 раунд 8 (`city-plan-v2`: стресс и негативные планы)

Ветка `claude/save-work-handoff-xuav3q`, папка `research/round-8-results/K12/`. Общий прототип не менялся.
База проверок: BUILD `a5b5e2d` (код = кандидат `4e93f30`). Кода v2 в ней нет.

## Быстрый запуск

```bash
git fetch origin claude/beautiful-clarke-sbzomj
python research/round-5-results/K12/extract_build.py a5b5e2ddbe087c4eab8e947748cdf69dbae84a0d /tmp/ce
cd research/round-8-results/K12
python make_fixtures_v2.py                                   # fixtures_v2/, индекс, oracle_problems.json
python oracle/plan_v2_oracle.py --app-root /tmp/ce --problems oracle_problems.json --out expected/oracle_mine.json
node plan_stress.cjs --app-root /tmp/ce --expected expected/oracle_mine.json      # этап 1
```

## Как подключить реализацию BUILD

Нужен адаптер (CommonJS), который экспортирует `function ({appRoot, D, EV, ctx, requireWeb})` и возвращает:

| Функция | Обязательно | Смысл |
|---|---|---|
| `snapshot(city)` | да | текущий `source_snapshot` среза города |
| `initialState()` | да | пустое состояние |
| `importScenario(text, state)` | да | `{ok, code, state}`; при отказе `state` прежний; входной объект не менять |
| `evaluate(state)` | желательно | `{selected_ids, rows[{id, after_mm,…}], metrics{unknown_count, weighted_sum_mm, max_mm, covered_weight, cost}, feasibility{feasible}}` |
| `optimize(state)` | желательно | результат `optimizePlans`: `{status, reasons, objectives{mean, minimax, coverage}, pareto, evaluated, feasible_count, problem_digest, sensitivity}` |
| `problemDigest(state)` | желательно | для проверки независимости от порядка массивов |
| `currentState()` | если активный сценарий хранится внутри модуля | |

Пример — `adapters/reference_v2_adapter.cjs`.

## Определения, которые проверяет тест (из CORE_SPEC)

- Расстояние: гаверсинус, R = 6371008,8, `mm = Math.round(d*1000)` один раз.
- Ничья ближайшего объекта: (мм, источник раньше гипотетического, id).
- `evaluated` — число подмножеств свободных кандидатов (без required/excluded), то есть 2^|free|.
- `feasible_count` — из них подходящие по `max_selected` и бюджету.
- Цели — лексикографические ключи CORE_SPEC. ID в ключе отсортированы как строки (`c16` < `c3`).
- Парето — только по планам без unknown, минимизация (cost, weighted_sum_mm); равные пары сворачиваются
  к наименьшим ID.
- Чувствительность — бюджеты `[0, floor(B/2), B]` без дублей.
- `infeasible` с причиной: `required_cost_exceeds_budget` / `required_count_exceeds_max_selected`.
