# K03 round 9 — «Чувствительность к качеству координат»: STATUS

| Поле | Значение |
|---|---|
| Слот | K03 (`research/round-9/tasks/K03.txt` @ `0ab1667`, ветка codex/research-import-2026-10-05), не BUILD |
| Ветка | `claude/epic-curie-iitc43` (вход r9: `9b39f0f`) |
| Закреплённая сборка (snapshots r9) | `d865dd4a124291e10dd0b7bb1d9eada20d34c268`; дерево прототипа = `3e1302a` (проверено) |
| Новые сборки BUILD, проверенные явно | `e1cbc3fa84518a84698c03d014dc153f71338d54` (r9 stage 3: `web/resilience.js`); `d18847f9e7c18fcfae3349c0b223b023d359a838` (r9 stage 4, последняя на 2026-10-06; движок и данные = e1cbc3f, изменены только UI и инструменты) |
| Обновлено | 2026-10-06, этапы 1–3 |
| Статус | **этапы 1–3 done** |

## Итог прогонов (финальные скрипты; `runs/stage{1,2,3}_<sha>.json`)

| Сборка | Этап 1 | Этап 2 | Этап 3 |
|---|---|---|---|
| d865dd4 (закреплённая) | PASS 10 | PASS 8 | PASS 8; устойчивость **NOT_RUN** (в сборке нет `resilience.js`) |
| e1cbc3f | PASS 10 | PASS 8 | PASS 16, INFO 1 |
| d18847f (последняя) | PASS 10 | PASS 8 | PASS 16, INFO 1 |
| d18847f + патч K03 | — | — | PASS 16, INFO 1; неоднозначностей спецификации 0 вместо 4 |

FAIL 0, SKIP 0 во всех прогонах.

Отрицательный контроль — каждая испорченная копия дала FAIL в ожидаемых проверках:
- этап 1 — 5/5;
- этап 2 — 7/7 (копии модуля);
- этап 3 — 5/5 (копии `resilience.js`/`plan.js` e1cbc3f).

Тесты сборки на d18847f без патча и с патчем K03 одинаковы: `resilience.cjs` 112/112, `plan.cjs` 164/164, браузерный `resilience_smoke.cjs` 40/40.

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

## Этап 3 — сценарная фильтрация, другой город, кейсы Шымкента и Астаны (done)

### Кейсы

`make_stage3.py` → `fixtures/stage3.json` и `cases/<город>_<категория>.envelope.json` + `.manifest.json`, 4 среза.
- Каждый envelope — полный city-resilience-v1: план city-plan-v2 (точки и кандидаты synthetic) и до 7 явных случаев на **настоящих** source ID.
- Каждый manifest — копии исключаемых записей с provenance на базовом срезе.

| Срез | Случаи | Группа COLOCATED |
|---|---|---|
| Шымкент, школы | одна изолированная; по одной из двух пар в общих координатах; QA-группа COLOCATED (3 школы из 10 записей); 3 у центра; тот же набор повторно; все 15 | есть |
| Шымкент, поликлиники | то же: группы 3 и 4 в общих координатах, QA-группа — 4 из 10 | есть |
| Астана, школы / поликлиники | одна изолированная; 3 у центра; повтор; все | **нет: `no_qa_group`, группа не создана** |

### Ожидания

- Baseline каждого случая с нуля по оставшимся записям: `resilience_cases_ref.case_baseline`.
- After ручного плана.
- Полный перебор nominal/robust: `robust_ref.py`, отдельный от сборки.
- 14 утверждений по построению.

Результат перебора: в Астане (школы) устойчивый план отличается от обычного, цена устойчивости +23,4 м. В трёх других срезах планы совпадают, цена 0; преимущество не придумывается.

### Проверки (`runs/stage3_<sha>.json`)

**Часть A — `plan.js` любой сборки (d865dd4, e1cbc3f, d18847f): PASS 8**

| Проверка | Что подтверждено |
|---|---|
| S3-plan-case-baseline | 26 случаев с base, 256 строк: baseline через `plan.precompute` на отфильтрованной копии = оракулу; записей в случае N − k; 49 ничьих |
| S3-plan-after-manual | after/delta ручного плана в каждом случае = оракулу |
| S3-construction | Исключение одной записи из общих координат оставляет соседнюю в тех же координатах (0 мм) — совпадение координат не дубликат. QA-группа или одиночная запись: ближайшая дальше. Все записи исключены → «до» неизвестно (`null`), а не 0 |
| S3-module-view | `caseView` модуля K03: тот же `source_snapshot`, исключены ровно ID случая, контекст не изменён |
| S3-other-city | План Шымкента в контексте Астаны → `other_city`; чужой snapshot → `foreign_snapshot`; ID записи другого города → `other_city_source` |
| S3-no-qa-group | Астана: групп COLOCATED в `evidence.js` нет — статус `no_qa_group`, случай не создан |
| S3-integrity | `data.js`/`evidence.js` (файл и объект) и `source_snapshot` не изменились |

**Часть B — `web/resilience.js` (e1cbc3f и d18847f): PASS 8, INFO 1. На d865dd4 — NOT_RUN**

