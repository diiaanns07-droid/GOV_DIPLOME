# K10 — доступ к источникам и реальные образцы: STATUS

| Поле | Значение |
|---|---|
| Задача | K10: проверить доступ к источникам A12/AST-A12, получить 3–5 небольших реальных наборов для обоих городов |
| Агент / город / сфера | K10 (слот Claude, не роль A10) / Шымкент и Астана / данные и ГИС |
| Обновлено | 2026-10-05, ~05:30 UTC |
| Статус | **partial**, checkpoint 1 |
| Рабочая ветка | `claude/save-work-handoff-j7pc05` |
| Исходный коммит | `b87e5af6eeb6a5bdc33037a9f16d4e3377166ee5` (`codex/research-import-2026-10-05`), влит обычным merge |
| Назначенные пути | `research/next-round/K10/`, `research/handoffs/shared/K10/` |

## Цель и критерий готовности

Для каждого из 3–5 наборов, покрывающих оба города, нужно:
- скачать небольшой образец, а не только открыть страницу каталога;
- записать прямую ссылку, дату, поля, единицы, географию и условия использования;
- для недоступного указать точное препятствие.

## Главное

1. **Казахстанские госисточники из этой среды недоступны.** Прокси отклоняет CONNECT с кодом 403 по политике сети окружения. Это касается stat.gov.kz, taldau, gov.kz, data.egov.kz, adilet, Казгидромета, а также OSM (Overpass, API, Nominatim, Geofabrik), HDX, GHSL, WorldPop, Zenodo, Hugging Face, сайта и документации Overture. Каждый хост проверен **одним** запросом, полный список — в `access_log.json`.
2. **Доступен публичный S3-бакет Overture Maps** (`overturemaps-us-west-2`). Из него по HTTP Range скачаны только нужные row groups последнего выпуска `2026-09-23.1` для обоих городов: административные полигоны и точки интереса.
3. **Шымкент впервые получил районные полигоны**, привязанные к OSM relation@version. На уровне районов их **4**: Абай, Әл-Фараби, Еңбекші, Қаратау. Они покрывают 100% полигона города (1 169,968 км²) без пересечений. «Тұран» есть только как macrohood. Официальный состав районов **не проверен**: БНС и Әділет заблокированы.
4. **Районы Астаны в продукте** (`data/astana_districts.geojson`) совпадают с Overture: IoU = 1,0 по всем 6 районам.
5. **Независимо воспроизведена находка AST-A12.** Эксклав Байқоңыра площадью 9,021 км² одновременно лежит в Целиноградском районе Акмолинской области.
6. **Новое наблюдение по Астане.** 11,034 км² полигона города (точка около 71,4046; 50,872) не входят ни в один район. Сарайшық в данных — locality, а не county.
7. **Прототип первой функции «социальные объекты → районы»** работает на обоих городах (E02). Однако число объектов в Overture мало: например, в категории school 79 точек на весь Шымкент. Значит, Overture — материал для **конвейера**, а не измерение обеспеченности.

## Наборы

| ID | Набор | Статус | Города | Лицензия (по полям записей) | Образец |
|---|---|---|---|---|---|
| K10-D01 | Overture divisions/division_area | SV | оба | ODbL-1.0 (OSM); у region также CC0 (Esri Community Maps) | `samples/*_districts_overture.geojson` |
| K10-D02 | Overture places/place | SV | оба | CDLA-Permissive-2.0 (Meta, Microsoft, Overture), CC0-1.0 (AllThePlaces), Apache-2.0 (Foursquare) | `samples/*_places_social_sample.jsonl` |
| K10-D03 | geoBoundaries gbOpen KAZ ADM1/ADM2 | META | оба | ODbL-1.0 | `samples/geoboundaries_KAZ_ADM*_metaData.json` |

Прямые URL файлов parquet, номера row groups, время и объём загрузки — в `datasets.json` и `provenance/*.provenance.json`.

## Файлы результата

Все пути от `research/next-round/K10/`:
- `STATUS.md` — этот файл;
- `datasets.json` — реестр наборов: URL, дата, поля, единицы, география, лицензия, ограничения;
- `access_log.json` — проверка доступа, по одному запросу на каждый хост;
- `samples/shymkent_districts_overture.geojson`, `samples/astana_districts_overture.geojson` — полигоны города и районов с исходной точностью;
- `samples/shymkent_places_social_sample.jsonl` (95 строк), `samples/astana_places_social_sample.jsonl` (105 строк) — до 15 объектов на группу;
- `samples/geoboundaries_KAZ_ADM1_metaData.json`, `samples/geoboundaries_KAZ_ADM2_metaData.json`;
- `results/E01_district_coverage.json` — площади, покрытие, пересечения, сравнение со слоем продукта;
- `results/E02_social_poi_by_district.json` — счётчики по районам при confidence ≥ 0 и ≥ 0,5;
- `provenance/*.provenance.json`, `provenance/raw_extracts.sha256` — журнал извлечения и sha256 сырых выгрузок (сами выгрузки 3–22 МБ в git не добавлялись);
- `scripts/overture_extract.py`, `scripts/check_districts.py`, `scripts/places_by_district.py`, `scripts/make_samples.py`.

