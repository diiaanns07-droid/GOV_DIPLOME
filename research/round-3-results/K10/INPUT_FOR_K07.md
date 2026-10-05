# Вход для K07: компактный геопакет K10 (раунд 3)

- **Ветка:** `claude/save-work-handoff-j7pc05`. Точный SHA коммита указан в STATUS.md и в ответе K10. Читать нужно по SHA, а не по названию ветки.
- **Папка:** `research/round-3-results/K10/`.
- **Выпуск Overture:** `2026-09-23.1`.

## Как прочитать без слияния веток

```bash
git fetch origin claude/save-work-handoff-j7pc05
SHA=<sha из STATUS K10>
mkdir -p inputs/K10 && for f in package_manifest.json \
  data/shymkent/places_social.geojson data/shymkent/segments.geojson data/shymkent/connectors.geojson \
  data/astana/places_social.geojson   data/astana/segments.geojson   data/astana/connectors.geojson \
  scripts/offline_check.py scripts/geo_util.py scripts/k10_rules.py; do
  mkdir -p "inputs/K10/$(dirname $f)"
  git show "$SHA:research/round-3-results/K10/$f" > "inputs/K10/$f"   # bash: байты без перекодирования
done
python3 inputs/K10/scripts/offline_check.py   # должно вывести "ok": true и exit 0; сеть внутри заблокирована
```

`git show … > file` в bash сохраняет байты как есть. В PowerShell используйте `git show "$SHA:path" | Set-Content -AsByteStream` или `git archive`. После копирования SHA256 файлов должны совпасть с `package_manifest.json`, это и проверяет `offline_check.py`.

## Точные пути и содержимое

| Путь в `research/round-3-results/K10/` | Объекты: Шымкент / Астана | Ключевые поля |
|---|---|---|
| `data/<city>/places_social.geojson` | 55 / 65 точек | `k10_group` (school, preschool, college_university, hospital, outpatient_clinic, pharmacy, government_office), `name_primary`, `confidence`, `taxonomy`, `addresses`, `sources[]` (dataset, license, record_id, update_time), `overture_id`, `overture_version` |
| `data/<city>/segments.geojson` | 1 084 / 1 326 линий (все road) | `connectors[]` {`connector_id`, `at`}, `class`, `subclass`, `subclass_rules`, `access_restrictions`, `road_flags`, `level_rules`, `width_rules`, `road_surface`, `speed_limits`, `sources[]` (OSM `record_id` с `@version`), производные `k10_foot_access`, `k10_flags`, `k10_levels`, `k10_crosses_bbox_edge`, `k10_length_m` |
| `data/<city>/connectors.geojson` | 1 729 / 2 309 точек | `overture_id`, `overture_version`, `k10_inside_bbox` |
| `package_manifest.json` | — | bbox, S3-ключи и row groups, колонки, запросы, SHA256 и число объектов в каждом файле |

**Квадраты** — `[lon_min, lat_min, lon_max, lat_max]` EPSG:4326, около 2×2 км:
- Шымкент: `[69.593365, 42.306645, 69.617658, 42.324611]`;
- Астана: `[71.418372, 51.163033, 71.447, 51.181]`.

Правило выбора квадрата записано в `selection/<city>_bbox_selection.json`.

## Правила построения графа

1. **Ребро** — пара соседних по `at` соединителей одного сегмента. **Узел** — `connector_id`.
2. **Не соединяйте линии по пересечению геометрий.** Эстакады и тоннели (`k10_flags`: is_bridge, is_tunnel; `k10_levels` ≠ 0) пересекают другие дороги без общего соединителя.
3. **Проверка K10 (структура, без учёта пешеходных прав):**
   - Шымкент: 7 компонент, крупнейшая — 98,13% длины;
   - Астана: 8 компонент, 99,16%;
   - без сегментов с `k10_foot_access = denied`: Шымкент 7 компонент (98,11%), Астана 9 компонент (99,05%).

## Пригодность для пешеходов: что известно и что нет

| `k10_foot_access` (road) | Шымкент | Астана | Смысл |
|---|---|---|---|
| unknown | 954 | 1 138 | правил для пешеходов нет: **не разрешение** |
| conditional | 115 | 166 | из них одностороннее движение (`denied` + `heading=backward` без `mode`): 110 / 159; прочие условия: 5 / 7 |
| denied | 8 | 22 | явный запрет `mode: foot` |
| allowed | 7 | 0 | явное разрешение или designated для foot |

Поэтому сеть можно показывать как «граф OSM-дорог и дорожек». Утверждение «пешеход реально пройдёт» данными не подкреплено. Одностороннее движение для пешеходов обычно не действует, но K10 это не проверял.

## Край квадрата

- **Сегменты**, пересекающие границу: Шымкент 136, Астана 143. Сохранены целиком, у них `k10_crosses_bbox_edge = true`.
- **Соединители вне квадрата:** 276 / 260. Это точки разреза графа.
- **Места ближе 100 м к краю:** 6 / 8.

Не объявляйте объект недостижимым, если путь к нему может проходить вне квадрата. Достижимость считается только в пределах этого графа.

## Чего в пакете нет

- официальных реестров школ и поликлиник, мощностей, населения, официального состава районов;
- точного списка всех соцобъектов квадрата (Overture неполон);
- рельсов и воды: в квадратах они не встретились (`by_subtype`: только road).
