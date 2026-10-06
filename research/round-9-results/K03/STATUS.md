# K03 round 9 — «Чувствительность к качеству координат»: STATUS

| Поле | Значение |
|---|---|
| Слот | K03 (`research/round-9/tasks/K03.txt` @ `0ab1667`, ветка codex/research-import-2026-10-05), не BUILD |
| Ветка | `claude/epic-curie-iitc43` (вход r9: `9b39f0f`) |
| Проверенная сборка | `claude/beautiful-clarke-sbzomj` @ **`d865dd4a124291e10dd0b7bb1d9eada20d34c268`**. Дерево `prototypes/city-evidence` = `3e1302a` (проверено, `inputs/BUILD_MANIFEST.json`) |
| Обновлено | 2026-10-06, этапы 1–2 |
| Статус | **этапы 1–2 done**; этап 3 — в работе |

## Этап 1 — r8 geo-fixtures на настоящем plan.js (done)

Прогон шёл через адаптер `plan_adapter.cjs` (Node, без DOM). Адаптер загружает `web/data.js` и `web/evidence.js`, как `tests/plan.cjs` сборки, и вызывает настоящие функции: `makeContext`, `validatePlanScenario`, `precompute`, `evaluatePlan`, `facts.qaOf`. Сам адаптер ничего не вычисляет.

Эталон — независимый Python-оракул K03 r8 (`research/round-8-results/K03/geo_v2_ref.py` @ `9b39f0f`) и ожидания fixtures r8. По ответу сборки ожидания не менялись.

`data.js`/`evidence.js` в d865dd4 побайтно равны данным fixtures r8 (a5b5e2d). Поэтому fixtures подключены без пересоздания.

### Проверки (`runs/stage1_d865dd4.json`): PASS 10, FAIL 0, SKIP 0, NOT_RUN 0

| Проверка | Что сделано |
|---|---|
| S1-build | Хэши файлов сборки; данные = данным fixtures |
| S1-validate | 104 validate-случая r8 на `validatePlanScenario`. Решение «принять/отклонить» совпало у всех. 86 — тот же код, 18 — код по таблице политики (ниже) |
| S1-context | bbox и записи категорий обоих городов. `source_snapshot` plan.js = мой независимый пересчёт по формуле plan.js; контекст заморожен |
| S1-nearest-fixtures | table/after/bind/cand-случаи r8 (этапы 1–3), 132 точки: ближайшая запись (ID, мм), мм до кандидатов, after, delta = оракул |
| S1-real-sources | Контрольная точка в координатах **каждой** из 55 настоящих записей школ и поликлиник обоих городов. До = 0 мм; ближайшая — меньший ID среди записей в тех же координатах; кандидат поверх записи её не вытесняет |
| S1-random | 32 seeded synthetic сценария, 800 строк `evaluatePlan` = оракул |
| S1-ties | 74 ничьи (14 на настоящих записях, 5 наборов): plan.js выбирает меньший ID |
| S1-qa | QA каждой записи категории, как её показывает интерфейс (`facts.qaOf`), = флаги оракула: COLOCATED и размер группы, пары POSSIBLE_DUPLICATE, CATEGORY_DOUBT |
| S1-coincident-not-duplicate | См. отдельный раздел ниже |
| S1-integrity | После всех вызовов `data.js`/`evidence.js` и загруженный объект не изменились |

### Совпадающие координаты ≠ дубликат учреждения (отдельная проверка)

- plan.js хранит каждую запись в общих координатах отдельно: `source_candidates` = числу всех записей категории, слияния нет.
- Пар записей в одних координатах (все категории, оба города) — **58**. Из них только **4** помечены POSSIBLE_DUPLICATE, и только по правилу адреса/имени (`same_address`, `same_group_same_house_number`). Правила «по координатам» нет.
- Пример: Шымкент (69.5958, 42.3167) — 10 записей с разными названиями: 4 поликлиники, 3 школы, колледж, госучреждение, аптека. Ни одна пара из них не помечена дублем.
- Тексты UI:
  - COLOCATED — «координата совпадает… точное место не проверено»;
  - POSSIBLE_DUPLICATE — «возможный дубликат (правило, м)».

  Совпадение координат дубликатом не называется.

### Отрицательный контроль (`runs/negative_controls_s1.json`): 5/5 испорченных копий дают FAIL

Порча делалась только во временной копии сборки.
- ничья → больший ID: FAIL nearest/real-sources/random/ties;
- слияние записей в одних координатах (`makeContext`): FAIL context/coincident;
- кандидат выигрывает ничью у записи: FAIL nearest/real-sources;
- текст COLOCATED «вероятно дубликат»: FAIL coincident;
- исключённые границы bbox: FAIL validate.

