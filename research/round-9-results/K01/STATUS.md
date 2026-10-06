# K01 раунд 9 — STATUS: совместимость и строгий импорт

- Роль K01 (не BUILD), ветка `claude/loving-thompson-nmajdo`. Общий прототип не изменялся.
- **Tested BUILD:** `claude/beautiful-clarke-sbzomj` @ **`d865dd4a124291e10dd0b7bb1d9eada20d34c268`** (byte-exact извлечение по git-объектам; `data.js`/`facts.js` идентичны a5b5e2d).
- Входы: `research/round-9/{snapshots.json,REVIEW.txt,CORE_SPEC.txt,TASK.txt,tasks/K01.txt}` @ `codex/research-import-2026-10-05` `0ab1667`; свои r8 фикстуры `research/round-8-results/K01/fixtures` (@ e717082).

| Этап | Статус |
|---|---|
| 1. r8 fixtures → настоящий plan.js; v1/v2 roundtrip, snapshot, UTF-8/NFC, атомарность; расхождения | **done** |
| 2. JSON Schema + семантические негативные fixtures city-resilience-v1, узкий валидатор | **done** |
| 3. Адаптер к BUILD r9 resilience, отказ до смены состояния, канонизация; CONTRACT_DIFF.txt | in progress |

## Этап 1 — реально выполнено на d865dd4
- `node test_compat.cjs --app-root APP` → **72 passed, 0 failed** (`runs/stage1_compat_d865dd4.txt`): 46 r8-фикстур под контрактом BUILD (через `POLICY_r8_to_build.json`), v2 roundtrip с derived (оба города), подмена derived → `forged_derived`, без derived → принят, v1 через `whatif.js` и `wrong_version` в v2, чужой snapshot, `other_city`, 14 случаев NFC/UTF-8 ID, BOM, ровно 256 KiB с кириллицей / +1 байт, неизменность ctx и входа при отказе.
- `NODE_PATH=$(npm root -g) node browser_atomic.cjs --app-root APP` → **15 passed, 0 failed** (`runs/stage1_browser_d865dd4.txt`): Chromium file://, настоящий `CITY_PLAN_UI.importText`; 10 отказов (forged derived, overlap, bbox, NaN, дубль ключа, >256 KiB, битый UTF-8, чужой snapshot, 17 кандидатов, v1) не меняют план и город; валидный файл Астаны переключает город; ошибок страницы нет.
- Один промежуточный FAIL был ошибкой моего теста (неверная сборка 256 KiB-файла), исправлен; не дефект продукта.
- Расхождения r8↔BUILD с минимальными входами: `DIFF_r8_vs_BUILD.md` (9 пунктов, дефектов продукта нет).

## Этап 2 — реально выполнено (поверх настоящего plan.js d865dd4)
- `resilience_v1.schema.json` — структура envelope; `resilience_contract.js` — узкий модуль (фабрика `(CITY_PLAN, CITY_WHATIF)`), план проверяет **`validatePlanScenario` BUILD**, свой планировщик не пишется.
  Коды: `bad_version/wrong_version`, `derived_not_allowed`, коды PlanError BUILD для плана, `too_many_candidates` (>12), `bad_cases` (0 или >7), `bad_case_id`, `reserved_case_id`, `duplicate_case_id`,
  `bad_label` (пусто/пробелы/>120 code points/Cc/U+2028/2029/непарный суррогат), `bad_exclusions` (пусто или больше записей категории), `duplicate_source_id`, `candidate_id_as_source`, `wrong_category_source`, `unknown_source`.
- `make_resilience_fixtures.cjs` → 49 фикстур (11 valid) обоих городов; source ID — реальные записи среза BUILD, сценарии synthetic; `RESILIENCE_EXPECTED.json`, `RESILIENCE_MANIFEST.json`.
- `node test_resilience_contract.cjs --app-root APP` → **55 passed, 0 failed** (`runs/stage2_resilience_contract_d865dd4.txt`): все фикстуры; schema; экспорт = только вход, roundtrip; канонизация cases/исключений;
  digest не зависит от порядка, меняется от label/исключений/плана, selected_ids — только в scenario digest; base добавляется вычислителем, не файлом; отказ не мутирует вход и ctx.
