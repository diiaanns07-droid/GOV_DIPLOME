# K03 r9 — построитель случаев исключения (`resilience_cases.js`, оракул `resilience_cases_ref.py`)

Модуль — небольшое дополнение к `web/plan.js` сборки, не второй движок. Он готовит вход `cases` для envelope `city-resilience-v1` (CORE_SPEC r9) и вычислительное представление случая. Ни устойчивый план, ни метрики случаев он не считает.

- Браузер: `window.CITY_RESILIENCE_CASES`, после `facts.js` и `plan.js`.
- Node: `require('./resilience_cases.js')`.
- Ошибки — `CaseError{code, path, detail}`. Тексты выводить только как текст.

## Принципы

- **Только явный выбор.** Нет функции «исключить все записи с QA». QA-группу пользователь указывает индексом.
- **QA не доказывает ошибку.** Метка показывается, но запись не исключается автоматически.
- **Исходники неизменны.**
  - `data.js`, `evidence.js` и контекст `plan.js` не меняются.
  - Случай — это список ID; вычисление идёт на копии списка мест (`caseView`) с **тем же** `source_snapshot`.
- **Формулировки.** Подписи по умолчанию начинаются с «Условно без …». Обязательное примечание: `NOTE_RU = "Условно исключаем из расчёта; это не подтверждение закрытия. Пустые исходные данные не означают отсутствие услуги."`

## Функции

| Функция | Что делает |
|---|---|
| `sourceCatalog(data, evidence, ctx, category, F)` | Записи категории для выбора, отсортированы по ID; результат заморожен (подробности ниже) |
| `sourceIndex(data)` | ID → `[{city, group}]` всех городов; нужен для кода ошибки «другой город/категория» |
| `singleCase(cat, sourceId, {id, label?, index, candidateIds?})` | Одна запись |
| `groupCase(cat, sourceIds, {...})` | Пользовательская группа. Повтор ID — ошибка, без молчаливого удаления |
| `colocatedGroups(evidence, cat)` | Группы COLOCATED среза — только для показа (подробности ниже). Ничего не создаёт |
| `colocatedCase(evidence, cat, index, opts)` | Случай из выбранной пользователем группы, статусы ниже |
| `validateCases(cat, cases, {index, candidateIds})` | Проверка списка случаев, результат ниже |
| `checkEnvelopeShape(obj)` / `makeEnvelope(plan, cases)` | Форма envelope `{schema_version, plan, cases}`, правила ниже |
| `caseView(ctx, disabledIds)` | Вычислительное представление случая, ниже |
| `exclusionDigest(cat, cases, F)` | Отдельный digest исключений, ниже |
| `exclusionManifest(cat, validated, F, build)` | Неизменяемый sidecar для отчёта, ниже |
| `nextCaseId`, `defaultLabel`, `canon`, `isId` | Вспомогательные |

### `sourceCatalog`

Поля каждой записи:
- `id`, `category`, `name`, `address`, `lon`, `lat`;
- `coord_decimals` (derived: число знаков после запятой);
- `provenance` — overture_category/version, confidence, operating_status, `sources[]`;
- `record_sha256` — sha256 канонического JSON исходной записи `data.js`;
- `position_status: source_reported_unverified`;
- `qa`: `colocated`, `possible_duplicates`, `category_doubt`;
- `same_coordinates`: `in_category`, `other_categories`.

### `colocatedGroups`

Для каждой группы: `{index, lon, lat, size, ids_in_category, ids_other_categories}`. Если групп нет, список пуст — группа не придумывается.

### `colocatedCase`

Исключаются только записи выбранной категории из этой группы. Записи других категорий и соседи вне группы (например, в 1,11 м) не добавляются.

Статусы:
- `ok`;
- `no_qa_group` — Астана;
- `no_records_in_category`;
- `qa_unavailable`.

### `validateCases`

Результат: `{cases, with_base, identical_sets}`.
- ID исключений отсортированы.
- `base` с пустым исключением добавляется в `with_base` и не принимается из файла.
- `identical_sets` — случаи с одинаковым набором. Это допустимо; совпадение показывается.

