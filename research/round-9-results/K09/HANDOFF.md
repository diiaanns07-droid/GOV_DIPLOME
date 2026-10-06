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

## Этап 2 — ГОТОВ: протокол T3 предрегистрирован

Всё ниже зафиксировано этим коммитом до прогона.

- **Протокол:** `T3_PROTOCOL.md` и `config/t3_config.json`:
  - seeds 0–9;
  - семейства single, pair и cluster (k = 1, 3, 7), attribute и all_disabled;
  - размеры S, M, L (до 12 кандидатов и 25 точек), бюджеты 0.5 и 1.0;
  - 1340 задач, включая 20 stress-задач 12×25×8;
  - метрики, инварианты, ограничения интерпретации.
- **Исключения по атрибутам записей:** `config/t3_attribute_sets.json`, из data.js и evidence.js @ d865dd4:
  - Overture confidence < 0.5 — shymkent 6, astana 7;
  - QA BUILD — shymkent 7, astana 0.
- **Оракул** `k09res/resilience.py` — независимая реализация CORE_SPEC r9:
  - строгий envelope с лимитом ≤12 кандидатов, проверяемым до предвычислений;
  - baseline по случаям; nominal и robust; W и worst_case_ids; цена устойчивости;
  - digest задачи, сценария и исключений;
  - валидация непроверенного входа и работа с глубокой копией.
- **Генератор и раннер:** `k09res/t3.py`, `scripts/run_t3.py`, включая `--emit-envelopes` для будущего адаптера BUILD.
- **Тесты:** `tests/test_resilience.py` (13) и `tests/test_t3.py` (4) — **17 OK**:
  - ручная фикстура на меридиане (R·|Δφ|);
  - 36 seeded задач против наивного перебора;
  - инварианты и независимость от порядка;
  - все правила валидации; лимит до предвычислений.
- **Формат** проверен на 12 задачах в scratch. Это не прогон: результаты не смотрелись.

## Этап 3 — В РАБОТЕ: эксперимент T3 выполнен, BUILD r9 проверен

**BUILD r9.** Опубликован: `33cc635ec212e522b3e17fb0b598fad0ad602f71` (этап 2 BUILD; код resilience.js = `7077ff7`, дерево приложения то же). Закреплён, манифест — `inputs/BUILD_MANIFEST_33cc635.json`. Код resilience.js прочитан до запуска: чистый модуль, без I/O.

**Прогон T3 оракулом:** `scripts/run_t3.py` → `results/stage3/`:
- 1340 задач, ~17 с;
- инварианты (assert) выполнены во всех задачах;
- детерминированные файлы — sha256 в `results/stage3/DETERMINISTIC_SHA256.txt`.

**Интеграция с BUILD 33cc635:** `adapter/build_resilience_adapter.cjs` + `scripts/compare_t3_build.py`. На тех же 1340 envelope **0 расхождений**:
- статусы, feasible_count, same_plan, цена;
- nominal и robust: ids, cost, W, worst_case_ids;
- потери L и охват в каждом случае.

**Строгая валидация:** `scripts/validation_conformance.py`, 60 неверных и пограничных envelope:
- 54 — совпадение;
- 2 — то же решение с другим именем кода (`bad_exclusions` против `bad_id`);
- 4 — различие политики, отмеченное до запуска: BUILD строже и отклоняет пробельную метку и U+2028;
- 0 настоящих расхождений.

**Время BUILD** (Node v22, медиана):
- 12 кандидатов, 25 точек, 8 случаев, max_selected = 3 — 2.2 мс;
- stress, max_selected = 5 — 8.3 мс (максимум 9.0).

**Дальше:**
- независимая проверка (workflow: слепая JS-реализация по CORE_SPEC, обзор BUILD resilience.js, обзор оракула K09);
- T3_RESULTS.md, финальный HANDOFF.