| Проверка | Что подтверждено |
|---|---|
| S3-build-envelopes | Мои 4 файла импортируются сборкой; её чистые случаи = случаям модуля K03 |
| S3-build-case-baseline | `evaluateResilience`, 512 строк: before по оставшимся записям каждого случая; after/delta, метрики случаев, W и худшие случаи = оракулу |
| S3-build-optimize | `optimizeResilience` = моему полному перебору: планы, W, худшие случаи, среднее base, цена, `same_plan`, число допустимых наборов |
| S3-build-invariants | После validate/evaluate/optimize/export/import исходники и контексты не изменились; `source_snapshot` результата = исходному; экспорт — только вход |
| S3-build-other-city | Envelope в чужом городе → `other_city`; ID записи другого города → `unknown_source` |
| S3-build-duplicates-order | Повтор набора показан и результат не меняет; порядок случаев и ID не влияет на результаты и digest |
| S3-build-validate-map | 96 списков случаев из fixtures этапа 2 в настоящем плане: решение = ожиданию K03, коды по таблице. 4 расхождения из-за неоднозначности спецификации (одиночный суррогат) показаны отдельно |
| S3-build-envelope-rules | Производные и лишние поля отклонены; 13 кандидатов → `too_many_candidates` до проверки плана; `base` в файле → `reserved_id` |
| S3-build-policy (INFO) | Различия политики подписи — `patches/README.md` |

### Предложения к BUILD (`patches/`, не применены)

Патч против d18847f проверен на копии. Тесты сборки до и после одинаковы: 112/112, 164/164, браузер 40/40.
- **P1** — подсказка «в тех же координатах ещё N» в таблице записей случая. `ui_same_coords_check.cjs`: на d18847f FAIL на Шымкенте (пробел), с патчем 6/6.
- **P2** — `\p{Cs}` в `CTRL`: одиночный суррогат в подписи превращался в U+FFFD в HTML-отчёте.

### Честные примечания по ходу

- Мутант этапа 3 «записи `hospital` в baseline» сначала не был пойман. Причина: `makeContext` и так оставляет только школы и поликлиники, то есть мутант эквивалентен исходному коду, а не тест слаб. Заменён на реальный дефект — поликлиники в baseline школ; пойман.
- Прогоны этапов 1–2 на e1cbc3f и d18847f повторены финальными скриптами. Адаптер `plan_adapter.cjs` после этапа 1 получил только новую операцию `validate_raw`.

## Также выполнено

- `research/round-8-results/K03/run_tests.py --app-root <копия d865dd4> --stages 1,2,3` → PASS 21, FAIL 0 (`runs/r8_module_on_d865dd4.json`). Это тест **моего модуля** geo_v2 на данных d865dd4, а не тест продукта.

## Ограничения

- В закреплённой d865dd4 устойчивости нет — там эта часть NOT_RUN. Интеграция проверена на явно записанных новых SHA e1cbc3f и d18847f.
- Модуль K03 `resilience_cases.js` в сборку не встроен. Мои коды ошибок отличаются от кодов сборки названиями (таблица `CODE_MAP` в `run_stage3.py`), решения совпадают.
- Браузер — Chromium через Playwright на Linux (file://). Windows и другие браузеры — NOT_RUN.
- Контрольные точки, веса, стоимости и кандидаты — synthetic. Записи — Overture из сборки: вторичные данные, на месте не проверены.
- Браузерный UI не запускался: QA проверен через `facts.qaOf`, которую вызывает `plan-ui.js`.
- Окружение: Linux, Python 3.11.15, node v22.22.0.

## Воспроизведение

```bash
git fetch origin claude/beautiful-clarke-sbzomj
python3 research/round-5-results/K03/extract_build.py --sha d865dd4a124291e10dd0b7bb1d9eada20d34c268 --out /tmp/app9
python3 research/round-9-results/K03/make_manifest.py --app-root /tmp/app9 --sha d865dd4a124291e10dd0b7bb1d9eada20d34c268   # → inputs/BUILD_MANIFEST_d865dd4.json
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

## Воспроизведение этапа 3

```bash
git fetch origin claude/beautiful-clarke-sbzomj
python3 research/round-5-results/K03/extract_build.py --sha d18847f9e7c18fcfae3349c0b223b023d359a838 --out /tmp/app9c
python3 research/round-9-results/K03/make_stage3.py --app-root /tmp/app9 --target-sha d865dd4a124291e10dd0b7bb1d9eada20d34c268   # уже в fixtures/ и cases/
python3 research/round-9-results/K03/run_stage3.py --app-root /tmp/app9  --target-sha d865dd4a124291e10dd0b7bb1d9eada20d34c268 --json /tmp/s3a.json  # часть B: NOT_RUN
python3 research/round-9-results/K03/run_stage3.py --app-root /tmp/app9c --target-sha d18847f9e7c18fcfae3349c0b223b023d359a838 --json /tmp/s3c.json
python3 research/round-9-results/K03/negative_controls.py --app-root /tmp/app9b --work /tmp/k03neg --stage 3 --target-sha e1cbc3fa84518a84698c03d014dc153f71338d54
NODE_PATH="$(npm root -g)" node research/round-9-results/K03/ui_same_coords_check.cjs /tmp/app9c /tmp/ui.json   # FAIL до патча P1
```

## Файлы этапа 3

- `make_stage3.py` → `fixtures/stage3.json`, `cases/*.envelope.json`, `cases/*.manifest.json`.
- `robust_ref.py`, `run_stage3.py`, `resilience_adapter.cjs`, `ui_same_coords_check.cjs`.
- `patches/build_d18847f_k03_same_coords_label.patch`, `patches/README.md`.
- `inputs/BUILD_MANIFEST_{d865dd4,e1cbc3f,d18847f}.json`.
- `runs/stage{1,2,3}_{d865dd4,e1cbc3f,d18847f}.json`, `runs/stage3_d18847f_k03patch.json`, `runs/negative_controls_s3.json`, `runs/ui_same_coords_d18847f*.json`, `runs/build_tests_d18847f_vs_k03patch.json`.

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
- `make_manifest.py` → `inputs/BUILD_MANIFEST_<sha>.json`.
- `runs/stage1_d865dd4.json`, `runs/negative_controls_s1.json`, `runs/r8_module_on_d865dd4.json`.
