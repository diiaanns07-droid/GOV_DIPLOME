# K10, раунд 4 — STATUS (REVIEW: права прохода и топология)

| Поле | Значение |
|---|---|
| Роль | REVIEW, слот K10 (`research/round-4/review/K10.txt`) |
| Ветка | `claude/save-work-handoff-j7pc05` |
| Задание и снимки | `origin/codex/research-import-2026-10-05` @ `cadba4d200387b9a97cb2d1c5aa0a8fd5a150c1e` |
| Входы | K10 `claude/save-work-handoff-j7pc05` @ `ea703f1ddd3a411430a981164a78a7dda64ec909` (пакет читается на месте, SHA сверены); K07 `claude/save-work-handoff-ku3ej3` @ `6778deda6d3f3a7f27698f651c1b0046d2a9aae9` (4 файла скопированы побайтно в `inputs/K07/`) |
| Статус | **done** для заданного объёма: объяснение причин отклонения, адаптер, тесты. Новых выгрузок не делалось, это вне задания |
| Обновлено | 2026-10-05 |
| Пути | только `research/round-4-results/K10/` |

## Сделано

- **`REVIEW.md`** — почему K07 может отклонять пакет:
  1. квадрат 2×2 км вместо рамки 6×6 км; квадрат Астаны не пересекает ядро K07;
  2. нет заголовка `k07_clip`;
  3. права прохода и многоуровневость неизвестны у большинства сегментов;
  4. 37–42% узлов попадают в краевую зону;
  5. места в GeoJSON, а K07 просил JSONL.

  Плюс 5 найденных проблем в `graph_check.py` K07 и рекомендации, в K07 не применённые.
- **`scripts/k10_k07_adapter.py`:**
  - проверка SHA пакета;
  - заголовок `k07_clip` с честным `k07_requested_clip_6x6km_satisfied: false`;
  - разбиение по `at` по геодезической длине;
  - режимы графа `topology` и `strict_foot`;
  - край определяется по флагам данных;
  - `unknown` и `conditional` никогда не становятся `allowed`.
- **`tests/test_k07_compat.py`**, 16 тестов: реальные соединители, разбиение по `at`, мост без общего соединителя, `conditional` и `unknown`, путь за край, топологический режим на реальных данных, совместимость рамки. Синтетические фикстуры помечены `SYNTHETIC`.
- **`scripts/run_review.py`** → `results/review_measurements.json`: `check()` K07 на пакете без адаптера и с адаптером, перекрёстная таблица прав, ошибки привязки по `at`, пересечения, узлы края, пример маршрута.
- **`scripts/copy_inputs.py`** → `inputs/MANIFEST.json`: побайтные копии через `git show` и `write_bytes` с SHA256 и сверка пакета K10 на месте.

## Реально выполненные проверки

- **Самотест K07** (`GC.selftest()`) в окружении Python 3.12.3, networkx 3.6.1, shapely 2.1.2, pyproj 3.8.0 → passed.
- **`python -m unittest discover -s research/round-4-results/K10/tests -v`** → 16 тестов, OK (около 22 с).
- **`run_review.py`** → exit 0; числа из него приведены в REVIEW.md.
- **SHA256** всех 6 файлов пакета на диске совпали с `package_manifest.json` K10. SHA копий K07 записаны в `inputs/MANIFEST.json`.

## Ограничения

- **Рамка 6×6 км по запросу K07 не скачивалась** (задание запрещает новые выгрузки). Квадрат 2×2 км не выдаётся за выполнение этого требования.
- **Пешеходная проходимость не установлена.** Явных разрешений 7 сегментов в Шымкенте и 0 в Астане. Топологический режим показывает только связь в графе данных.
- **Overture/OSM** — вторичные данные. Соцобъекты в квадрате — не реестр города.
- **Проверено только на Linux.** `main()` K07 не вызывался, чтобы не перезаписать его файл результата.

## Следующий шаг

1. Для BUILD или K07: если нужна рамка 6×6 км, перезапустить `research/round-3-results/K10/scripts/download.py`, указав в `selection/*_bbox_selection.json` рамки из `K10_REQUEST.md`. Затем выполнить `offline_check` и этот набор тестов. Отдельно исправить `foot_rule` и линейную привязку в K07 (см. «Рекомендации» в REVIEW.md).

## Воспроизведение

```bash
/usr/bin/python3.12 -m venv /tmp/v && /tmp/v/bin/pip install networkx==3.6.1 shapely==2.1.2 pyproj==3.8.0
python3 research/round-4-results/K10/scripts/copy_inputs.py           # из корня репозитория, нужен git с fetch ветки K07
/tmp/v/bin/python -m unittest discover -s research/round-4-results/K10/tests -v
/tmp/v/bin/python research/round-4-results/K10/scripts/run_review.py > research/round-4-results/K10/results/review_measurements.json
```
