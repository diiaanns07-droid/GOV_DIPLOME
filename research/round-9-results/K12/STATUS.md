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
| 2. Корпус устойчивости (`city-resilience-v1`), атомарность, сеть, неизменность источников | **done** на `d865dd4`; прогон на новом BUILD `33cc635` — далее |
| 3. Ограниченный fuzz на BUILD, оракул, поздние результаты в UI, итоговый handoff | **в работе**: новый BUILD `33cc635` проверен (API, корпус, v2 fuzz); fuzz устойчивости, UI и патчи — далее |

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

## Этап 2 — корпус устойчивости `city-resilience-v1` (на `d865dd4`)

- `make_resilience_fixtures.py` → `fixtures_rs/` (56 файлов + 3 рецепта), `FIXTURES_RS_INDEX.json`, `rs_oracle_problems.json`.
  - 59 конвертов: 13 допустимых, 46 недопустимых, из них 4 с пометкой policy.
  - ID записей настоящие (`data.js` sha256 `bb2a7e66…`), остальное синтетика.
  - Допустимые A01–A13: оба города, 7 случаев, 12 кандидатов × 25 точек, одинаковые наборы, все записи исключены,
    Unicode-id и HTML в label, 120 code points с эмодзи, перестановка, 0 кандидатов, `infeasible`, ровно 256 KiB.
  - Недопустимые N01–N49:
    - ID кандидата и поддельные, чужой категории и города source ID;
    - `base` и повтор id, 8 случаев, 0 случаев, 13 и 17 кандидатов;
    - пустое исключение и повтор внутри случая;
    - label пустой, 121 code point, `\n`, U+0007, число;
    - лишнее поле (вероятность), `derived_results` в конверте и в plan;
    - версия, plan v1, чужой snapshot, ошибки plan;
    - id с HTML, длиной 65 и не в NFC; `__proto__`;
    - повтор ключа, NaN, Infinity, `1e999`, глубина 40 и 20 000, 262 145 байт, обрезанный JSON, корень-массив,
      одиночный суррогат.
- `oracle/resilience_oracle.py` — независимый оракул, написан только по CORE_SPEC r9: строгий JSON, валидация конверта,
  точный перебор, худший вектор, nominal и robust, цена устойчивости. ID сравниваются как в JS (UTF-16).
  - Самопроверка корпуса: **59/59** совпадений меток (`results/stage2_corpus_selfcheck_oracle.json`).
  - Ожидания: `expected/rs_oracle_d865dd4.json` (13 задач). В A04 и A06 устойчивый план отличается от обычного,
    в остальных совпадает: цена 0, преимущество не выдумывается.
- `resilience_stress.cjs` (группы R и X).
  - **BUILD `d865dd4`:**
    - R — 59 NOT_RUN: `resilience.js` нет;
    - X — 6/6 PASS (`results/stage2_resilience_d865dd4.json`): v2- и v1-импорт отклоняют все 59 конвертов
      типизированным кодом; `plan` каждого допустимого конверта — валидный v2, его mean-оптимум равен nominal
      оракула; plan-уровень негативов (13 кандидатов v2 принимает — отказ остаётся задачей устойчивости);
      `CITY_EVIDENCE`, `data.js` и замороженный контекст не меняются; сети нет.
  - **Самопроверка харнесса** (адаптер к оракулу — не BUILD): 65/65 PASS.
  - **Контроль чувствительности харнесса:**
    - испорченные ожидания дают ровно 2 FAIL (A04 robust, A06 цена);
    - адаптер, сбрасывающий состояние при отказе, даёт FAIL на всех 46 отказах.
- `ui_r9_browser.cjs`, группа B, на `d865dd4`: 5 PASS, 1 NOT_RUN (`results/stage2_ui_browser_d865dd4.json`).
  - v2-импорт в UI отклоняет 56 конвертов, план и город не меняются, сообщение есть;
  - v1-импорт — то же;
  - `CITY_EVIDENCE` на странице без изменений;
  - внешних запросов 0;
  - панели устойчивости нет — NOT_RUN.
- **Новый BUILD:** при повторной проверке после этапа 2 найден `33cc635` («BUILD round 9 stage 2»), в нём есть
  `web/resilience.js`. Явная проверка этого SHA — следующий шаг.

## Этап 3 — новый BUILD `33cc635ec212e522b3e17fb0b598fad0ad602f71` (промежуточный итог)

- BUILD опубликовал этапы 1–2 раунда 9: `e990f01` → `fb768b2` → `7077ff7` → `33cc635`.
  - Копия байтами, manifest `manifests/33cc635_extract.json` (206 файлов).
  - Прочитаны до запуска: `web/resilience.js` целиком, диффы `plan.js`, `whatif.js`, `app.js`, `index.html`,
    `check_all.py`, `test_serve.py` (поднимает только 127.0.0.1).
  - `data.js` байт-в-байт тот же (`bb2a7e66…`), поэтому ожидания оракула общие с `d865dd4`.
- BUILD закрыл r8 F1 своим патчем: публичные `evaluatePlan` и `createSearch` вызывают `validatePlanScenario`.
  r8 F2 (`whatif.js`) применён.
