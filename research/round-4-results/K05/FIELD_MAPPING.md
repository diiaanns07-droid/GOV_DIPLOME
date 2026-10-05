# Отображение полей для сборщика: K10 round 3 → k05-obs-v1.2

Источник: `research/round-3-results/K10/data/<city>/places_social.geojson`, `selection/<city>_bbox_selection.json` и `package_manifest.json` @ `ea703f1`. Код отображения — `k05r4_adapter.py`, проверка — `k05r4_contract.py`. Схема `schema/k05-obs-v1.2.schema.json`; v1.1 не изменена.

## Одна запись наблюдения = (город, квадрат, группа, порог confidence)

| Поле наблюдения | Откуда | Правило |
|---|---|---|
| `schema_version` | константа | `k05-obs-v1.2` |
| `city_id` | `places_social.geojson` → `city` | `shymkent` → `kz.shymkent`, `astana` → `kz.astana`. У каждого объекта `properties.city` должен совпадать, иначе ошибка `CITY_MISMATCH` |
| `geo_unit_id` | selection → `selected.row`, `selected.col` | `kz.<city>.k10sq_r<row>_c<col>`. Это **квадрат**, а не район |
| `spatial_unit.type` | константа | `bbox` |
| `spatial_unit.bbox` | selection → `selected.bbox` (= `places_social.bbox`) | `[xmin, ymin, xmax, ymax]`, EPSG:4326. Должен совпасть с `bbox` коллекции |
| `spatial_unit.edges_inclusive` | K10 `geo_util.point_in_bbox` | `true` (сравнения `<=`) |
| `spatial_unit.geometry_source`, `geometry_sha256` | путь и sha256 файла selection | — |
| `spatial_unit.overlaps_districts` | расчёт K05 (pyproj/shapely по полигонам K10 round 2) | доли площади квадрата в районах. При двух и более районах — предупреждение `CROSSES_DISTRICTS` |
| `indicator_id` | группа + порог | `overture_place_records.<k10_group>.conf_ge_0_0` или `.conf_ge_0_5` |
| `value` | счёт объектов с `properties.k10_group == g` и `confidence >= t` | `confidence = null` **не считается** и не превращается в 0. Если такие записи есть, порог > 0 даёт `coverage.complete=false` |
| `value_status` | по `value` | `0` → `reported_zero` (квадрат полон), `>0` → `reported`; не извлекавшаяся категория → `missing` |
| `missing_reason` | — | `not_collected` для групп вне K10 `social_group` (например, park); `zero_in_partial_coverage`, если охват неполный |
| `unit` | константа | `records` (записи Overture, не «школы») |
| `kind` | константа | `derived` (счёт поверх правила K10) |
| `period` | `package_manifest.release` | дата выпуска: `2026-09-23` |
| `release` | `package_manifest.release` | `2026-09-23.1` |
| `data_version` | `release` | `overture@2026-09-23.1` |
| `boundary_version` | selection | `k10_r3_square:r<row>_c<col>@<sha256[:12] selection>` |
| `source.url` | `package_manifest.cities.<c>.queries.places.files[0].url` | URL parquet в S3 |
| `source.sha256`, `source.path` | файл `places_social.geojson` | sha256 обязан совпасть с `package_manifest...files.places_social.sha256`, иначе адаптер останавливается |
| `source.retrieved_at` | `package_manifest.cities.<c>.started_utc` | — |
| `source.query` | `package_manifest...queries.places.query` | «point within bbox AND K10 social rule» |
| `source.locator` | — | `<path>#features[k10_group=g][confidence>=t]` |
| `source.evidence` | ветка/SHA K10 + `row_groups_read` | — |
| `coverage.complete` | — | `true`: это полный ответ запроса для квадрата и выпуска. Не означает полноту реестра района или города |
| `coverage.scope`, `selection` | — | текстом: «все записи выпуска с точкой в квадрате … не реестр района/города» |
| `method` | — | шаги K10 `download.py` + счёт K05; параметры: порог, bbox, ссылка K10 |
| `note` | — | районы квадрата и число записей ближе 100 м к краю |

## Чего сборщику не делать

- **Не складывать** квадрат с районными счётчиками E02 раунда 2/3. Агрегат отклоняет это: записи v1.1 без `spatial_unit` дают `LEGACY_UNIT`, район и bbox — `SPATIAL_MIX`.
- **Не делить** значение квадрата по районам пропорционально площади: распределение объектов неравномерно (см. REPORT §3).
- **Не подписывать** значение как «число школ». Подпись: «записей Overture (группа K10) в квадрате 2×2 км, выпуск 2026-09-23.1».
- **Показ:** `null` → «нет данных» с `missing_reason`; `0` → только при `reported_zero` и `coverage.complete=true`.
- **Не сравнивать города** по квадратам как по городам: квадраты выбраны по максимуму объектов, это не репрезентативная выборка.
- **Помечать** объекты с предупреждениями `COLOCATED` / `POSSIBLE_DUPLICATE` из `examples/<city>/square_object_qa.json` на карте как «координата/дубликат под вопросом».
