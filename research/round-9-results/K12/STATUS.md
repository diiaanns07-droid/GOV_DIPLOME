# STATUS — K12, раунд 9: негативная проверка и границы API

- **Роль:** K12 (не BUILD). Ветка `claude/save-work-handoff-xuav3q`.
- **Задание:** `research/round-9/tasks/K12.txt`, `TASK.txt`, `CORE_SPEC.txt`, `REVIEW.txt` @ `codex/research-import-2026-10-05` `0ab1667`.
- **Проверяемая сборка:** BUILD `claude/beautiful-clarke-sbzomj` @ `d865dd4a124291e10dd0b7bb1d9eada20d34c268`
  (код = `3e1302a`), закреплена в `round-9/snapshots.json`.
  - Копия извлечена байтами (`research/round-5-results/K12/extract_build.py`), git blob сверен.
    Manifest: `manifests/d865dd4_extract.json`, 199 файлов.
- **Новый BUILD раунда 9 не опубликован.** На момент проверки (2026-10-06) последняя запись ветки BUILD — `d865dd4`;
  `web/resilience.js` нет ни в одной ветке origin.
  - Поэтому интеграция `city-resilience-v1` — **NOT_RUN**. Пробы и адаптер для неё готовы и запустятся сами,
    как только появится `web/resilience.js`.

## Этапы

| Этап | Статус |
|---|---|
| 1. Повторная проверка F1 и границ прямого API, патч и регрессионный тест | **done** |
| 2. Корпус устойчивости (`city-resilience-v1`), атомарность, сеть, неизменность источников | следующий |
| 3. Ограниченный fuzz на BUILD, оракул, поздние результаты в UI, итоговый handoff | — |

## Этап 1 — границы прямого API `plan.js`

- `api_guard.cjs` — переносимый модуль.
  - Каждая проба выполняется в отдельном дочернем процессе со сторожем 10 с.
  - Размеры: 17 и 20 кандидатов. 2^30 не запускается.
  - Вердикты: PASS — типизированный отказ быстрее 200 мс до тяжёлой работы; FAIL; NOT_RUN.
  - Адаптеры:
    - `adapters/plan_v2_api_adapter.cjs` — публичные `createSearch`, `optimizePlans`, `sensitivity`,
      `evaluatePlan` без UI и импорта;
    - `adapters/resilience_api_adapter.cjs` — имена API из CORE_SPEC r9.
- **Исходный `d865dd4`: 2 PASS, 20 FAIL, 9 NOT_RUN** → `results/stage1_api_guard_d865dd4.json`.
  - Это известный исходный repro r8 F1 и его расширение по CORE_SPEC r9, а не новая регрессия.
  - Через UI и импорт всё это недостижимо: оба пути валидируют до поиска. Это не удалённая атака на сервер.
  - Размер:
    - `createSearch`: 17 кандидатов → объект поиска на 131 072 набора, 20 → 1 048 576, без отказа;
    - `optimizePlans`: 17 → `optimal` (131 072 набора, 129 мс), 20 → `optimal` (1 048 576, 116 мс);
    - `sensitivity` и `evaluatePlan` с 17 кандидатами принимаются.
  - Объект прошёл `validate`, затем дополнен до 17 кандидатов → `optimal`.
  - Типы и значения:
    - вес `"5"` → `total_weight: "0523451"` (сложение строк);
    - стоимость `"100"` принимается;
    - `lon: NaN` → `weighted_sum_mm` = NaN (в JSON `null`) при `unknown_count` 0;
    - вес −50, повтор ID кандидата, `max_selected` 99, кандидат вне bbox, чужой `source_snapshot` принимаются;
    - категория `hospital` и `city_id` astana в контексте Шымкента считаются по чужому срезу.
  - Неизвестный `required_ids` → нетипизированный `TypeError` вместо кода.
  - **Изменение переданного объекта между шагами поиска меняет ответ.** Бюджет читается из живого объекта:
    у неизменной задачи 382 допустимых набора, после смены бюджета 0 на середине поиска — 57.
  - Контроли PASS: валидные 16 кандидатов через прямой API; `validate` возвращает независимую копию.
- **Патч `fixes/build_d865dd4_k12_r9.patch`** (sha256 `683021cd…c514`) включает:
  - `plan.js`: `evaluatePlan` и `createSearch` валидируют вход (`validatePlanScenario`) до `precompute` и работают
    только с чистой копией. `optimizePlans` и `sensitivity` идут через `createSearch`.
  - `whatif.js`: версия проверяется раньше лишних полей (F2 r8).
  - Новый регрессионный тест BUILD `tests/plan_api_guard.cjs`, 19 проверок.
  - Применение проверено двумя способами: `git apply --cached --check` против дерева `d865dd4` (временный индекс) — OK;
    `patch -p3` на свежей копии даёт байт-в-байт проверенные файлы.
  - Патч r9 заменяет r8 `build_d865dd4_k12.patch`: F1 закрывается валидацией, F2 включён.
- **На копии с патчем:**

  | Проверка | Результат |
  |---|---|
  | `api_guard.cjs` | 22 PASS, 0 FAIL, 9 NOT_RUN |
  | Новый `tests/plan_api_guard.cjs` | 19/19; на исходном `d865dd4` — 15 FAIL, т.е. тест ловит дефект |
  | BUILD `tools/check_all.py` | exit 0: plan 156, whatif 71, facts 44, unittest; `evidence.js` rebuild — SKIP |
  | Браузерные тесты BUILD | `smoke` 24/24, `plan_smoke` 52/52, `whatif_smoke` 32/32 |
  | Харнесс K12 r8: `plan_stress` | 73 PASS + 2 ADVISORY (политика `derived_results`, имя причины), 0 FAIL |
  | Харнесс K12 r8: `stage2_runtime` | 33 PASS, 0 FAIL, 6 SKIP; E2a исправлен |
  | Харнесс K12 r8: `plan_fuzz` | 300 случаев с оракулом, `--strict-api-guard`, PASS |
  | Харнесс K12 r8: `ui_gate_browser` | 9/9 |
- **Окружение:** Linux, Node 22.22.0, Python 3.11.15, Playwright 1.56.1 + Chromium. Windows — NOT_RUN.

## Ограничения этапа 1

- Порог «до тяжёлой работы» (200 мс) выбран K12, в CORE_SPEC числа нет.
- Пробы устойчивости R* — NOT_RUN: модуля нет. Адаптер написан по именам CORE_SPEC r9. Если BUILD назовёт
  экспорт иначе, нужно поправить адаптер; это ошибка адаптера, а не продукта.
- Решение о применении патча за BUILD; общий прототип K12 не менял.
