# K02, раунд 5 (REVIEW). Регрессия JS-объяснений `web/facts.js`

Проверяемая сборка: K04 `claude/beautiful-clarke-sbzomj` @ `0bf27deb8549b325b34a9610402613d745544edb`, `prototypes/city-evidence/`.
- Сборка извлечена побайтно, git blob 57 файлов сверен. Общая папка и файлы сборки не изменялись.
- `web/facts.js` сборки — порт K02 r3 (`24c1750`). Исправлений K02 r4 (`7020637`) в нём нет. Поэтому дефекты r3 перешли в JS. Ниже они проверены **на JS самой сборки**, а не на Python.

## Итог

- **Baseline `0bf27de`: 2 PASS, 9 FAIL из 11.** Все 9 падений — ожидаемые падения baseline (`expected_baseline_failures` в `baseline/*.json`).
- **Patch-предложение** `patches/facts_catalog_digest.patch` проверено на копии: 11 из 11 PASS. Собственные `conformance.cjs` и `smoke.cjs` сборки тоже проходят.
- **Сборка НЕ исправлена.** Patch только предложен. Статус FIXED можно ставить лишь после того, как сборщик применит patch и тест повторится на новом SHA.

## 1. Тест (`tests/facts_regression.cjs`)

Без зависимостей, Node ≥ 18. Цель задаётся явно:

```bash
node research/round-5-results/K02/tests/facts_regression.cjs --app-root <извлечённая prototypes/city-evidence> [--json out.json]
node research/round-5-results/K02/tests/facts_regression.cjs --url http://127.0.0.1:8765/ [--json out.json]   # serve.py сборки
```

- Читает `web/facts.js`, `web/data.js`, `web/evidence.js` с диска или по HTTP.
- Входы меняет только в клонах в памяти.
- Код выхода: 0 — всё PASS, 1 — есть FAIL, 2 — сборка не загрузилась.

## 2. Результаты

| Тест | Что проверяет | Baseline `0bf27de` | `0bf27de` + patch (копия) |
|---|---|---|---|
| T1_value_change | тот же город и срез, значение `places.school` 15→16, план по старому каталогу | **FAIL**: accepted, срез тот же | PASS: `stale_catalog` |
| T2_unit_change | единица `segments.foot_unknown` → km | **FAIL**: accepted (единицы в каталоге нет) | PASS |
| T3_coverage_change | `coverage.complete` true→false | **FAIL**: accepted (охвата в каталоге нет) | PASS |
| T4_digest_distinguishes | старый срез и изменённый каталог различимы; одинаковые совпадают | **FAIL**: нет API `catalogDigest` | PASS |
| T5_duplicate_across_sections | один ID в `summary` и `risks` | **FAIL**: accepted | PASS: `duplicate_id` |
| T6_null_vs_zero | `capacity.school_places` = null → только в `data_gaps`, «нет данных» / «дерек жоқ»; `district_status.ambiguous` = 0 → «0» | PASS | PASS |
| T7_city_substitution_observations | наблюдения `kz.astana` под ключом `shymkent` | **FAIL**: принято, числа Астаны показаны как шымкентские | PASS: `foreign_city` при `buildCatalog` |
| T8_city_switch_stale_plan | план по Астане против каталога Шымкента | PASS: `foreign_city` | PASS |
| T9_nonfinite_nan / _inf | NaN / Infinity в наблюдении | **FAIL**: `buildCatalog` принял, `render` падает с обычным Error | PASS: `non_finite` при `buildCatalog` |
| T10_incomplete_coverage_visible | счётчики квадрата (`coverage.complete=false`) помечены в тексте | **FAIL**: «Школа: записей в квадрате: 15 (наблюдение)» | PASS: «… (наблюдение, неполный охват)» |

- Режимы `--url` (через `serve.py` сборки, порт 8799) и `--app-root` на baseline дали одинаковые результаты.
- T6 и T8 проходят и на baseline. Здесь сборка корректна: null не превращается в 0, план для чужого города отклоняется.

