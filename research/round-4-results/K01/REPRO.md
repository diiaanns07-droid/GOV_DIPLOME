# K01 раунд 4 (REVIEW): воспроизводимость геопакета K10 раунда 3

Вход: `claude/save-work-handoff-j7pc05` @ `ea703f1ddd3a411430a981164a78a7dda64ec909`,
путь `research/round-3-results/K10/` (25 файлов, 5 245 188 байт). SHA взят из
`research/round-4/snapshots.json` на `origin/codex/research-import-2026-10-05` @ `cadba4d`.
Дата прогона: 2026-10-05. Python 3.11.15, Linux; pytest не установлен (использован unittest).

## Итог
Пакет **воспроизводится офлайн**: проверка и 8 тестов проходят в новой временной папке вне клона,
отчёт `offline_check` побайтно совпадает с закоммиченными `results/offline_check_local.json` и
`results/offline_check_clean_clone_602f0c0.json` (sha256 `f263fb10…d662`). Ниже — найденные недостатки переноса;
блокирующих для офлайн-использования нет.

Проверялась **целостность и повторяемость** пакета, не правильность данных Overture/OSM, не полнота
городских реестров (это квадраты 2×2 км, `observed_secondary`, классификация соцобъектов — derived).

## Реальные команды и результат
| # | Команда | Exit | Результат |
|---|---|---|---|
| 1 | `python3 research/round-4-results/K01/copy_k10.py <T>` (git ls-tree + cat-file → `Path.write_bytes`) | 0 | 25 файлов; `diff -r` с копией в `inputs/` — идентичны; `inputs/COPY_MANIFEST.json` с blob и sha256 |
| 2 | `cd / && python3 <T>/K10/scripts/offline_check.py --json <T>/oc_run1.json` | 0 | `ok: true`, `errors: []`; открыты только 6 файлов данных + manifest → `run/oc_run1.json` |
| 3 | `cd <T>/K10 && python3 -m unittest discover -s tests -v` | 0 | 8/8 OK за 0.16 с → `run/ut.log` |
| 4 | независимый скрипт: sha256/bytes/features каждого файла из `package_manifest.json` + sha256 selection | 0 | 6/6 файлов данных и 2/2 selection совпали |
| 5 | сравнение `oc_run1.json` с двумя отчётами в `results/` | — | идентичны (dict и sha256) |
| 6 | `cd / && python3 -m unittest discover -s <T>/K10/tests -t <T>/K10/tests` | 0 | OK — тесты не зависят от cwd |
| 7 | clone c `core.autocrlf=true`, checkout `ea703f1 -- research/round-3-results/K10`, `offline_check.py` | 0 | `errors: []`; в 6 GeoJSON 0 символов LF/CR, поэтому EOL-конверсия Windows хэши не ломает |

Сеть: использовался только `git fetch` с GitHub. Raw Overture не скачивались, `download.py` не запускался.

## Зависимость от файлов вне пакета
| Скрипт | Внешние входы | Статус |
|---|---|---|
| `scripts/offline_check.py`, `tests/test_package.py` | нет (только stdlib, файлы пакета; аудит `open` подтверждает) | автономны |
| `scripts/download.py` | сеть: S3 Overture (~350 МБ, 533 запроса по manifest); pyarrow, shapely, requests | не запускался (сеть/скачивание вне задачи) |
| `selection/select_bbox.py` | `research/next-round/K10/samples/<city>_districts_overture.geojson` (раунд 2) и **незакоммиченная** raw-выгрузка мест `.jsonl` раунда 2; shapely | вне пакета; raw в git нет → выбор квадрата из пакета не воспроизводится |
| `selection/crosscheck_round2.py` | raw-выгрузки раунда 2 (sha256 в `research/next-round/K10/provenance/raw_extracts.sha256`) | вне пакета; `results/crosscheck_round2.json` — утверждение автора, не перепроверено |

## Конкретные недостатки переноса
1. **Выбор квадрата нельзя повторить из пакета.** `select_bbox.py`/`crosscheck_round2.py` требуют raw-выгрузок раунда 2,
   которых нет в Git, и полигона из другой папки `research/next-round/K10/`. Проверяемо только, что
   `selection/*.json` совпадают с sha256 в manifest — не то, что квадрат выбран по описанному правилу.
2. **`package_manifest.json` — корень доверия без собственной контрольной суммы.** Согласованная подмена
   данных и manifest не ловится `offline_check`; частично ловят `tests/expected_counts.json` (количества, а не хэши).
   Скрипты, `selection/*.py` и `results/` не хэшированы вовсе. Предложение: хранить sha256 manifest и скриптов
   в отдельном файле/коммите-якоре (например, в `INPUT_FOR_K07.md` или в теге).
3. **Тест подмены проверяет копию данных, но не копию кода.** В `TamperDetection` копия `offline_check.py`
   импортирует `geo_util`/`k10_rules` из уже загруженного `sys.modules` — подтверждено: модуль берётся из
   ORIGINAL-пакета. Подмена правил в копии осталась бы незамеченной этим тестом. Исправление: запускать копию
   отдельным `subprocess` (`python <dst>/scripts/offline_check.py`) и проверять exit code.
4. **Сетевая блокировка не снимается после `run()`.** `install_guards()` подменяет `socket.*` глобально и не
   восстанавливает их (в `finally` восстанавливается только `open`). Подтверждено: после `run()`
   `socket.create_connection` всё ещё бросает `NetworkBlocked`. Для импорта как библиотеки (K07/сборка) это
   побочный эффект на весь процесс; `test_network_blocked` от него и зависит (проверяет остаточную блокировку,
   а не блокировку во время проверки).
5. **Аудит открытых файлов неполный.** Перехватывается только `builtins.open`; `io.open`, `os.open`,
   `pathlib.Path.read_bytes` (через `io.open`) мимо аудита. Пока код этого не делает, но гарантия «открыты
   только файлы manifest» слабее, чем звучит.
6. **Версии зависимостей сборки.** `requirements-download.txt` и `tool_versions` фиксируют pyarrow 25.0.1 / shapely 2.1.2,
   но бит-в-бит повторяемость `download.py` (порядок признаков, округление) не проверялась; пакет frozen по
   выпуску `2026-09-23.1`, выпуски Overture со временем удаляются из бакета — пересборка в будущем может стать невозможной.
7. **pytest упоминается, но не нужен и не установлен** — работает `unittest`; README это допускает, расхождения нет.

## Файлы этого отчёта
- `inputs/K10/` — байтовая копия пакета; `inputs/COPY_MANIFEST.json` — blob/sha256 каждого файла и исходный SHA.
- `copy_k10.py` — скрипт копирования из git-объектов.
- `run/oc_run1.json`, `run/oc_run1.stderr` (пусто), `run/ut.log` — фактические выходы прогона.