### Находки этапа 1 (для BUILD и устойчивости r9)

1. **Ничья скрыта в строке плана (информация, не ошибка расчёта).**
   - `evaluatePlan` отдаёт один `nearest_before` без числа ничьих.
   - На настоящих данных Шымкента 14 записей школ и поликлиник стоят группами в общих координатах (школы 3+2+2, поликлиники 4+3). Пользователь видит одно имя.
   - Для r9 это важно: если условно исключить показанную запись, расстояние не изменится, потому что в тех же координатах остаётся другая запись. Это не ошибка, но без раскрытия ничьей выглядит как сбой.
   - Предложение (этап 3): показывать в UI все ID ничьей / число записей в тех же координатах.
2. **8 записей школ и поликлиник с общими координатами без метки COLOCATED** (порог правила ≥3).
   - Астана: 2 поликлиники совпадают по координатам с больницами.
   - Шымкент: школьные пары «Express toefl / Kasipkoy.kurs» (есть POSSIBLE_DUPLICATE) и «ALEM мектебі / Алем мектеп» (без меток); «Техникалық лицей» — с больницей; поликлиника «ИП Ауелбекова» — с колледжем.
   - Интерфейс плана для них не показывает признак общих координат. Список — `S1-qa.details.shared_without_colocated`.
3. **Различия политики проверки мест** — не дефекты, отказ во всех случаях верный:
   - plan.js не распознаёт перестановку lon/lat и город точки: `outside_bbox` вместо `lon_lat_swapped` / `other_city`;
   - нечисло, NaN и диапазон объединены в `bad_coord`;
   - `bad_points` вместо `too_many_points`;
   - пути ошибки нет: только текст `detail`.

   ID: plan.js принимает Unicode NFC `[\p{L}\p{N}_.-]` до 64 символов (CORE_SPEC r9 — принимать как в BUILD). Мои r8 fixtures из этого не выходят.
4. **Erratum к моему r8 STATUS** (сам отчёт r8 не переписываю). Строка «Астана — пара поликлиник без COLOCATED» неверна: в Астане нет записей школ или поликлиник в общих координатах внутри категории. Там совпадают поликлиника и больница (2 пары) и 2 госучреждения. В r8 fixtures такого случая нет; ошибка была только в тексте STATUS.

## Этап 2 — построитель случаев явного исключения ID (done)

- `resilience_cases.js` (UMD, без DOM) и независимый оракул `resilience_cases_ref.py`. API и правила — в `CASES_API.md`.
- Три способа создать случай: одна запись, пользовательская группа, QA-группа COLOCATED по явно указанному индексу.
  - Автоматических исключений нет.
  - Для Астаны групп COLOCATED нет: статус `no_qa_group`, группа не создаётся.
  - Если в выбранной QA-группе нет записей категории: `no_records_in_category`.
- `validateCases` проверяет `cases` envelope city-resilience-v1 по CORE_SPEC r9:
  - 1..7 случаев + авто-`base`;
  - ID по правилам BUILD (NFC), `base` зарезервирован;
  - подпись ≤120 code points без управляющих символов;
  - ID исключений: только исходные записи этого города и категории; кандидат, другой город или категория отклоняются типизированной ошибкой; без повторов; не больше числа записей;
  - совпадающие наборы допустимы и показываются (`identical_sets`).
- Envelope без производных полей (`per_case`, `worst_case_ids`, `verified`, `derived_results` → `derived_not_accepted`).
- **Manifest исключаемых записей на базовом срезе** (`exclusionManifest`), для каждого ID:
  - категория, координаты, имя, адрес, provenance (`sources[]`, версия Overture, confidence) и QA;
  - `record_sha256` исходной записи `data.js`;
  - `base_source_snapshot` — формула plan.js, пересчитана независимо;
  - отдельный `exclusion_digest`: от порядка не зависит; объект заморожен.
- `make_stage2.py` → `fixtures/stage2.json`: 211 случаев, ожидания по построению из `data.js`/`evidence.js`. Кейсы Шымкента и Астаны по обеим категориям плюс 9 проверок envelope.

### Проверки (`runs/stage2_d865dd4.json`): PASS 8, FAIL 0, SKIP 0, NOT_RUN 0

JS выполнялся на контексте **настоящего** `plan.js` d865dd4 (`cases_runner.cjs`).

