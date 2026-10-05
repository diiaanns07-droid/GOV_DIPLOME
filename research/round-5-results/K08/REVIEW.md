# K08 R5 — атрибуция поставляемого демо `prototypes/city-evidence`

База: BUILD K04, ветка `claude/beautiful-clarke-sbzomj` @ `0bf27deb8549b325b34a9610402613d745544edb`. Проверяется готовая сборка: `web/`, `inputs/`, `source_manifest.json`. Сравнение — с пакетом атрибуции K08 раунда 4 (`claude/dazzling-mayer-drhsxk` @ `182cb1b`, `research/round-4-results/K08/`).
Это техническая проверка наличия файлов, уведомлений и ссылок, а не юридическое заключение.

## Что уже есть в демо
- `inputs/` побайтно совпадает с `source_manifest.json` (40/40) и с upstream git-объектами по указанным SHA (40/40, отличий 0).
- Подвал карты (`web/app.js:214`) и блок «Источники» (`app.js:359`, из `data.js` `cities.*.attribution`) показывают «© OpenStreetMap contributors; Overture Maps Foundation».
- Карточка места выводит из данных `dataset · license · update_time · record_id` по каждому источнику записи (`app.js:294`).
- README и `index.html:116` говорят, что данные вторичные (Overture/OSM) и это не полный реестр.

## Чего не хватает именно в поставке (baseline, ожидаемые FAIL)
| ID | Что | Где | Сравнение с пакетом R4 |
|---|---|---|---|
| A2 | Нет текстов ODbL-1.0, CDLA-Permissive-2.0, Apache-2.0 | `web/` (сервер `serve.py` отдаёт только `web/`) | в R4 подготовлены `attribution/LICENSES/*.txt`; в сборку не скопированы |
| A3 | Нет файла атрибуции | `web/` | в R4 подготовлен `attribution/ATTRIBUTION.md`; в сборку не скопирован |
| A4 | Meta (CDLA-P-2.0, все места Шымкента и 64 Астаны) и Foursquare (Apache-2.0, 1 запись Астаны) не названы в общем уведомлении | `app.js:214`, `data.js attribution` | находка R4 F2 (константная шапка K10) перешла в демо без изменений |
| A6 | Ни у одного из 2410 сегментов в `data.js` нет `dataset` | `tools/build_data.py: seg_rec` | sources во входе есть (R4 F1), но адаптер сборки берёт только record_id/license/update_time |
| A7 | Карточка любой дороги подписана «Дорога (OSM через Overture)». 9 сегментов (1 Шымкент, 8 Астана), у которых источник всей записи — TomTom (ODbL-1.0), показываются как OSM с источником «— · ODbL-1.0 · —» | `app.js:300`, `app.js:308` | находка R4 F3 перешла в UI в виде неверной подписи |
| A5 (WARN) | Нет ссылки на openstreetmap.org/copyright; в `index.html` нет ни одного `href` | `index.html`, `app.js` | формулировка не сверена с первоисточником (страница не открывалась) |
| A10 (INFO) | В `source_manifest.json` нет поля для изменённых файлов. Сейчас изменённых нет, но схема не позволяет отдельно указать hash изменённого файла | `tools/copy_inputs.py` | — |
| (не в checker) | Подпись места «Confidence — оценка Overture» верна, но источник Overture CDLA-P-2.0 для `/properties/confidence` отброшен: `build_data.py` берёт только sources с пустым property | `tools/build_data.py:89` | R4 F1: property сохранено во входе, теряется в сборке |

Статус каждого пункта — **не исправлено** в `0bf27de`. Исправление ещё не предложено. Patch-предложение будет отдельным этапом в этой папке.

## Checker
`check_demo_attribution.py` — только stdlib.
- `--app-root <извлечённая prototypes/city-evidence>`: проверяет поставку `web/` и входы. С `--repo <git>` дополнительно сверяет каждый файл manifest с `git show <sha>:<path>`.
- `--url <BASE>`: проверяет только то, что отдаёт сервер. Без доступа к `inputs/` checker не видит поставщиков, которых нет в `data.js` (TomTom), поэтому A6/A7 в этом режиме дают WARN, а не FAIL.

Baseline на `0bf27de`:
- `baseline/app_root_0bf27de.json` — PASS 3, WARN 2, FAIL 8, INFO 2;
- `baseline/url_0bf27de.json` — PASS 0, WARN 3, FAIL 6, INFO 1.

Код выхода 1 — это ожидаемые FAIL baseline, а не дефект новой версии.
