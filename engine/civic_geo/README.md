# engine/civic_geo — точность карты (R12, раунд 14)

Только стандартная библиотека Python. Граф OSM **только читается**
(`engine/civic_scenarios/graphs/osm-astana-walking-20260506.graph.json`, сверка sha256 по MANIFEST.json).

## Что внутри

| Файл | Что делает |
|---|---|
| `geo.py` | метры на плоскости вокруг точки, проекция на ломаную, обрезка ломаной (вершины OSM сохраняются), полигоны, упрощение, `max_offset_m` |
| `graph.py` | рёбра графа с формой OSM + тип дороги/казахское имя из `data/civic/astana/geo/way_tags.json`; сетка 100 м; `nearest()` |
| `segment.py` | `street_segment(graph, a, b)` — участок улицы по рёбрам (Дейкстра, «по одной улице» дешевле); `snap_polyline` для старых линий |
| `objects.py` | объекты OSM, дворы, ячейки 150 м (та же сетка, что у R07 `ui/civic_heat/geo.py`) |
| `targets.py` | `targets(lon, lat, category=None)` — 1–3 кандидата привязки жалобы по `target_kinds` из `research/round-14/categories_v2.json` |
| `accuracy.py` | проверки CONTRACT §8 и отчёт по всему, что показывает карта |
| `api.py` | функции для маршрутов `/api/civic/v2/...` (подключает R01) |
| `__init__.py` | `targets`, `target_geometry`, `street_snap`, `segment_between`, `objects_near`, `yard_at`, `geo_status` |
| `build_way_tags.py`, `build_geo_data.py`, `snap_demo.py` | пересборка данных в `data/civic/astana/geo/` |

## Команды

    python3 -m engine.civic_geo report [--json out.json]     # отчёт точности, код 1 при FAIL
    python3 -m engine.civic_geo targets 71.4289 51.1716 roads
    python3 -m engine.civic_geo segment 71.4251,51.1712 71.4326,51.1719 --kind road
    python3 -m engine.civic_geo bench 3000                   # время /targets
    python3 -m engine.civic_geo build-way-tags | build-data | snap-demo

## Правила точности (CONTRACT §8)

1. Участок улицы — только рёбра графа: середина берётся целиком из OSM, крайние рёбра обрезаются по проекции щелчка.
2. Остановки, площадки, парки — только реальные объекты OSM (`osm-node-…`, `osm-way-…`, `osm-relation-…`).
3. Проверки: линия ≤ 5 м от формы своих рёбер (проверяется каждые 2 м), остановка ≤ 60 м от улицы,
   координаты внутри полигонов районов из `data/civic/astana/geofence.json`.
4. Нет точного места — область «примерное место» (двор или ячейка 150 м), а не уверенная линия.

## Производительность

Первая загрузка графа ~1,7 с (кэш процесса, потокобезопасно); `targets` — p50 0,2 мс, p95 0,45 мс (3000 точек).
