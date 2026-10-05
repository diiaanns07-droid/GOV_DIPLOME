# K01 раунд 4 — STATUS

- **Роль:** REVIEW, слот K01. Ветка `claude/loving-thompson-nmajdo` (вход раунда-4 snapshot: 50df8eb).
- **Статус: done** для минимального объёма задания (копия, прогон, REPRO.md). Расширения не делались.
- **Входы:** `origin/codex/research-import-2026-10-05` @ `cadba4d` (`research/round-4/snapshots.json`, `review/K01.txt`);
  K10: `claude/save-work-handoff-j7pc05` @ `ea703f1ddd3a411430a981164a78a7dda64ec909`, `research/round-3-results/K10/`.

## Сделано
- Пакет K10 (25 файлов) скопирован из git-объектов байт-в-байт в `inputs/K10/` с `inputs/COPY_MANIFEST.json`.
- Прочитаны `offline_check.py`, `geo_util.py`, `k10_rules.py`, `tests/test_package.py`, `expected_counts.json`, README, manifest;
  просмотрены внешние ссылки в `download.py` и `selection/*.py`.
- Прогон в новой временной папке вне клона; итог и 7 недостатков переноса — `REPRO.md`.

## Реально запущенные проверки
- `offline_check.py` из cwd=`/` — exit 0, `errors: []`; отчёт идентичен двум закоммиченным отчётам K10.
- `unittest discover` — 8/8 OK (в папке пакета и из другого cwd).
- Независимая сверка sha256/bytes/features по manifest — 6/6 + 2 selection.
- Checkout с `core.autocrlf=true` + `offline_check` — exit 0.
- Пробы: тест подмены использует исходные `geo_util`/`k10_rules` (подтверждено); `socket`-блокировка остаётся после `run()` (подтверждено).
- Не запускались: `download.py`, `select_bbox.py`, `crosscheck_round2.py` (нужны сеть или незакоммиченные raw раунда 2); pytest (не установлен).

## Ограничения
- Проверены целостность и повторяемость пакета, а не истинность данных Overture/OSM и не полнота городских реестров.
- Города не смешивались: проверки по shymkent и astana идут раздельно, как в manifest.

## Следующий шаг
Сборщику/K10: исправить п.3 (тест подмены через subprocess) и п.4 (восстановить `socket` в `finally`), добавить sha256 manifest и скриптов (п.2).
Повтор: `git fetch origin claude/save-work-handoff-j7pc05 && python3 research/round-4-results/K01/copy_k10.py <tmp> && cd <tmp>/K10 && python3 scripts/offline_check.py && python3 -m unittest discover -s tests -v`.