| Проверка | Результат |
|---|---|
| S2-python-oracle | 211/211 |
| S2-js | 211/211 |
| S2-js-python-parity | 0 расхождений |
| S2-digest-invariance | Перестановка случаев и ID digest не меняет; другая подпись или набор меняют; JS = Python |
| S2-no-auto-exclusion | Поведенческая проба: каждая функция без явного выбора не создаёт случай (JS и Python, 4 среза) |
| S2-wording | 25 подписей по умолчанию «Условно…», без «закрытие/кризис/риск/дубликат/прогноз»; примечание = формулировке CORE_SPEC |
| S2-integrity | Файл и объекты `data.js`/`evidence.js` не изменились; `source_snapshot` = пересчёту |

Первый прогон дал FAIL в S2-no-auto-exclusion. Причина была в самом тесте: статический поиск строки `qa.colocated.map` сработал на законном списке групп для показа. Я заменил его поведенческой пробой и повторил прогон. Модуль не менялся.

### Отрицательный контроль (`runs/negative_controls_s2.json`): 7/7 испорченных копий модуля дают FAIL

- ID не сортируются;
- повтор ID молча принимается;
- принимается ID кандидата;
- QA-группа захватывает другие категории;
- длина подписи считается в UTF-16;
- без индекса берётся первая QA-группа (автоисключение);
- digest зависит от порядка.

## Также выполнено

- `research/round-8-results/K03/run_tests.py --app-root <копия d865dd4> --stages 1,2,3` → PASS 21, FAIL 0 (`runs/r8_module_on_d865dd4.json`). Это тест **моего модуля** geo_v2 на данных d865dd4, а не тест продукта.

## Ограничения

- Устойчивости (`resilience.js`, envelope city-resilience-v1) в d865dd4 нет. Её интеграцию я не проверял. Коды ошибок моего модуля — предложение; у BUILD они могут отличаться.
- Контрольные точки, веса, стоимости и кандидаты — synthetic. Записи — Overture из сборки: вторичные данные, на месте не проверены.
- Браузерный UI не запускался: QA проверен через `facts.qaOf`, которую вызывает `plan-ui.js`.
- Окружение: Linux, Python 3.11.15, node v22.22.0.

## Воспроизведение

```bash
git fetch origin claude/beautiful-clarke-sbzomj
python3 research/round-5-results/K03/extract_build.py --sha d865dd4a124291e10dd0b7bb1d9eada20d34c268 --out /tmp/app9
python3 research/round-9-results/K03/make_manifest.py --app-root /tmp/app9 --sha d865dd4a124291e10dd0b7bb1d9eada20d34c268
python3 research/round-9-results/K03/make_stage1_scan.py --app-root /tmp/app9 --target-sha d865dd4a124291e10dd0b7bb1d9eada20d34c268  # уже в fixtures/
python3 research/round-9-results/K03/run_stage1.py --app-root /tmp/app9 --target-sha d865dd4a124291e10dd0b7bb1d9eada20d34c268 --json /tmp/s1.json
python3 research/round-9-results/K03/negative_controls.py --app-root /tmp/app9 --work /tmp/k03neg --stage 1
```

## Воспроизведение этапа 2

```bash
python3 research/round-9-results/K03/make_stage2.py --app-root /tmp/app9 --target-sha d865dd4a124291e10dd0b7bb1d9eada20d34c268  # уже в fixtures/
python3 research/round-9-results/K03/run_stage2.py --app-root /tmp/app9 --target-sha d865dd4a124291e10dd0b7bb1d9eada20d34c268 --json /tmp/s2.json
python3 research/round-9-results/K03/negative_controls.py --app-root /tmp/app9 --work /tmp/k03neg --stage 2
```

## Файлы этапа 2

- `resilience_cases.js`, `resilience_cases_ref.py`, `CASES_API.md`.
- `cases_runner.cjs`, `run_stage2.py`.
- `make_stage2.py` → `fixtures/stage2.json`.
- `runs/stage2_d865dd4.json`, `runs/negative_controls_s2.json`.

## Файлы этапа 1

- `plan_adapter.cjs` — адаптер к настоящему plan.js.
- `r9_common.py` — общие помощники.
- `run_stage1.py` — проверки этапа 1.
- `make_stage1_scan.py` → `fixtures/stage1_scan.json`.
- `negative_controls.py`.
- `make_manifest.py` → `inputs/BUILD_MANIFEST.json`.
- `runs/stage1_d865dd4.json`, `runs/negative_controls_s1.json`, `runs/r8_module_on_d865dd4.json`.
