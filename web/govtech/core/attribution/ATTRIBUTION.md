# Атрибуция: компактный геопакет K10 (раунд 3), Шымкент и Астана

Пакет: `research/round-3-results/K10/`. Данные — вторичные (`observed_secondary`), выпуск Overture Maps `2026-09-23.1`. Это не официальный реестр и не полный реестр города.

Строки ниже построены по полю `sources[]` каждой записи (dataset, license, property). Поле `sources.license` — указание лицензии в записи, а не полная юридическая проверка. Рекомендованные формулировки атрибуции Overture, OpenStreetMap, Meta, Foursquare и TomTom из этой среды не открывались.

## По файлам

### `data/astana/connectors.geojson` (astana, записей: 2309, sha256 `74a77d2ed250d6a55ee478054a6e89a4de15fc96f65063176a1194345994e801`)

- OpenStreetMap (provider `osm`, resource `planet`, version `2026-09-09`) — **ODbL-1.0**; относится к: (вся запись); записей sources: 2309
- Тексты: LICENSES/ODbL-1.0.txt

### `data/astana/places_social.geojson` (astana, записей: 65, sha256 `f5722c4455ca37d7ff23c2b48dc6e0097737e1cdc9e5faea8c0ed8dd4200e343`)

- Overture (provider `overture`, resource `confidence_calculation`, version `2026-09-17`) — **CDLA-Permissive-2.0**; относится к: /properties/confidence; записей sources: 65
- meta (provider `meta`, resource `meta`, version `2026-09-14`) — **CDLA-Permissive-2.0**; относится к: (вся запись); записей sources: 62
- meta (provider `meta`, resource `meta`, version `2026-08-24`) — **CDLA-Permissive-2.0**; относится к: (вся запись); записей sources: 2
- Foursquare (provider `foursquare`, resource `foursquare`, version `2026-04-14`) — **Apache-2.0**; относится к: (вся запись); записей sources: 1
- Записей без OSM как источника всей записи: 65 (Foursquare, meta).
- **Шапка `attribution` во входном файле** (Overture Maps Foundation / © OpenStreetMap contributors (ODbL-1.0)) не соответствует sources: не названы ['Foursquare', 'meta']; названы, но отсутствуют в записях ['OpenStreetMap'].
- Тексты: LICENSES/Apache-2.0.txt, LICENSES/CDLA-Permissive-2.0.txt

### `data/astana/segments.geojson` (astana, записей: 1326, sha256 `5fc1b3b5f6cabad6e2edfd042bb3727aa8fd0c7bcba9962175025e37eb08dbb9`)

- OpenStreetMap (provider `osm`, resource `planet`, version `2026-09-09`) — **ODbL-1.0**; относится к: (вся запись), /routes; записей sources: 1568
- TomTom (provider `tomtom`, resource `orbis`, version `2637`) — **ODbL-1.0**; относится к: (вся запись); записей sources: 8
- Записей без OSM как источника всей записи: 8 (TomTom).
- **Шапка `attribution` во входном файле** (Overture Maps Foundation / © OpenStreetMap contributors (ODbL-1.0)) не соответствует sources: не названы ['TomTom']; названы, но отсутствуют в записях —.
- Тексты: LICENSES/ODbL-1.0.txt

### `data/shymkent/connectors.geojson` (shymkent, записей: 1729, sha256 `8bbd25959eef559abeccb39d99884d96caf920d219f5a71f11298ade5e27bca0`)

- OpenStreetMap (provider `osm`, resource `planet`, version `2026-09-09`) — **ODbL-1.0**; относится к: (вся запись); записей sources: 1729
- Тексты: LICENSES/ODbL-1.0.txt

### `data/shymkent/places_social.geojson` (shymkent, записей: 55, sha256 `e0959270b962362a400723fba0ae26d8190e2ab0ac11278bd93cf872b7b003e7`)

- Overture (provider `overture`, resource `confidence_calculation`, version `2026-09-17`) — **CDLA-Permissive-2.0**; относится к: /properties/confidence; записей sources: 55
- meta (provider `meta`, resource `meta`, version `2026-09-14`) — **CDLA-Permissive-2.0**; относится к: (вся запись); записей sources: 54
- meta (provider `meta`, resource `meta`, version `2026-08-24`) — **CDLA-Permissive-2.0**; относится к: (вся запись); записей sources: 1
- Записей без OSM как источника всей записи: 55 (meta).
- **Шапка `attribution` во входном файле** (Overture Maps Foundation / © OpenStreetMap contributors (ODbL-1.0)) не соответствует sources: не названы ['meta']; названы, но отсутствуют в записях ['OpenStreetMap'].
- Тексты: LICENSES/CDLA-Permissive-2.0.txt

### `data/shymkent/segments.geojson` (shymkent, записей: 1084, sha256 `055b0e7aaef8d5b42fdbb6663f46ef245156b33a0f92b8f94cc73ab7a9c77648`)

- OpenStreetMap (provider `osm`, resource `planet`, version `2026-09-09`) — **ODbL-1.0**; относится к: (вся запись); записей sources: 1175
- TomTom (provider `tomtom`, resource `orbis`, version `2637`) — **ODbL-1.0**; относится к: (вся запись); записей sources: 1
- Записей без OSM как источника всей записи: 1 (TomTom).
- **Шапка `attribution` во входном файле** (Overture Maps Foundation / © OpenStreetMap contributors (ODbL-1.0)) не соответствует sources: не названы ['TomTom']; названы, но отсутствуют в записях —.
- Тексты: LICENSES/ODbL-1.0.txt

## Тексты лицензий

Каталог `LICENSES/` содержит побайтные копии `text/<id>.txt` из https://github.com/spdx/license-list-data @ `31ba1a50e5397e00a304dbadc76531740e89ee48` (нормализованные тексты SPDX, а не файлы с сайтов стюардов). Тексты не изменялись.

- `LICENSES/Apache-2.0.txt` — sha256 `074e6e32c86a4c0ef8b3ed25b721ca23aca83df277cd88106ef7177c354615ff` — sha256 совпадает
- `LICENSES/CDLA-Permissive-2.0.txt` — sha256 `4531a67d443284d93ffed0803df5b10634aff21c3d77e381f2d48af01d875868` — sha256 совпадает
- `LICENSES/ODbL-1.0.txt` — sha256 `77d2692c3d64efdd4db18dce2407699baf62930e2b50d6e5ed90b48acf16b7c1` — sha256 совпадает

## Что относится к чему

- **Данные** (`data/`) — условия по `sources[].license` записей (выше).
- **Код K10** (`scripts/`, `selection/`, `tests/`) — лицензия кода не указана. Условия данных к коду не применяются, и наоборот.
- **Производные значения K10** (`k10_group`, `k10_foot_access`, `k10_*`) — классификация K10 поверх данных. Условия производного набора для ODbL-частей — ODbL 4.4 (share-alike); для CDLA-P-2.0 — 3.1 (Results без ограничений). Юридического заключения нет.

## Неизвестно

- Общие условия и рекомендуемая строка атрибуции Overture Maps Foundation.
- Требования к атрибуции Meta, Foursquare (включая наличие NOTICE для Apache-2.0 4(d)) и TomTom Orbis.
- Точная формулировка OSM на openstreetmap.org/copyright. Строка «© OpenStreetMap contributors» взята из пакета K10 и данных продукта и не сверена с первоисточником.
