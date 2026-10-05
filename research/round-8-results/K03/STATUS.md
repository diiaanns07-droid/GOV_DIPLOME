# K03 round 8 — «Геометрия и корректность входных мест»: STATUS

| Поле | Значение |
|---|---|
| Слот | K03 (`research/round-8/tasks/K03.txt` @ `c3f6c00`), не BUILD |
| Ветка | `claude/epic-curie-iitc43` |
| База (проверенная) | `claude/beautiful-clarke-sbzomj` @ **`a5b5e2ddbe087c4eab8e947748cdf69dbae84a0d`**. Код = `4e93f30` (`git diff` по прототипу пуст, проверено мной) |
| Обновлено | 2026-10-05, этапы 1–3 |
| Статус | **этапы 1–3 done** (финальный пакет). В прототип **не интегрировано**: интеграцию city-plan-v2 в BUILD я не проверял |

## Этап 1 — геоадаптер v2 (done)

- `geo_v2.js` — модуль для браузера и node без DOM; `geo_v2_ref.py` — независимый Python-оракул. API — `API.md`.
  - Контекст среза: bbox, `edges_inclusive`, `source_snapshot` v2, записи категории с provenance и QA.
  - Проверка мест: 1..25 контрольных точек, 0..16 кандидатов, `kind=hypothetical`, вес и стоимость, ID ≤ 64, координаты и bbox; район не требуется.
  - Таблица расстояний в мм `haversine-mm-v1` и устойчивый ключ ничьей.
- `make_fixtures.py` → `fixtures/stage1.json`: 76 случаев на обоих городах из данных a5b5e2d.
  - 4 контекста (город × категория).
  - Максимум 25/16 с таблицей и `nearestAfter`.
  - 26/17/0 мест, пустое состояние UI, углы bbox, 1e-9° снаружи, перестановка, другой город, NaN.
  - Кандидат на границе районов (K03 r7: район `ambiguous`) принимается; кандидат с ID исходной записи и кандидат в её координатах остаются `hypothetical`.
  - 20 ошибок полей: ID, вес, стоимость, kind, категория, лишние поля, строка, диапазон.
  - Места — synthetic (сетка внутри bbox), не данные города.
- `run_tests.py` + `node_runner.cjs` — прогон JS и Python на одних fixtures с полной сверкой результатов.

## Реально выполненные проверки

`python3 research/round-8-results/K03/run_tests.py --app-root <копия a5b5e2d> --stages 1` → **PASS 4, FAIL 0, SKIP 0** (`runs/stage1_a5b5e2d.json`):
- fixtures построены на этих `data.js` и `evidence.js` (sha256 совпадают);
- Python-оракул — 76/76;
- JS (node v22.22.0) — 76/76;
- паритет JS/Python по полному результату — 0 расхождений.

Первый прогон паритета нашёл лишнее поле `id` в ответе JS `nearestAfter`, расходившееся с API. Исправлено, прогон повторён.

## Этап 2 — независимая проверка геометрии (done)

- `make_stage2.py` → `fixtures/stage2.json`: 59 случаев на обоих городах и обеих категориях, ожидания заданы по построению:
  - каждая сторона bbox: середина принята, 1e-9° снаружи — отказ;
  - перестановка lon/lat у контрольной точки;
  - точка в координатах записи → 0 мм (честный 0);
  - точка в общих координатах нескольких записей → ничья 0 мм, меньший ID, все ключи в `tied_keys` (записи не сливаются);
  - кандидат поверх записи и зеркальная ничья — побеждает source;
  - два кандидата в одной точке — меньший ID;
  - почти-ничья < 1 мм: кандидат дальше на доли мм, но в мм равен → ничья по ID;
  - округление мм у границ k+0,5 мм ±3 ulp.
- `stage_checks.py` — независимые проверки (`--js` проверяет любую копию модуля):
  - **геодезия:** 1375 пар; гаверсинус R=6371008.8 отличается от WGS84 (pyproj) не более чем на **0,315 %**; ближайшая запись по сфере и эллипсоиду различается у 1 из 50 точек — это свойство метрики;
  - **симметрия:** d(a,b)=d(b,a) и мм JS = Python на 1080 парах;
  - **округление:** 25 590 значений у границ полумиллиметра — `floor(x+0.5)` = `Math.round` = `js_round`, 0 расхождений. Единственное расходящееся значение x = 0.49999999999999994 не получается из d·1000 (проверено поиском `nextafter`);
  - **независимость от порядка:** обратный порядок мест в `data.js`, точек и кандидатов в 24 сценариях даёт те же ключи, мм и ничьи (JS и Python);
  - **QA-группы:** COLOCATED, пересчитанные из точных координат, совпадают с evidence; флаг привязан по ID; записи категории не сливаются;
  - **копия среза с `edges_inclusive=false`:** угол отклоняется (JS и Python).
- Находки по QA (информационно, `runs/stage12_a5b5e2d.json`):
  - группа Шымкента (69.5958, 42.3167) из 10 записей **межкатегорийная**: 4 поликлиники, 3 школы, по одной записи колледжа, госучреждения и аптеки. В плане по школам у записи из группы `colocated_group.size=10`, а ничья по категории — 3;
  - правило «точное совпадение 5 знаков» **разрезает физическое скопление**: 2 записи в 1,11 м от группы из 4 (69.60702, 42.31757/42.31758) в COLOCATED не попадают.

## Этап 3 — привязка ближайшей записи к provenance/QA (done)

