# STATUS — K08, раунд 4, REVIEW: атрибуция и происхождение пакета K10

**Статус:** done в объёме задания: матрица, готовые attribution-файлы, адаптер и patch. Юридической проверки нет; неизвестные условия поставщиков перечислены.

- Роль: REVIEW (не BUILD). Ветка: `claude/dazzling-mayer-drhsxk`, slot K08 в `research/round-4/snapshots.json` @ codex/research-import-2026-10-05. Задание: `research/round-4/review/K08.txt`.
- Вход: K10 `claude/save-work-handoff-j7pc05` @ `ea703f1ddd3a411430a981164a78a7dda64ec909`, `research/round-3-results/K10/`. Получен через `git archive`, без merge; входные файлы не изменялись (sha256 до и после совпали).
- Тексты лицензий: SPDX license-list-data @ `31ba1a50e5397e00a304dbadc76531740e89ee48`, скачаны в раунде 3. Повторно не запрашивались, sha256 сверены.

## Выходы (`research/round-4-results/K08/`)
| Путь | Что |
|---|---|
| `MATRIX.md`, `matrix.json` | файл / источник / условия / доказательство / неизвестно; находки F1–F7 |
| `attribution/ATTRIBUTION.md` | готовая атрибуция по фактическим `sources[]` каждого файла пакета |
| `attribution/attribution.json` | то же в машиночитаемом виде (поставщики, лицензии, property, проверка шапки) |
| `attribution/LICENSES/ODbL-1.0.txt`, `CDLA-Permissive-2.0.txt`, `Apache-2.0.txt` | побайтные копии текстов SPDX; sha256 в `logs/LICENSES.sha256` |
| `scripts/build_attribution.py` | адаптер: только stdlib, без сети, только чтение пакета; строит attribution.* и проверяет sha256 текстов (код 1 при расхождении) |
| `download_py_attribution.patch` | patch для `research/round-3-results/K10/scripts/download.py`: attribution и license_texts в шапке считаются по sources каждого файла вместо константы строки 177 |
| `logs/` | результаты проверок |

## Главное
- F1: sources[] сохранены полностью (все 10 полей, включая property и record_id). Прошлый пробел K08-C5 закрыт.
- F2: шапка `attribution` всех файлов — константа. В places_social указан OSM, хотя записей OSM там нет; Meta (CDLA-P-2.0) и Foursquare (Apache-2.0) не названы.
- F3: 9 сегментов, у которых источник всей записи — TomTom Orbis (ODbL-1.0), не описаны атрибуцией «© OpenStreetMap».
- F4: в пакете нет текстов лицензий. CDLA-P-2.0 2.1 и Apache-2.0 4(a) требуют их при передаче, ODbL 4.2 — уведомления.
- F5: 26 записей sources ссылаются на /routes, но колонка routes не извлечена.
- F6: условия Overture, Meta, Foursquare (NOTICE) и TomTom, а также формулировка OSM copyright не проверены.

## Реально выполненные проверки
- sha256 6 файлов data/ совпали с `package_manifest.json`. Подсчитаны sources[] по всем записям.
- `scripts/download.py` и `offline_check.py` K10 прочитаны. `offline_check.py` запущен: ok, сеть заблокирована. `python3 -m unittest discover -s tests`: 8 OK. Лицензии они не проверяют.
- `build_attribution.py` на пакете: 3 текста лицензий совпали по sha256, расхождение шапки в 4 файлах (places и segments обоих городов). Входы не изменились.
- Негативные проверки адаптера: изменённый байт в тексте лицензии даёт код 1; удалённый текст — «ОТСУТСТВУЕТ».
- Patch: `git apply --check` на чистом worktree ea703f1 проходит, `py_compile` ok. Новые функции `attribution_from`/`licenses_from` проверены офлайн на закоммиченных записях (`logs/patch_helper_offline_test.txt`). Копия пакета с этими шапками проходит проверку адаптера без расхождений (`logs/patched_headers_adapter_check.json`).
- **Не запускалось:** `download.py` с patch, потому что нужна сеть и пересборка из S3. После применения patch sha256 файлов data/ и манифест изменятся, их надо пересобрать командой K10.

## Ограничения
Тексты — нормализованные версии SPDX, а не файлы с сайтов стюардов. Страницы атрибуции Overture, openstreetmap.org/copyright, условия Meta, Foursquare и TomTom не открывались. Юридического заключения нет. Лицензия кода K10 не указана. Условия данных к коду не применяются.

## Следующий шаг
Сборщику: положить `attribution/ATTRIBUTION.md` и `attribution/LICENSES/` рядом с пакетом. При следующей пересборке применить `download_py_attribution.patch`, выполнить `python3 research/round-3-results/K10/scripts/download.py`, затем `offline_check.py` и `scripts/build_attribution.py <пакет> <out>`: должно быть `header_mismatch: []`.

## Воспроизведение
```bash
git fetch origin claude/save-work-handoff-j7pc05
mkdir k10 && git archive ea703f1ddd3a411430a981164a78a7dda64ec909 research/round-3-results/K10 | tar -x -C k10
python3 research/round-4-results/K08/scripts/build_attribution.py k10/research/round-3-results/K10 research/round-4-results/K08/attribution
(cd k10 && git apply --check -p1 ../research/round-4-results/K08/download_py_attribution.patch)
```
