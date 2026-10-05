# K01 раунд 8 — контракт `city-plan-v2`: валидатор, импорт/экспорт, digest

Изолированный модуль для BUILD по `research/round-8/CORE_SPEC.txt`. Общий прототип не изменён; интеграции в BUILD ещё нет.
Оптимизатор (evaluatePlan/optimizePlans) — **не часть этого модуля**: здесь контракт, состояние и воспроизводимость.

## Файлы
| Файл | Что |
|---|---|
| `planv2.js` | UMD-модуль без DOM (`window.CITY_PLAN_V2` / `module.exports`) |
| `plan_v2.schema.json` | JSON Schema 2020-12 структурной части |
| `planv2_ref.py` | независимый Python-оракул: интерпретирует schema-файл, семантика и canonical JSON написаны отдельно |
| `planv2_cli.cjs` | CLI: `context`, `validate`, `digest`, `export`, `migrate` |
| `load_app.cjs` | headless загрузка `web/data.js` + `web/facts.js` прототипа |
| `make_fixtures.py`, `make_v1_fixtures.cjs` | детерминированные генераторы фикстур |
| `fixtures/real/context_<city>.json` | контекст среза из реальных данных прототипа (provenance: build SHA, sha256 data.js и places_social) |
| `fixtures/synthetic/*.json` | 46 **synthetic** сценариев (точки, веса, стоимости, бюджеты выдуманы; не городская статистика) |
| `fixtures/v1/*.json` | v1-сценарии, экспортированные `whatif.js` BUILD |
| `fixtures/EXPECTED.json`, `fixtures/MANIFEST.json` | ожидаемые вердикты; sha256/байты всех фикстур |
| `test_planv2.cjs`, `test_state.cjs`, `test_digest.cjs`, `test_planv2_ref.py`, `run_all.sh` | тесты |

## API (`planv2.js`)
- `contextFromData(data, city, F)` → `{city_id, bbox, source_snapshot, sha256hex, release}`; `F` = `CITY_FACTS` прототипа.
  `source_snapshot = "sha256:" + sha256hex(JSON.stringify(["city-plan-v2", city, release, places_social_sha256, F.placesDigest(data, city), "haversine-mm-v1"]))` — та же схема, что у v1 `whatif.js sourceSnapshot`, но со своей версией и metric_version.
- `validatePlanScenario(input, context)` → чистая копия или `PlanV2Error{code, detail}`; `derived_results` отбрасывается.
- `importPlan(textOrUint8Array, context)` → `{scenario, notes}`; ≤256 KiB (UTF-8 байты), BOM пропускается, без NaN/Infinity/1e999/дубликатов ключей (в т.ч. через `\u`-escape).
- `exportPlan(scenario, context, derive?)` → текст; поля входа первыми, `derived_results {kind:"derived", metric_version, problem_digest, value}` только если передан `derive` (например, результат evaluatePlan BUILD).
- `problemDigest(sc, ctx)` → `pd1:<sha256>`; `scenarioDigest(sc, ctx)` → `sd1:<sha256>` (= problem + отсортированные `selected_ids`).
  Канон: `[schema, metric_version, source_snapshot, city_id, category, points sorted by id [id,lon,lat,weight], candidates sorted by id [id,lon,lat,category,kind,cost], budget, max_selected, coverage_radius_m, sorted required, sorted excluded]` через `JSON.stringify`.
- `migrateV1(v1Validated, {budget, cost, max_selected?, coverage_radius_m?}, ctx)` — без явных budget/cost → `cost_required`; веса = 1.
- `PlanStore(ctx)`: `importText`, `edit(mutator)`, `switchContext`, `switchCategory`, `startOptimization()` → `{request_id, problem_digest}`, `receive(answer)` (старый/чужой ответ игнорируется), `applyProposal(ids)`. Отказ не меняет `active`.

## Порядок проверок (одинаковый первый код в JS и Python для одиночных дефектов)
too_large → bad_encoding → bad_json / duplicate_key / non_finite → bad_shape → unknown_field → missing_field → bad_version → bad_city →
foreign_city → foreign_snapshot → bad_category → control_points (bad_points, unknown_field/missing_field, bad_id, duplicate_id, bad_coord, outside_bbox, bad_weight) →
candidates (bad_candidates, …, bad_category, bad_kind, bad_cost) → bad_budget → bad_max_selected → bad_radius → required/excluded (bad_id, duplicate_id, unknown_ref) → constraint_conflict → selected_ids.
Python проверяет сначала всю структуру по schema, потом семантику; при нескольких дефектах первый код может отличаться — фикстуры однодефектные.

## Интеграция в BUILD (предложение, не выполнено)
1. Скопировать `planv2.js` байтами в `prototypes/city-evidence/web/` (+ запись sha256 в манифест входов), подключить после `facts.js`.
2. `const ctx = CITY_PLAN_V2.contextFromData(window.CITY_EVIDENCE, STATE.city, CITY_FACTS)`; хранить сценарий в `new CITY_PLAN_V2.PlanStore(ctx)`;
   при смене города/категории вызывать `switchContext/switchCategory`.
3. Worker: передавать `startOptimization()` вместе с задачей; ответ принимать только через `store.receive(answer)`; кнопка «Применить» → `applyProposal`.
4. Экспорт: `exportPlan(store.active, ctx, (sc) => evaluatePlan(...))`; импорт: `store.importText(fileText)`; сообщения выводить через `textContent`.
5. Проверка: `bash research/round-8-results/K01/run_all.sh <новый BUILD SHA>`; после копирования модуля добавить `node test_planv2.cjs --app-root <app>` в `check_all`.

## Ограничения
- Это контракт, а не оптимизатор: before/after, мм-метрика, Парето и перебор реализуются другим модулем; здесь только `metric_version` в digest.
- Canonical-форма опирается на `JSON.stringify` чисел; Python-оракул отказывается от экспоненциальной записи (координаты ограничены bbox, целые поля — целые).
- Целочисленность проверяется по значению (`1.0` == `1`), как это неизбежно в JS.
- ID только ASCII `^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$`: кириллица/zero-width/суррогаты отклоняются (защита от подмены и URL), это сознательное сужение спецификации «≤64 символа».
- Контрольные точки — выбранные пользователем места, веса — приоритеты, стоимости — условные единицы, не тенге и не смета.
