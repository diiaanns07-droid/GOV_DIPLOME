# Объекты OpenStreetMap Астаны — LOCAL-1

Классификация: **real**. Исходные ответы Overpass сохранены без изменения JSON, с gzip-сжатием.

Bbox из `engine/civic_scenarios/graphs/osm-astana-walking-20260506.graph.json`: `[71.2079, 50.9206, 71.7953, 51.3612]` (west, south, east, north).

| Набор | Фильтр OSM | Объектов | gzip, байт | JSON, байт |
|---|---|---:|---:|---:|
| [Остановки](raw/bus_stops.json.gz) | `highway=bus_stop` | 967 | 25227 | 210078 |
| [Платформы общественного транспорта](raw/platforms.json.gz) | `public_transport=platform` | 729 | 22692 | 190593 |
| [Детские площадки](raw/playgrounds.json.gz) | `leisure=playground` | 348 | 36727 | 242602 |
| [Спортплощадки](raw/pitches.json.gz) | `leisure=pitch` | 716 | 65431 | 437670 |
| [Парки](raw/parks.json.gz) | `leisure=park` | 128 | 31328 | 170033 |
| [Скверы и сады](raw/gardens.json.gz) | `leisure=garden` | 52 | 6253 | 38276 |
| [Жилые кварталы](raw/residential.json.gz) | `landuse=residential` | 570 | 77750 | 477541 |
| [Места сбора мусора](raw/waste_disposal.json.gz) | `amenity=waste_disposal` | 102 | 4261 | 27692 |
| [Приём вторсырья](raw/recycling.json.gz) | `amenity=recycling` | 41 | 1880 | 14998 |
| [Фонари](raw/street_lamps.json.gz) | `highway=street_lamp` | 217 | 3116 | 28666 |
| [Школы](raw/schools.json.gz) | `amenity=school` | 175 | 26768 | 146741 |
| [Детские сады](raw/kindergartens.json.gz) | `amenity=kindergarten` | 147 | 16435 | 91677 |

Всего записей по наборам: **4192**; уникальных `(type, id)`: **3513**.
Общий размер архивов: **317868 байт**; лимит всей папки — 20 000 000 байт.

Один объект может входить в несколько наборов (например, остановка одновременно является платформой); при объединении следует удалять повторы по `(type, id)`.
Запросы включают node, way и relation. Использовано `out geom;`: у узлов lat/lon, у путей geometry, у отношений геометрия членов. Геометрия путей/отношений не обрезана по bbox и может выходить за него. Bbox не является административной границей Астаны.
Теги отражают полноту картирования OSM, а не полный городской реестр. Каждый набор — отдельный запрос; его время и `osm_base` указаны в SOURCE.json.

Проверки: JSON читается после распаковки; Overpass не вернул remark; теги совпадают с запросом; идентификаторы внутри набора уникальны; геометрия присутствует; SHA-256 сохранены в SOURCE.json.

Лицензия: [ODbL 1.0](https://opendatacommons.org/licenses/odbl/1-0/). Атрибуция: **© OpenStreetMap contributors** — [условия](https://www.openstreetmap.org/copyright).
Тексты запросов, endpoint, времена загрузки UTC, osm_base, размеры и контрольные суммы: [SOURCE.json](SOURCE.json).
