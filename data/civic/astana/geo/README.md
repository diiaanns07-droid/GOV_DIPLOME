# data/civic/astana/geo — привязка к улицам и объектам OSM (R12, раунд 14)

Всё в этой папке собрано скриптами `engine/civic_geo/` из снимков OpenStreetMap.
Лицензия ODbL-1.0, атрибуция «© OpenStreetMap contributors» (https://www.openstreetmap.org/copyright).

| Файл | Что внутри | Чем собран | Источник |
|---|---|---|---|
| `way_tags.json` | для каждой линии графа: тип дороги (highway), казахское название, признак тротуара | `python3 -m engine.civic_geo build-way-tags` | `data/civic/astana/osm-walking/overpass.json.gz` (снимок 2026-05-06) |
| `objects.json` | остановки, детские и спортплощадки, парки, места для мусора: id OSM, имя ru/kk, точка, [полигон] | `python3 -m engine.civic_geo build-data` | `data/civic/astana/osm-objects/raw/*` (LOCAL-1) + остановки из снимка пешеходной сети |
| `yards.json` | дворы: полигоны `landuse=residential`, упрощены с допуском 1,5 м | то же | LOCAL-1 |
| `cells.json` | параметры сетки ~150 м для мест, где двора нет (`cell-<ix>-<iy>`) | то же | — |
| `demo_snapped.json` | демо-линии R05, привязанные к рёбрам графа (копия — `web/civic/map/demo_snapped.json`) | `python3 -m engine.civic_geo snap-demo` | `data/civic/astana/demo_synthetic.json` (СИНТЕТИКА) |
| `SOURCE.json` | входные файлы и их sha256, число объектов, что пропущено и почему | `build-data` | — |

Статус на сегодня — в `SOURCE.json` → `status`. Пока выгрузки LOCAL-1 нет, `objects.json` содержит только
остановки, которые есть в снимке пешеходной сети (узлы на линиях дорог), а `yards.json` пуст.
Когда LOCAL-1 положит `data/civic/astana/osm-objects/raw/`, выполнить:

    python3 -m engine.civic_geo build-data
    python3 -m engine.civic_geo snap-demo
    python3 -m engine.civic_geo report --json research/round-14-results/R12/accuracy_report.json

Объекты не придумываются: каждая запись — реальный объект OSM со своим id; демо-записи остаются синтетикой.
