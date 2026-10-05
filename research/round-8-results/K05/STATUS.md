# K05 round 8 — точный оптимизатор и оценка плана (city-plan-v2): STATUS

Ветка `claude/optimistic-davinci-1oiqs9`. Задание `research/round-8/tasks/K05.txt`, спецификация `research/round-8/CORE_SPEC.txt` @ codex/research-import-2026-10-05 (c3f6c00).
Целевая база данных: `a5b5e2ddbe087c4eab8e947748cdf69dbae84a0d` (`claude/beautiful-clarke-sbzomj`, `prototypes/city-evidence/web/{data,evidence,facts,whatif}.js`), извлечена `git archive` во временный каталог. Общий прототип не менялся; модуль в BUILD **не интегрирован**.

| Этап | Статус |
|---|---|
| 1. validate/evaluate/optimize, полный перебор ≤16, ограничения, ничьи | **done** (checkpoint 1) |
| 2. три objective, Парето, counters/progress/cancel, статусы | частично в коде, тесты — следующий шаг |
| 3. edge cases, benchmark max-size, независимый оракул, README/API | не начат |

## Этап 1 — сделано
- `plan.js`: строгий JSON (≤256 KiB, повтор ключа, NaN/Infinity/1e999), `validatePlanScenario` (типизированные ошибки code/message/path), `prepareProblem` (расстояния в мм один раз: m·(src+n) гаверсинусов), `evaluatePlan` (строки до/после/дельта, ns source/candidate, метрики CORE_SPEC), `optimizePlans` (полный перебор 2^n масок, required/excluded/бюджет/max_selected, лексикографические ключи mean/minimax/coverage, ничьи source<candidate<id), digest задачи/сценария, независимые от порядка массивов.
- `tests/helpers.cjs` (загрузка сборки по `--app-root`, snapshot функцией сборки `whatif.sourceSnapshot`, synthetic фикстуры с seed), `tests/test_stage1.cjs`.

## Проверки (реально выполнены, node 22)
- `node research/round-8-results/K05/tests/test_stage1.cjs --app-root <a5b5e2d>/prototypes/city-evidence` → 17 passed, 0 failed (`runs/stage1_a5b5e2d.json`): ручной пример на экваторе (d = R·Δλ), ограничения, infeasible с причиной, ничьи, пустой baseline, валидация, строгий JSON, перестановки, счётчик гаверсинусов, оба города × обе категории (кандидаты synthetic).
- Мутация (кандидат выигрывает ничью у источника) → 1 FAIL: тест ничьей не вырожденный.

## Синтетика
Кандидаты, стоимости, веса, бюджеты в тестах — SYNTHETIC (`syn_*`, seed). Не цены, не население, не городская статистика.

## Следующий шаг
Этап 2: тесты Парето/статусов/cancel/progress и async-API: `node research/round-8-results/K05/tests/test_stage2.cjs --app-root …`.