### `checkEnvelopeShape` / `makeEnvelope`

Envelope содержит только `{schema_version, plan, cases}`.
- Производные поля → `derived_not_accepted`: `per_case`, `worst_case_ids`, `verified`, `derived_results` в plan и т. д.
- Любое другое поле → `unknown_field`.
- Сам `plan` проверяет `CITY_PLAN.validatePlanScenario` сборки.

### `caseView`

Возвращает `{...ctx, places: без исключённых}`, заморожен. `source_snapshot` прежний. ID вне контекста → `unknown_source_id`.

### `exclusionDigest`

`sha256` от `[k03-cases-v1, city, category, source_snapshot, [[case id, label, sorted ids]] по ID]`. От порядка случаев и ID не зависит.

### `exclusionManifest`

`{schema: k03-exclusion-manifest-v1, note, base_source_snapshot, release, exclusion_digest, cases (+identical_to), records{ID: запись каталога}, build}`.
- Объект заморожен.
- В envelope не входит и при импорте не принимается.

## Проверка списка случаев (CORE_SPEC r9)

Порядок проверок и коды ошибок:

1. `cases` — массив (`bad_shape`) из 1..7 элементов (`no_cases` / `too_many_cases`). Вместе с `base` — максимум 8.
2. Каждый случай — объект ровно с полями `{id, label, disabled_source_ids}`: иначе `bad_shape`, `unknown_field`, `missing_field`.
3. `id`:
   - правило ID сборки: Unicode NFC, `[\p{L}\p{N}_.-]`, 1..64 code points (`bad_case_id`);
   - `"base"` зарезервирован (`reserved_case_id`);
   - уникален (`duplicate_case_id`).
4. `label` — непустая строка до 120 code points, без управляющих символов и одиночных суррогатов (`bad_label`).
5. `disabled_source_ids` — массив (`bad_shape`):
   - не пуст (`empty_exclusion`);
   - длина не больше числа записей категории — проверяется **до** разбора ID (`too_many_exclusions`).
6. Каждый ID исключения:
   - строка-ID (`bad_source_id`; `source:<id>` тоже отклоняется);
   - запись этой категории; иначе `other_category_source`, `other_city_source`, `candidate_not_source` (ID кандидата не принимается вместо исходной записи) или `unknown_source_id`;
   - без повторов (`duplicate_source_id`).

Если у кандидата тот же ID, что у исходной записи, допустимо: `disabled_source_ids` — пространство source, исключается именно запись.

## Подключение в BUILD (предложение; прототип меняет только BUILD)

1. Подключить `resilience_cases.js` после `plan.js`:
   ```js
   const RC = CITY_RESILIENCE_CASES;
   const cat = RC.sourceCatalog(CITY_EVIDENCE, CITY_OBS, ctx, category, CITY_FACTS);
   ```
2. Панель выбора: таблица `cat.records` (имя, ID, QA, источник, «в тех же координатах ещё N»), явные флажки. Кнопки:
   - «Создать случай» — `singleCase` / `groupCase`;
   - «Случай из QA-группы…» — `colocatedGroups` + выбор + `colocatedCase`.
3. Перед вычислением: `validateCases(cat, envelope.cases, {index: RC.sourceIndex(CITY_EVIDENCE), candidateIds: plan.candidates.map(c => c.id)})`.
4. Baseline случая: `CITY_PLAN.precompute(RC.caseView(ctx, case.disabled_source_ids), scenario)`. Это тот же движок v2 на отфильтрованной копии; `source_snapshot` сценария совпадает. Проверено на этапе 3.
5. В HTML-отчёт добавить `exclusionManifest(...)`: перечень исключений с provenance и `record_sha256` на базовом срезе.

## Проверка интегрированной копии

```bash
python3 research/round-9-results/K03/run_stage2.py --app-root <копия SHA> --target-sha <SHA> --js <копия>/web/resilience_cases.js
```

Если `data.js`/`evidence.js` другие, результат — TEST_INCOMPATIBLE. Тогда пересоздать fixtures: `make_stage2.py --app-root <копия> --target-sha <SHA>`.
