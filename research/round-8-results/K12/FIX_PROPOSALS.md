# Предложения по исправлению — K12, раунд 8

- **Цель:** BUILD `claude/beautiful-clarke-sbzomj` @ `d865dd4a124291e10dd0b7bb1d9eada20d34c268`.
  - Код `city-plan-v2` (`web/plan.js`, `web/plan-ui.js`) появился после снимка раунда `a5b5e2d`.
  - Копия извлечена байтами (`extract_build.py`): 199 файлов, git blob сверен.
- **Патч:** `fixes/build_d865dd4_k12.patch`, sha256 `1f01993b…a700a`.
  - Применяется из корня репозитория: `git apply research/round-8-results/K12/fixes/build_d865dd4_k12.patch`.
  - K12 общий прототип не меняет. Применять или нет, решает BUILD.
  - Патч проверен на свежей копии `d865dd4`: `patch -p3` даёт байт-в-байт ту копию, на которой шли тесты.
    - `plan.js` sha256 `c5b30e38…`;
    - `whatif.js` sha256 `456dc47e…`.

## F1 — ADVISORY (API): отказ до перебора и в `createSearch`

- **Наблюдение.** `createSearch` и `optimizePlans` не проверяют число кандидатов.
  - Через интерфейс и импорт это не воспроизводится: `startSearch` и `importPlanScenario` сначала вызывают
    `validatePlanScenario` (`too_many_candidates`). Это подтверждено и в браузере, проверка U1.
  - Прямой вызов модуля с непроверенным объектом (`limits_child.cjs`, дочерний процесс со сторожем 20 с):

    | Кандидатов | Ответ | Перебрано | Время |
    |---|---|---|---|
    | 20 | `optimal` | 1 048 576 | 97 мс |
    | 30 | `optimal` | 1 073 741 824 | 18,5 с |
    | 40 | зависание | — | процесс снят через 20 с |

  - 20 кандидатов выходят за предел CORE_SPEC (16), но ответ подписан `optimal`. При 32 и более свободных
    кандидатах `1 << k` к тому же переполняется.
- **Исправление** (3 строки в начале `createSearch`): типизированный отказ `PlanError("too_many_candidates")` до
  `precompute` и до любого перебора.
- **Проверено на копии с патчем:**
  - `plan_fuzz.cjs --strict-api-guard`, 200 случаев с оракулом: PASS. API 20/30/40: отказ за 1,5–2,9 мс,
    `evaluated` 0.
  - `tools/check_all.py`: тот же результат, что без патча (plan 156 проверок, whatif 71, facts 44,
    unittest 44 OK; `evidence.js` rebuild — SKIP, нет shapely/pyproj).
  - Браузерные тесты BUILD: `plan_smoke.cjs` 52/52, `whatif_smoke.cjs` 32/32.
  - `plan_stress.cjs`: 73 PASS + 2 ADVISORY, как без патча.
- **Repro без патча:**

  ```bash
  node plan_fuzz.cjs --app-root <копия d865dd4> --adapter adapters/build_v2_plan_adapter.cjs --cases 1 --no-oracle
  # → ADVISORY limits/api_refuses_before_enumeration
  ```

  С `--strict-api-guard` та же находка даёт FAIL.

## F2 — ADVISORY (v1): `whatif.js` должен называть чужую версию раньше лишних полей

- **Наблюдение.** v1-импорт отклоняет файл `city-plan-v2` кодом `unknown_field`, потому что поле `candidates`
  проверяется раньше версии. Пользователь не узнаёт, что это файл другого режима.
  - v2 (`plan.js`) делает правильно: для файла v1 возвращает `wrong_version` с подсказкой.
- **Исправление** (2 строки): если `schema_version` задан и не равен `city-whatif-v1` — `bad_version` до проверки
  полей. Файл без `schema_version` по-прежнему получает `missing_field`.
- **Проверено на копии:**
  - `stage2_runtime.cjs`: E2a PASS, advisory 0;
  - `tests/whatif.cjs` (71 проверка) PASS;
  - `whatif_smoke.cjs` 32/32;
  - модуль раунда 7 `whatif_import_stress.cjs`: 47/49, как без патча (P03 — расхождение моей фикстуры, см. ниже).

## Не дефекты: CORE_SPEC допускает обе политики (для сведения BUILD и координатора)

| # | Где | BUILD `d865dd4` | Эталон K12 | Как считает тест K12 |
|---|---|---|---|---|
| P1 | поддельные `derived_results` | отказ `forged_derived` (сверяет с пересчётом) | принимает как данные, пересчитывает | ADVISORY: оба варианта соответствуют «не доверяет derived_results»; полезная нагрузка не исполняется и не попадает в вывод |
| P2 | имя причины `infeasible` | `required_exceeds_max_selected` | `required_count_exceeds_max_selected` | смысл обязателен, имя — ADVISORY |
| P3 | `evaluated` при `infeasible` | 0 (перебор не запускался) | 2^\|free\| (перебор был, подходящих нет) | не сравнивается: CORE_SPEC не определяет |
| P4 | коды отказов | 16 иных имён (`bad_points`, `too_many_candidates`, `unknown_ref`, `required_excluded_overlap`, `bad_shape` для лишних полей точек, `bad_json` для глубины) | словарь эталона | `code_mismatch`, FAIL только с `--strict-codes` |

- **Следствие P1 для пользователя.** Файл, сохранённый другой версией прототипа (иной текст `note` или формат
  `derived_results`), не загрузится, даже если входные поля верны.
  - Возможное смягчение — на усмотрение BUILD: при несовпадении принимать входные поля, отбрасывать
    `derived_results` и показывать предупреждение.
  - Патч K12 этого не делает.
- **P3 — координатору.** Стоит зафиксировать в CORE_SPEC, что такое `evaluated` для `infeasible`.

## Свои расхождения K12

- **P03 раунда 7:** фикстура кладёт выводимые значения в поле `results`, а BUILD v1 разрешает `derived_results`.
  - Ошибка в моей фикстуре, не в BUILD. Раунд 7 закрыт, поэтому фикстуру не правил.
  - В раунде 8 правильное имя проверяет E1 (PASS).
- **N15 раунда 7:** отпечаток v1 без категории. Остаётся advisory, v2 этим не затронут.