- **`api_guard.cjs` на `33cc635`:** 33 PASS, **1 FAIL**, **1 ADVISORY**, 0 NOT_RUN → `results/stage3_api_guard_33cc635.json`.
  - Все 20 прежних FAIL `d865dd4` теперь PASS. Устойчивость: 13/16 кандидатов, 8 случаев, изменение после
    validate, кандидат вместо записи, `base` — типизированные отказы за 5–25 мс. 12 × 7 = 4096 наборов, `optimal`.
  - Изменение конверта посреди поиска ответ не меняет.
  - **FAIL `rs/R_selected_null`:** `evaluateResilience(ctx, env, null)` → `TypeError: selectedIds is not iterable`
    вместо типизированного кода.
  - **ADVISORY `v2/I_internal_export`:** `PL.internal.createSearch` экспортирован без валидации; непроверенный
    объект с 20 кандидатами даёт поиск на 1 048 576 наборов. CORE_SPEC допускает внутренний проверенный путь, но
    этот путь достижим снаружи.
- **Корпус устойчивости `resilience_stress.cjs` на `33cc635`:** 63 PASS, 0 FAIL, **2 ADVISORY**
  → `results/stage3_resilience_33cc635.json`.
  - Все 46 отказов: типизированный код, состояние прежнее, сети нет, `CITY_EVIDENCE` не меняется.
  - Все 13 допустимых совпали с независимым оракулом K12: nominal и robust ID, худший вектор, худшие случаи,
    `evaluated`, `feasible_count`, цена устойчивости. Дубль случая и перестановка дают те же планы.
  - X1–X6 PASS.
  - ADVISORY (policy): N35 — label с U+202E (bidi override, категория Cf) принят; N49 — одиночный суррогат принят.
- **Собственные проверки BUILD на копии:** `check_all` exit 0 (plan 164 проверки, resilience 111, whatif, facts,
  unittest; `evidence.js` rebuild — SKIP).
- **Харнесс K12 r8 на `33cc635`:**
  - `plan_stress` 73 PASS + 2 ADVISORY;
  - `stage2_runtime` 33 PASS, 0 FAIL, 6 SKIP;
  - `plan_fuzz` seed 9, 500 случаев с оракулом, `--strict-api-guard`: **PASS**. API 20/30/40 →
    `too_many_candidates` за 0,6–4,1 мс. Худший случай v2 32 мс, async-кусок 3 мс.

## Этап 3 — `33cc635`: fuzz устойчивости, UI, порядок ID, патч r9b

- **`resilience_fuzz.cjs`** — ограниченный fuzz настоящего `resilience.js`.
  - Бюджет: seed, число случаев, лимит времени. Строгий PASS/FAIL, `--replay`, сжатие до минимального repro.
  - Пакетная сверка с независимым оракулом K12.
  - 10 свойств:
    - принятие валидного конверта;
    - вход не изменяется;
    - независимость от порядка;
    - дубль случая ни на что не влияет;
    - robust не хуже nominal по W, nominal не хуже по L_base, цена ≥ 0, при совпадении планов цена 0;
    - W = максимум по случаям, `worst_case_ids` полны;
    - `evaluate` = `optimize`;
    - новый случай не уменьшает W;
    - счётчики и строгий JSON;
    - отмена не даёт `optimal`.
  - 16 видов недопустимых мутаций.
  - Seed 21, 300 конвертов: **PASS** (3000 проверок свойств, 300 сверок с оракулом; в 44 случаях robust ≠ nominal,
    25 `infeasible`) → `results/stage3_resilience_fuzz_33cc635_seed21.json`.
  - Seed 22, 150 конвертов, все с Unicode-ID (129 с не-ASCII кандидатами): **PASS** → `..._seed22_unicode.json`.
  - Контроль: обёртка «robust := nominal» поймана (5 нарушений свойств, 10 расхождений с оракулом); repro сжат
    до 1 точки.
- **`ui_r9_browser.cjs` на `33cc635`:** 10 PASS, 1 NOT_RUN → `results/stage3_ui_browser_33cc635.json`.
  - B1–B3: конверты отклоняются UI v1 и v2 без изменения состояния, данные среза неизменны.
  - L1–L5: смена ручного выбора во время поиска; объяснение отбрасывается после смены выбора; смена города
    сбрасывает результат; применение только кнопкой; смена бюджета.
  - Z1–Z2: сети и ошибок нет.
  - B4 (панель устойчивости, смена случаев) — **NOT_RUN**: в `33cc635` UI устойчивости нет.
  - Браузерный страж r8 `ui_gate_browser`: 9/9.
- **`id_order_probe.cjs`:** при точном равенстве JS BUILD выбирает `𝔸` (UTF-16), а Python-оракулы BUILD — `ﬀ`
  (кодовые точки).
  - Расхождение в v2 mean, nominal, robust и порядке `worst_case_ids` (`results/stage3_id_order_probe_33cc635.json`).
  - Оракул K12 r9 совпадает с JS. **Собственное ограничение:** оракул K12 r8 (v2) сортирует как Python.
- **Патч `fixes/build_33cc635_k12_r9b.patch`** (G1–G4, `FIX_PROPOSALS.md`) на копии:

  | Проверка | Результат |
  |---|---|
  | `api_guard` | 35/35 |
  | Корпус | 65/65 |
  | `resilience_fuzz` | PASS |
  | `id_order_probe` | JS = Python BUILD 4/4 |
  | Новые тесты | 11/11 и 2/2; на исходном `33cc635` — 7 FAIL и 2 FAIL |
  | `check_all` | exit 0 (`expected_*.json` без изменений, unittest 52) |
  | Браузерные тесты BUILD | smoke 24, plan_smoke 52, whatif_smoke 32, plan_keyboard 14 — как на исходном `33cc635` |

- BUILD снова обновился: **`e1cbc3f`** («round 9 stage 3»). Его проверка — следующий шаг.