Наблюдение по данным сборки: все счётчики `places.*` имеют `coverage.complete=false` (квадрат ~2×2 км). Каталог сборки этот признак теряет. В интерфейсе квадрат упомянут в подписи, но строка объяснения его не несёт.

## 3. Ожидаемое изменение API (patch-предложение)

**`catalogDigest(catalog) → string` (новый экспорт).**
- 16 hex: FNV-1a 32 ×2 по отсортированным `[id, value, kind, unit, coverage_complete]`.
- Это отпечаток для обнаружения устаревшего плана, а не криптографическая защита.

**План:** `{sections, catalog_digest, comment?}`.
- `StubSelector.select(view, {digest})` кладёт digest.
- `explain()` и `renderExplanation()` передают digest каталога, по которому строился план.
- `validatePlan` сверяет digest **последним**, поэтому прежние коды (`unknown_id`, `foreign_city`, `stale_scenario`, `not_an_id`, `null_as_fact`, `value_in_gaps`) сохраняются. При несовпадении — `stale_catalog`.
- **Несовместимость:** внешний план без `catalog_digest` теперь отклоняется. Внутренние вызовы сборки обновлены в patch.

**Остальные изменения:**
- повтор ID между секциями → `duplicate_id`;
- `buildCatalog` проверяет `o.city_id === "kz." + city`, иначе `foreign_city`;
- значение — конечное число или null, иначе `PlanError("non_finite")`;
- факт получает `unit` и `coverage_complete`; они входят в digest и `facts_used`;
- `render(..., opts)`: при `coverage_complete === false` добавляется «неполный охват» / «толық емес қамту»;
- `opts.markCoverage === false` отключает пометку;
- `explain(..., selector, opts)` прокидывает `opts`.

**`tests/conformance.cjs`.** Сравнение текста с Python K02 r3 вызывается с `{markCoverage: false}`. У эталона r3 пометки нет, а остальной текст по-прежнему сравнивается побайтно. Если нужен эталон с пометкой, его надо перегенерировать от исправленного Python K02 r4 (`7020637`). Это работа сборщика.

## 4. Проверки (реально выполнены, Node v22.22.0)

- Baseline `0bf27de`:
  - `node tests/conformance.cjs` → all passed;
  - `node tests/smoke.cjs` → PASS (без ошибок консоли и сетевых запросов).
- `facts_regression.cjs --app-root` baseline → 9 FAILED of 11 (`baseline/app_root_0bf27de.json`).
- `facts_regression.cjs --url http://127.0.0.1:8799/` baseline → те же 9 FAIL (`baseline/url_0bf27de.json`).
- Копия `0bf27de` + patch:
  - `node --check web/facts.js` → ok;
  - `conformance.cjs` → all passed;
  - `smoke.cjs` → exit 0;
  - `facts_regression.cjs` → all 11 passed (`baseline/proposal_check_0bf27de_plus_patch.json`, sha256 исправленного `facts.js` `89d77520…`).
- `git apply --check` и `git apply` patch к чистой копии `0bf27de` → побайтно равно проверенной копии (`cmp`).
- **Не запускалось:** браузерная проверка сценария «нажать “Объяснить” → сменить фильтр → получить `stale_catalog`» вручную. `smoke.cjs` сборки покрывает её только косвенно.

## 5. Граница

- digest ловит переиспользование плана после изменения каталога. Он **не** защищает от злонамеренной подмены: FNV не криптографический, а данные лежат в том же браузере.
- Правильность самих наблюдений K05 и привязки K03 этот тест не проверяет.
- Подписи kk — черновик.
- `StubSelector` — детерминированная заглушка, не LLM. Качество выбора LLM не проверялось.

## 6. Для сборщика (повтор на исправленной версии)

```bash
git apply research/round-5-results/K02/patches/facts_catalog_digest.patch   # в ветке сборки
node prototypes/city-evidence/tests/conformance.cjs
node research/round-5-results/K02/tests/facts_regression.cjs --app-root prototypes/city-evidence --json facts_regression_<newsha>.json
```

Ожидание после исправления: 11 из 11 PASS. На baseline ожидаемо падают T1–T5, T7, T9 (×2) и T10.
