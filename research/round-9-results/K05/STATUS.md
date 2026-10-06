# K05 round 9 — точный устойчивый поиск: STATUS

Ветка `claude/optimistic-davinci-1oiqs9`. Задание `research/round-9/tasks/K05.txt`, CORE_SPEC r9 @ codex/research-import-2026-10-05 (0ab1667).
**Проверенная сборка: `d865dd4a124291e10dd0b7bb1d9eada20d34c268`** (`claude/beautiful-clarke-sbzomj`; дерево приложения = 3e1302a, `git diff --quiet` пуст), извлечена `git archive` во временный каталог. Общий прототип не менялся. Мой r8: `1804f5b`.

| Этап | Статус |
|---|---|
| 1. r8 oracle/fixtures против plan.js d865dd4 через адаптер; API-guard repro | **done** |
| 2. resilience-модуль поверх API BUILD | не начат |
| 3. gold/оракул/свойства/benchmark, полный handoff | не начат |

## Этап 1 — результаты на d865dd4 (реально выполнено)
| Проверка | Результат |
|---|---|
| `node research/round-9-results/K05/stage1/adapter_r8_vs_build.cjs --app-root <d865dd4>/prototypes/city-evidence --cases research/round-8-results/K05/runs/cases_dump_a5b5e2d.json` | **31 PASS / 0 FAIL**: 28 задач r8 (оба города, обе категории, 0..16 кандидатов, 2 infeasible, пустой baseline, все кандидаты в одной точке) — статус, feasible_count, 3 оптимума (ids+метрики), Парето, pareto_excluded, чувствительность, инвариантность к перестановке; + 3 ручные: три оптимума экватора, tie-break (source<hypothetical<id), пустой план |
| r8 Python-оракул на ОТВЕТАХ СБОРКИ (`--oracle-dump` → `oracle.py`) | **28/28** |
| Записи срезов: data.js a5b5e2d = d865dd4 (blob e61ff99); адаптер сверяет записи категории задачи с `makeContext` сборки | совпали |
| `stage1/repro_api_guard.cjs` (дочерние процессы, таймаут 8 с) | **дефект подтверждён**: `validatePlanScenario` отвергает 20 (`too_many_candidates`), но прямой `createSearch` без валидации перебирает 2^20/2^22 и зависает на 30 (2^30); проверенный объект не заморожен — дописанные после валидации кандидаты + `max_selected` обходят лимит (22 → таймаут) |

Адрес дефекта: `web/plan.js:213` `createSearch` (и `:171` `evaluatePlan`) используют переданный объект без повторной проверки; маски `1 << k` (`:236-242`) при >31 свободных кандидатах ещё и переполняются (по чтению кода, не запускалось).

## Предложение (не применено к прототипу)
`patches/plan_api_guard.patch` — 2 строки: `createSearch` и публичный `evaluatePlan` (без `pre`) повторно вызывают `validatePlanScenario(sc, ctx, {requirePoints:false})` до предвычислений. На копии d865dd4 + patch:
- repro: все >16 отвергнуты `too_many_candidates`, зависаний нет (`runs/api_guard_patched_copy.json`);
- тесты сборки: `node tests/plan.cjs` — all plan checks passed; `whatif.cjs` — passed; `conformance.cjs` — passed;
- браузер `tests/plan_smoke.cjs` (Playwright): 52 PASS / 0 FAIL и без patch, и с patch; отличие только во времени (`runs/build_plan_smoke_*.txt`).

## Следующий шаг
Этап 2: `research/round-9-results/K05/resilience.js` поверх API plan.js сборки.