- В `geo_v2.js` и `geo_v2_ref.py` добавлены `sourceEvidence`, `candidateEvidence`, `bindNearestSources` и `MESSAGES_RU` (API — `API.md`). Статус положения записи всегда `source_reported_unverified` / `not_confirmed`; кандидат поверх записи остаётся `hypothetical` с флагом `coincides_with_source`.
- `make_stage3.py` → `fixtures/stage3.json`: 14 случаев на обоих городах и обеих категориях:
  - provenance и QA всех записей категории; неизвестный ключ, `hypothetical:` и запись другой категории → `unknown_source`;
  - запись без общих координат: ничьей нет, «подтверждено» тоже нет;
  - общие координаты: Шымкент, группа из 10 — 3 школы / 4 поликлиники в ничьей; Астана — пара поликлиник без COLOCATED. Ничья раскрыта (`tie_shared_coordinates`);
  - кандидат поверх записи → `coincides_with_source`.
- `stage_checks.py` (этап 3):
  - **provenance/QA против исходных файлов:** 110 ответов JS и Python; provenance = `sources[]` в `data.js`, флаги = `evidence.qa` и точные совпадения координат; ни одного «confirmed/verified» вне отрицаний;
  - **таблица чужого среза или версии метрики** → `stale_table`;
  - **явная синтетика:** две школы на равном расстоянии с разными координатами → `tie_equal_distance`, меньший ID; запись без `record_id` и без `sources[]` помечена;
  - **срез без QA** → `qa_unavailable`;
  - **сверка с действующим v1 сборки** (`web/whatif.js` a5b5e2d): на 100 точках ближайшая запись и мм совпадают с `nearest_before` / `round(before·1000)` — 0 расхождений.

## Реально выполненные проверки (этапы 1–3)

`python3 research/round-8-results/K03/run_tests.py --app-root <копия a5b5e2d> --stages 1,2,3` → **PASS 21, FAIL 0, SKIP 0** (`runs/stage123_a5b5e2d.json`).

Отрицательный контроль (`runs/negative_controls_s3.txt`): копия, ставящая `confirmed` записи без QA-флагов, → 3 FAIL; копия без флага colocated → 2 FAIL.

## Реально выполненные проверки (этапы 1–2, промежуточный прогон)

`python3 research/round-8-results/K03/run_tests.py --app-root <копия a5b5e2d> --stages 1,2` → **PASS 14, FAIL 0, SKIP 0** (`runs/stage12_a5b5e2d.json`).

Отрицательный контроль (`runs/negative_controls_s12.txt`):
- копия JS с ничьей «hypothetical раньше source» → 8 несоответствий;
- копия с исключёнными границами bbox → 2 + 16 несоответствий.

Оба прогона — FAIL, как и должно быть.

## Ограничения

- Модуль не встроен в BUILD; интеграцию city-plan-v2 на конкретном SHA я не проверял. Сверка с v1 (`whatif.js`) — это сверка расчёта ближайшей записи, а не проверка v2-интерфейса.
- Стоимость, веса, контрольные точки и кандидаты в fixtures — synthetic. Записи — Overture из сборки (вторичный источник, юридически и на месте не проверены).
- Границы районов не используются и не проверяются (задание K03 r8 — без нового обзора границ).
- Окружение: Linux, Python 3.11.15, node v22.22.0; pyproj 3.7.2 — только для проверки геодезии (без него SKIP). Модуль и оракул используют только stdlib и встроенные средства.

## Как сборщику подключить и проверить

1. Скопировать `geo_v2.js` в `web/` и подключить после `facts.js`. Контекст:
   ```js
   CITY_PLAN_GEO.buildGeoContext(window.CITY_EVIDENCE, window.CITY_OBS, city, category, {sha256hex: CITY_FACTS.sha256hex})
   ```
2. Проверить интегрированную копию:
   ```bash
   python3 research/round-8-results/K03/run_tests.py --app-root <копия нового SHA> --stages 1,2,3 --js <копия>/web/geo_v2.js
   ```
3. Если `data.js`/`evidence.js` нового SHA другие, тест вернёт TEST_INCOMPATIBLE. Тогда fixtures пересоздаются:
   ```bash
   python3 research/round-8-results/K03/make_fixtures.py --app-root <копия> --target-sha <SHA>
   python3 research/round-8-results/K03/make_stage2.py --app-root <копия> --target-sha <SHA>
   python3 research/round-8-results/K03/make_stage3.py --app-root <копия> --target-sha <SHA>
   ```

## Воспроизведение

```bash
git fetch origin claude/beautiful-clarke-sbzomj
python3 research/round-5-results/K03/extract_build.py --sha a5b5e2ddbe087c4eab8e947748cdf69dbae84a0d --out /tmp/app8
python3 research/round-8-results/K03/run_tests.py --app-root /tmp/app8 --stages 1,2,3 --json /tmp/k03r8.json
```

## Файлы

- **Модуль и оракул:** `geo_v2.js`, `geo_v2_ref.py`, `API.md`.
- **Тесты:** `run_tests.py`, `node_runner.cjs`, `stage_checks.py`.
- **Генераторы fixtures:** `make_fixtures.py`, `make_stage2.py`, `make_stage3.py`.
- **Fixtures и прогоны:** `fixtures/stage{1,2,3}.json`, `runs/`.
- **Входы:** `inputs/` (r7 fixtures K03 @ c2557ef, manifest).
