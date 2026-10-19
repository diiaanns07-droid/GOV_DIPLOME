# Объекты OpenStreetMap Астаны — LOCAL-1 + LOCAL-10

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
| [Светофоры (узлы)](raw/traffic_signals.json.gz) | `highway=traffic_signals` | 891 | 13490 | 143630 |
| [Пешеходные переходы (узлы)](raw/crossings.json.gz) | `highway=crossing` | 3832 | 55864 | 622950 |

Всего записей по наборам: **8915**; уникальных `(type, id)`: **8236**.
Общий размер архивов: **387222 байт**; лимит всей папки — 20 000 000 байт.

Один объект может входить в несколько наборов (например, остановка одновременно является платформой); при объединении следует удалять повторы по `(type, id)`.
Запросы LOCAL-1 включают node, way и relation; LOCAL-10 (светофоры и переходы) — только node. Использовано `out geom;`: у узлов lat/lon, у путей geometry, у отношений геометрия членов. Геометрия путей/отношений не обрезана по bbox и может выходить за него. Bbox не является административной границей Астаны.
Теги отражают полноту картирования OSM, а не полный городской реестр. Каждый набор — отдельный запрос; его время и `osm_base` указаны в SOURCE.json.

Проверки: JSON читается после распаковки; Overpass не вернул remark; теги совпадают с запросом; идентификаторы внутри набора уникальны; геометрия присутствует; SHA-256 сохранены в SOURCE.json.

Лицензия: [ODbL 1.0](https://opendatacommons.org/licenses/odbl/1-0/). Атрибуция: **© OpenStreetMap contributors** — [условия](https://www.openstreetmap.org/copyright).
Тексты запросов, endpoint, времена загрузки UTC, osm_base, размеры и контрольные суммы: [SOURCE.json](SOURCE.json).

LOCAL-10: число объектов — число узлов OSM, а не уникальных перекрёстков или физических светофорных секций. Сохранены все узлы с указанными highway-тегами в bbox без дополнительного отсева. Проверены тип node, уникальность ID, соответствие тегам и координаты внутри bbox.