## Проверки (реально выполнены)

- **Доступ.** 20 хостов заблокированы (403 CONNECT), 9 доступны. Подробности в `access_log.json`, отказы также видны в `recentRelayFailures` прокси.
- **Чтение Overture.** Схема прочитана, затем извлечение:
  - division_area: Шымкент — 181 строка, ~55 МБ; Астана — 91 строка, ~50 МБ;
  - places: Шымкент — 2 608 строк; Астана — 8 815 строк; ~33 МБ на каждый запуск.
- **E01** (`check_districts.py`): все полигоны валидны (`is_valid`).
  - Шымкент: районы покрывают город на 100%, пересечений нет.
  - Астана: покрытие 98,62%, пересечений между районами нет; IoU со слоем продукта 1,0 для 6 из 6.
  - Отдельная проверка эксклава: Байқоңыр ∩ Целиноград = 9,021 км².
- **E02** (`places_by_district.py`):
  - доля точек внутри города: Шымкент 2 553 из 2 608, Астана 8 481 из 8 815;
  - точек внутри города, но вне районов: 0 в обоих городах;
  - повторов (то же нормализованное имя в той же ячейке ~100 м): 1 в Шымкенте, 13 в Астане.
- **Целостность geoBoundaries.** sha256 метаданных совпал с oid LFS.
- **Синтаксис.** Все новые JSON, GeoJSON и JSONL прочитаны парсером без ошибок.
- **Не запускалось:** тесты приложения (код продукта не менялся); импортированные скрипты A12/AST-A12 (не требовались).

## Доказательства и ограничения

- **Overture — вторичный, неофициальный источник.**
  - Границы — это OSM по состоянию на дату выпуска. Например, Сарайшық в Overture имеет версию r19733918@16 с update_time 2026-09-10. AST-A12 указывал правку 21.09.2026; возможно, выпуск её ещё не включает (не проверено).
  - Места — агрегат коммерческих и открытых источников, полнота неизвестна.
- **Условия использования** взяты из поля `sources.license` каждой записи. Общая страница атрибуции Overture заблокирована. Для ODbL нужна атрибуция «© OpenStreetMap contributors», для производной базы — share-alike.
- **Официальные данные** (БНС, КАТО, data.egov.kz, акты) в этом раунде **не получены**: заблокирован доступ к хостам. Это не означает, что таких данных нет.
- **Синтетики нет.** Все числа в `results/` вычислены из скачанных строк. Разметка групп (school, hospital и т.д.) — правило K10 поверх таксономии Overture, это производные данные.

## Незавершённое

- Нет образца дорожной и пешеходной сети (Overture transportation) для K07.
- Нет кодов ISO 3166-2 и сверки `region` (KZ-79, KZ-71) со справочником.
- Нет сверки с официальными реестрами и населением.
- Не проверено, существует ли официально пятый (Туранский) район Шымкента.

## Следующий конкретный шаг

1. Извлечь по обоим городам небольшой образец Overture `transportation/segment` (дороги и пешеходные пути) с подсчётом по классам. Сохранить его как K10-D04 для базовой доступности по сети у K07.

## Для воспроизведения

```bash
python3 -m venv venv && venv/bin/pip install pyarrow==25.0.1 shapely==2.1.2 pyproj==3.7.2 requests
cd research/next-round/K10
RAW=/path/to/raw && mkdir -p $RAW
for c in shymkent astana; do
  ../../../venv/bin/python scripts/overture_extract.py extract divisions division_area $c $RAW/${c}_division_area.jsonl
  ../../../venv/bin/python scripts/overture_extract.py extract places place $c $RAW/${c}_places.jsonl \
     --cols id,geometry,confidence,names,addresses,sources,operating_status,basic_category,taxonomy,version,bbox
done
../../../venv/bin/python scripts/check_districts.py $RAW ../../../data/astana_districts.geojson > results/E01_district_coverage.json
../../../venv/bin/python scripts/places_by_district.py $RAW > results/E02_social_poi_by_district.json
../../../venv/bin/python scripts/make_samples.py $RAW samples
```

Переменная `OVERTURE_RELEASE` фиксирует выпуск (по умолчанию `2026-09-23.1`). Секретов и ключей не требуется. Python 3.11.15.

## Зависимости от других агентов

- **K03 (география):** получает полигоны Шымкента и вопрос о 4 или 5 районах.
- **K07 (доступность):** получает E02 и предупреждение о полноте мест.
- **K08 (проверка):** список заблокированных хостов, а пункты «официальный состав районов» и «эксклав Байқоңыра» стоит включить в его проверку по первоисточникам.
- **Владелец:** чтобы открыть госисточники, в настройках окружения нужно добавить домены (Network access → Custom → Allowed domains): `stat.gov.kz`, `taldau.stat.gov.kz`, `data.egov.kz`, `www.gov.kz`, `adilet.zan.kz`, при необходимости `overpass-api.de`, `download.geofabrik.de`.
