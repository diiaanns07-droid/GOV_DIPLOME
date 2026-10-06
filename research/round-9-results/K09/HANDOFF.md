# K09 · раунд 9 · «Диплом: проверяемый эксперимент устойчивости» — STATUS

- **Задание:** `research/round-9/tasks/K09.txt`, CORE_SPEC r9, REVIEW. Ветка `codex/research-import-2026-10-05` @ `0ab1667`.
- **Ветка:** `claude/save-work-handoff-qho6eq`. Входной снимок r8 K09 — `e953ddc`; по `snapshots.json` r9 это K09.
- **Проверяемая сборка:** BUILD `claude/beautiful-clarke-sbzomj` @ `d865dd4a124291e10dd0b7bb1d9eada20d34c268`. Код равен `3e1302a`, дерево `a5d85e6`. На 2026-10-06 новее d865dd4 ничего не опубликовано.
- **Что не менялось:** общий прототип, main, чужие ветки, T1 (`research/round-3-results/K09`), r8 (`research/round-8-results/K09`).

## Этап 1 — ГОТОВ: сверка r8 с настоящим plan.js d865dd4

- **Копия BUILD:** `scripts/pin_build.py` делает байтовую копию web/, tests/ и tools/ и пишет манифест `inputs/BUILD_MANIFEST_d865dd4.json` (git blob и sha256).
- **Адаптер:** `adapter/build_plan_adapter.cjs` вызывает настоящие makeContext, validatePlanScenario, optimizePlans, sensitivity и evaluatePlan. Движок не копировался.
- **Задачи:** `scripts/make_build_tasks.py` — 6064 задачи: ind34, вся сетка v1 (2610) и вся сетка v2 (3420).
- **Сверка:** `scripts/compare_build.py` — **0 расхождений**:
  - статусы и причины infeasible;
  - feasible_count;
  - три победителя (ids, cost, unknown, wsum, max, covered);
  - Парето;
  - чувствительность к бюджету;
  - 18 787 вычислений evaluatePlan (метрики, допустимость, строки по точкам).
- **Различия API:** 14 пунктов, числа ни один не меняет. Описаны в `API_DIFF.md`, там же время BUILD:
  - Node v22: 16 кандидатов, max_selected = 3 — медиана 1.6–1.9 мс;
  - max_selected = 5 — 10.6 мс.
- **Воспроизводимость:**
  - повторная генерация задач даёт побайтно тот же файл;
  - второй прогон адаптера даёт тот же sha256 (поле времени исключено).

  Хэши — в `results/stage1/OUTPUT_HASHES.json`.

### PASS / SKIP этапа 1

**PASS:**
- сверка движка BUILD с оракулом r8 (6064 задачи);
- детерминизм.

**SKIP:**
- UI, браузер, импорт и экспорт BUILD (проверяли K07, K12, K10);
- время в браузере;
- лимит createSearch (находка K12).

### Команды

Выполнялись из `research/round-9-results/K09`:

```
python3 scripts/pin_build.py --out <tmp>/k09_build_d865dd4
python3 scripts/make_build_tasks.py --out <tmp>/s1_tasks.jsonl
node adapter/build_plan_adapter.cjs --web <tmp>/k09_build_d865dd4/prototypes/city-evidence/web --in <tmp>/s1_tasks.jsonl --out <tmp>/s1_build.jsonl --repeats 3
python3 scripts/compare_build.py <tmp>/s1_tasks.jsonl <tmp>/s1_build.jsonl results/stage1/compare_d865dd4.json    # exit 0
```

Окружение: Python 3.11.15, Node v22.22.0, linux x64.

## Этап 2 — далее

Протокол T3: сравнение nominal и robust на фиксированных сценариях исключения записей. Предрегистрация до запуска.

## Этап 3 — далее

Прогон через BUILD r9, если resilience.js появится. Иначе — независимый оракул и интеграция NOT_RUN.
