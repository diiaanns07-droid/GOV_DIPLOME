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

Статус каждого пункта в `0bf27de` — **не исправлено**. Исправление только **предложено** (`proposal/attribution_demo.patch`) и проверено на копии в scratch. В ветку BUILD оно не вносилось, поэтому не FIXED.

## Checker
`check_demo_attribution.py` — только stdlib.
- `--app-root <извлечённая prototypes/city-evidence>`: проверяет поставку `web/` и входы. С `--repo <git>` дополнительно сверяет каждый файл manifest с `git show <sha>:<path>`.
- `--url <BASE>`: проверяет только то, что отдаёт сервер. Без доступа к `inputs/` checker не видит поставщиков, которых нет в `data.js` (TomTom), поэтому A6/A7 в этом режиме дают WARN, а не FAIL.

Baseline на `0bf27de`:
- `baseline/app_root_0bf27de.json` — PASS 3, WARN 2, FAIL 8, INFO 2;
- `baseline/url_0bf27de.json` — PASS 0, WARN 3, FAIL 6, INFO 1.

Код выхода 1 — это ожидаемые FAIL baseline, а не дефект новой версии.

## Patch-предложение (`proposal/attribution_demo.patch`)
Изменения только в исходниках сборки. Сгенерированные файлы получаются повторным запуском инструментов.
- `tools/copy_inputs.py`: новый слот `k08_attr` — K08 R4 @ 182cb1b, `attribution/LICENSES/{ODbL-1.0,CDLA-Permissive-2.0,Apache-2.0}.txt`, `ATTRIBUTION.md`, `attribution.json`. Копирование побайтное, через `git show`, с записью в `source_manifest.json`.
- `tools/build_data.py`:
  - у сегментов сохраняется `dataset`, у мест — источники уровня property (Overture `/properties/confidence`);
  - `cities.*.attribution` считается по `sources[]` всех трёх слоёв, а не берётся из константной шапки K10; добавлены `licenses`, `source_counts`, `attribution_file`;
  - тексты лицензий копируются в `web/LICENSES/` с проверкой sha256 SPDX @31ba1a50, генерируется `web/ATTRIBUTION.md`.
- `web/app.js`:
  - подвал выводит атрибуцию города из данных и ссылку «атрибуция и лицензии» → `ATTRIBUTION.md`;
  - карточка дороги показывает фактический `dataset` (TomTom/OSM) вместо жёсткого «OSM»;
  - в карточке места показывается property.
- `tests/smoke.cjs:89`: копирование `web/` рекурсивное (`fs.cpSync`). Без этого тест «отсутствующий файл» падал с EISDIR на `web/LICENSES/`.

### Положительный контроль (на копии 0bf27de с применённым предложением; не FIXED в BUILD)
- `copy_inputs.py`: 45 файлов. `build_data.py`: 55/65 объектов, 1084/1326 сегментов, как и в baseline.
- checker `--app-root --repo`: PASS 14, FAIL 0 (`positive_control/app_root_patched_on_0bf27de.json`). Inputs 45/45 совпадают с upstream.
- checker `--url` (serve.py): PASS 12, FAIL 0 (`positive_control/url_patched_on_0bf27de.json`).
- `test_checker.py --app-root <patched>`: 6/6 мутаций обнаружены (`positive_control/test_checker_mutations.txt`).
- Тесты сборки на исправленной копии: `unittest` 7 OK, `node tests/conformance.cjs` all passed, `node tests/smoke.cjs` 16/16 PASS (baseline тоже 16/16). Подвал в Chromium: «Meta (CDLA-Permissive-2.0); Overture Maps Foundation (CDLA-Permissive-2.0); TomTom (ODbL-1.0); © OpenStreetMap contributors (ODbL-1.0) · Overture 2026-09-23.1 · атрибуция и лицензии» со ссылкой `ATTRIBUTION.md`.
- sha256 выходов web: `positive_control/web_outputs.sha256`.

### Повтор для сборщика на исправленной версии
```bash
git apply research/round-5-results/K08/proposal/attribution_demo.patch      # или собственное исправление
git fetch origin claude/dazzling-mayer-drhsxk                                # объекты для k08_attr и --repo
python3 prototypes/city-evidence/tools/copy_inputs.py && python3 prototypes/city-evidence/tools/build_data.py
python3 research/round-5-results/K08/check_demo_attribution.py --app-root prototypes/city-evidence --repo .
python3 research/round-5-results/K08/test_checker.py --app-root prototypes/city-evidence
python3 prototypes/city-evidence/serve.py 8765 &  python3 research/round-5-results/K08/check_demo_attribution.py --url http://127.0.0.1:8765/
```
Ожидаемо на исправленной версии: 0 FAIL. На baseline 0bf27de — 8 FAIL (app-root) и 6 FAIL (url), это зафиксированные ожидаемые падения.
