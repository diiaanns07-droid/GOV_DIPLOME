Задача / идентификатор: K03, география Астаны и Шымкента по A12/AST-A12
Агент / город / сфера: K03 (Claude Code), shared (astana + shymkent), данные/ГИС
Обновлено: 2026-10-05, UTC
Статус: partial (локальная проверка выполнена; официальная актуальность заблокирована сетью)
Рабочая ветка: claude/clever-mccarthy-pywscu
Исходный коммит: 0a169ef2b3ed7e431d4ffc2a4ee27702b2422a0a
Назначенные пути: research/next-round/K03/, этот файл

Цель: установить доступные районные границы и ID, проверить конфликты OSM на сохранённой геометрии, выпустить реестр территорий без выдуманных полигонов.

Что реально сделано:
- Проверен доступ: adilet.zan.kz, stat.gov.kz, overpass-api.de, openstreetmap.org — proxy CONNECT 403 (host_not_allowed). Повторов не было.
- Независимая сборка 11 relation из data/geo_sources/astana_districts_overpass.json (osm_base 2026-09-22T08:45:51Z).
- Подтверждены AST-A12: объединение 789,257 км² из 4 частей; эксклав Байконура 9,021 км² внутри Целиноградского района; тройная вершина (contains пусто, covers 3 района); Сарайшык admin_level 8, v17 от 2026-09-21; соседи без площадного пересечения.
- Уточнение: OSM-теги kato у 4 районов Астаны (у Нуры и Сарайшыка нет); слой продукта = сырой OSM (IoU 1.0).
- Шымкент: полигонов нет; есть только коды КПСиСУ 1979 и 197910–197914 (A10; 197914 с 2023), без расшифровки.
- Реестр 18 строк: territory_registry.csv/.json.

Файлы результата:
- research/next-round/K03/REPORT.md
- research/next-round/K03/territory_registry.csv
- research/next-round/K03/territory_registry.json
- research/next-round/K03/k03_geometry.py, geometry_result.json
- research/next-round/K03/build_registry.py
- research/next-round/K03/network_check.txt

Проверки:
- k03_geometry.py (Python 3.11.15, shapely 2.1.2, pyproj 3.7.2) → exit 0, geometry_result.json.
- build_registry.py → 18 rows. JSON обоих файлов проходит python -m json.tool.
- Не запускалось: Natural Earth сверка (файла нет), тесты продукта (код продукта не менялся).

Доказательства и ограничения:
- OSM — общественный источник, не юридическая граница; свежесть снимка 2026-09-22 не проверена.
- Коды Шымкента — из чужой выборки A10 (WebFetch 2026-10-04), K03 не перепроверял; справочника кодов нет.
- Названия районов Шымкента (A12-F016) и KZ-79 (A12-F018) — гипотезы, в реестре не сопоставлены с кодами.

Незавершённое:
- official_status всех строк = not_verified; КАТО из классификатора; соответствие 1979xx → районы; геометрия Шымкента.

Следующий конкретный шаг:
1. Из среды с доступом: акт о районах (adilet.zan.kz/акимат) и классификатор КАТО для обоих городов; Overpass по Шымкенту из A12 §4.3 с сохранением osm_base; заполнить official_status и kato в реестре.

Для воспроизведения (из корня):
- python3 -m venv /tmp/geo && /tmp/geo/bin/pip install shapely pyproj
- /tmp/geo/bin/python research/next-round/K03/k03_geometry.py > research/next-round/K03/geometry_result.json
- python3 research/next-round/K03/build_registry.py

Конфликты и зависимости: K05 (контракт данных) может использовать поля реестра; A10 — источник кодов Шымкента.
