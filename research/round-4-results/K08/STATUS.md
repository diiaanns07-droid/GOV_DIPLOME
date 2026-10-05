# STATUS — K08, раунд 4, REVIEW: атрибуция и происхождение пакета K10

**Статус:** partial — матрица готова; attribution-файлы и адаптер — следующий этап.

- Роль: REVIEW (не BUILD). Ветка: `claude/dazzling-mayer-drhsxk`, slot K08 в `research/round-4/snapshots.json` @ codex/research-import-2026-10-05.
- Задание: `research/round-4/review/K08.txt`.
- Вход: K10 `claude/save-work-handoff-j7pc05` @ `ea703f1ddd3a411430a981164a78a7dda64ec909`, `research/round-3-results/K10/`. Получен через `git archive`, без merge.
- Выходы: `research/round-4-results/K08/` — `MATRIX.md`, `matrix.json`, `STATUS.md`.

## Сделано
- Матрица по 6 файлам data/ и не-данным файлам: что сохранено в sources, какие лицензии в записях, условия по первичным текстам, доказательство, что неизвестно.
- Находки F1–F7 (см. MATRIX.md). Главное:
  - F2: в шапке `attribution` файлов мест указан OSM, хотя все места — meta/Foursquare;
  - F3: 9 сегментов только от TomTom не покрыты атрибуцией OSM;
  - F4: в пакете нет текстов CDLA-P-2.0, Apache-2.0 и ODbL.

## Реально выполненные проверки
- sha256 всех 6 файлов data/ совпали с `package_manifest.json`.
- Подсчёт sources[] по всем записям (dataset, provider, resource, license, property, version).
- Прочитан `scripts/download.py` (строка 177 — константная attribution). `offline_check.py` прочитан и запущен: ok, сеть заблокирована. `python3 -m unittest discover -s tests`: 8 тестов OK.
- Тексты лицензий SPDX @31ba1a50 сверены по sha256 с журналом раунда 3. Новых сетевых запросов не делалось.

## Ограничения
Страницы атрибуции Overture, openstreetmap.org/copyright, условия Meta, Foursquare и TomTom не открывались: хосты заблокированы или это запросы к третьим сторонам. Тексты лицензий — нормализованные версии SPDX. Юридического заключения нет.

## Следующий шаг
Сделать `attribution/`: ATTRIBUTION.md для каждого файла по фактическим sources, LICENSES/ с текстами ODbL-1.0, CDLA-Permissive-2.0 и Apache-2.0 и sha256, адаптер, который строит атрибуцию из sources без изменения входов, и patch для download.py:177.
