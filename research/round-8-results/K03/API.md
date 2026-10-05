# K03 r8 — геоадаптер city-plan-v2 (`geo_v2.js`, оракул `geo_v2_ref.py`)

Чистые функции без DOM. В браузере — `window.CITY_PLAN_GEO`, в Node — `require('./geo_v2.js')`. Python-оракул написан независимо, с теми же правилами и кодами ошибок.

## Контекст среза — `buildGeoContext(data, evidence, city, category, {sha256hex})`

- **`data`** = `window.CITY_EVIDENCE` (web/data.js), **`evidence`** = `window.CITY_OBS` (web/evidence.js).
- **`bbox`, `edges_inclusive`** — из `evidence.cities[city].spatial_unit`. bbox обязан совпадать с `data.cities[city].bbox`, иначе `bad_slice`.
- **`source_snapshot`** — `"sha256:" + sha256(JSON.stringify([schema, city, release, places_file_sha256, places_digest, bbox, edges_inclusive, metric_version]))`.
  - `places_digest` — sha256 отсортированного по ID массива `[id, r7(lon), r7(lat)]` **всех** мест города, где `r7(x) = Math.round(x·1e7)/1e7`.
  - Отпечаток считается из текущих данных; имя файла не используется.
- **`sources`** — записи только выбранной категории, отсортированные по ID:
  - `key: "source:<id>"`, `kind: "source"`;
  - `provenance`: `overture_id`, `overture_version`, `confidence`, `records[]` (dataset, record_id, license, update_time);
  - `qa`: `colocated_group`, `possible_duplicates[]`, `category_doubt`, `same_exact_coordinates` — флаги из `evidence.cities[city].qa` по ID записи.
- **`sources_digest`** — sha256 `[source_snapshot, category, [[id, lon, lat]…]]`.
- **`other_slices`** — bbox других городов, чтобы распознать точку чужого города.

## Проверка мест — `validatePlaces(ctx, {control_points, candidates}, {allowEmptyPoints})`

Ошибки типизированы: `GeoError{code, path}`. Проверки идут в таком порядке:
1. Форма объекта и массивов → `bad_shape`.
2. Число мест: контрольных точек 1..25 (`too_many_points`; при `allowEmptyPoints` допускается 0 — пустое состояние UI), кандидатов 0..16 (`too_many_candidates`).
3. Каждая контрольная точка `{id, lon, lat, weight}` — ровно эти поля:
   - `id` — строка 1..64 без управляющих символов (`bad_id`), уникальна в массиве (`duplicate_id`);
   - `weight` — целое 1..100 (`bad_weight`); это приоритет пользователя, а не численность;
   - координаты.
4. Каждый кандидат `{id, lon, lat, category, kind, cost}`:
   - `kind` только `hypothetical` (`bad_kind`);
   - `category` = категории контекста (`bad_category`);
   - `cost` — целое 1..1000000 условных единиц (`bad_cost`);
   - координаты.
5. Координаты (как K03 r7 `point_check`):
   - `not_number` → `not_finite` → `out_of_range`;
   - внутри bbox (границы по `edges_inclusive`, точное сравнение без допуска);
   - иначе `lon_lat_swapped` (только распознаётся) → `other_city` → `outside_bbox`.

**Район не проверяется.** Точка на спорной границе районов внутри bbox допустима.

Результат:
- копии с ключами `control:<id>` и `hypothetical:<id>`: пространство имён отделяет кандидатов от исходных `source:<id>`, даже при совпадении ID;
- у кандидата `coincides_with_sources` — ключи исходных записей с теми же координатами. Это справка: кандидат остаётся гипотетическим и не становится «существующим местом».

## Расстояния — `distanceTable(ctx, control_points, candidates)`

- `metric_version = "haversine-mm-v1"`: гаверсинус, R = 6371008.8, вход [lon, lat], промежуточное значение зажато в [0, 1]. Каждое расстояние один раз округляется: `Math.round(d_m·1000)`.
  - В Python так же (`js_round`). Формула `floor(x+0.5)` расходится с `Math.round` при x = 0.49999999999999994 — см. этап 2.
- `baseline[i]` — ближайшая исходная запись категории `{key, id, mm, tied_keys}`; `null`, если записей нет (а не 0).
- `to_candidates[i][j]` — расстояние в мм от точки i до кандидата j.
- Ключ ничьей `cmpNear`: (мм, source < hypothetical, ID по UTF-16). От порядка входных массивов не зависит.

`nearestAfter(table, i, selectedIdx, candidates)` → `{key, kind, mm}` или `null`. Гаверсинус в переборе не вызывается: только таблица.

## Вне области K03

`budget`, `max_selected`, `required/excluded`, метрики плана, перебор, Парето, digest задачи и объяснение относятся к другим модулям. Им передаются `distanceTable` и `cmpNear`.
