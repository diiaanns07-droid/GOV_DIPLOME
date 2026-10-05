# K05 round 8 — точный оптимизатор и оценка плана (city-plan-v2): STATUS

Ветка `claude/optimistic-davinci-1oiqs9`. Задание `research/round-8/tasks/K05.txt`, спецификация `research/round-8/CORE_SPEC.txt` @ codex/research-import-2026-10-05 (c3f6c00).
**Целевая база проверки: `a5b5e2ddbe087c4eab8e947748cdf69dbae84a0d`** (`claude/beautiful-clarke-sbzomj`, `prototypes/city-evidence/web/{data,evidence,facts,whatif}.js`), извлечена `git archive` во временный каталог; отпечаток среза — функцией сборки `whatif.sourceSnapshot`. Общий прототип не менялся. **Модуль в BUILD не интегрирован**; проверка интеграции не заявляется.

| Этап | Статус | Проверка (a5b5e2d) |
|---|---|---|
| 1. validate/evaluate/optimize, полный перебор ≤16, ограничения, стабильные ничьи | **done** | `test_stage1.cjs` 17 PASS / 0 FAIL / 0 SKIP |
| 2. три цели, точный Парето, counters/progress/cancel, optimal/infeasible/incomplete, async | **done** | `test_stage2.cjs` 24 PASS (12 сценариев = наивный перебор) |
| 3. краевые случаи, бенчмарк max-size, независимый оракул, README/API | **done** | `test_stage3.cjs` 15 PASS; оракул 28/28; бенчмарк 4/4 async=sync |

## Команды
См. `README.md` → «Команды». Результаты: `runs/stage{1,2,3}_a5b5e2d.json`, `runs/cases_dump_a5b5e2d.json`, `runs/oracle_a5b5e2d.json`, `runs/benchmark_a5b5e2d.json`.

## Проверки, найденные и исправленные ошибки
- Мутации: ничья кандидат≥источник → 1 FAIL (stage1); Парето `<=` → 7 FAIL (stage2); «sum раньше covered» в ключе coverage → оракул 27/28. «unknown раньше covered» — эквивалентный мутант (unknown>0 только у пустого плана при пустом baseline, его covered=0) — задокументировано, не дефект тестов.
- Исправлено в своём коде: чувствительность в async шла синхронно (блокировала бы UI) → чанками.
- Исправлено в своих тестах: фикстура «coverage важнее суммы» не покрывала нужные точки (2 vs 3) → перестроена; модуль не менялся.

## Синтетика и источники
Кандидаты, стоимости, веса, бюджеты — SYNTHETIC (`syn_*`, seed; ручные экваториальные фикстуры `SYNTHETIC-*`). Реальные только записи срезов Overture из data.js сборки (K10 r3, выпуск 2026-09-23.1) — observed_secondary, не реестр города. Python-оракул независим (itertools/кортежи/O(N²)); оракул K06 не ожидался.

## Ограничения
UI, «Применить», шаблонное объяснение и Web Worker — задача BUILD (модуль даёт async-чанки, same_plan_as, ns/kind). Миграции v1→v2 нет (режимы раздельны). Время бенчмарка машинно-зависимо.

## Следующий шаг
BUILD: подключить `plan.js` в `web/` по README, затем прогнать три `test_stage*.cjs` и оракул с `--app-root <новый SHA>` и сообщить SHA.
