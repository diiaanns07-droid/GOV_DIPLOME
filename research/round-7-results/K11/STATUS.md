# K11 round 7 — STATUS

Задание: `research/round-7/tasks/K11.txt` («Запуск и инструкция сценария»). Спецификация: `research/round-7/FEATURE_SPEC.txt` (`codex/research-import-2026-10-05` @ `7927fa8`).
Ветка: `claude/save-work-handoff-fmjw6r`. Предыдущие результаты: `3eaf08e` (раунд 6), первый этап раунда 7 отправлен отдельным коммитом.
Обновлено: 2026-10-05, UTC.
Статус: **done** в объёме:
- проверка запуска кандидата;
- изолированный эталон файлов сценария + fixtures + тесты;
- единый launch smoke;
- RUNBOOK.

Windows — modeled/not_run. **Функция в сборке не интегрирована** (её нет в `c58a3b2`).

Проверенный кандидат: `claude/beautiful-clarke-sbzomj` @ `c58a3b2b175cf978ad785fef7f88d8fd9b1338f2`, `prototypes/city-evidence/`. `git diff b3e4dc4 c58a3b2 -- prototypes/city-evidence/` пуст. Это вершина ветки на момент проверки. Извлечено 185 файлов, id blob совпали.

## Результаты

1. **Запуск `c58a3b2` (Linux):**
   - `k11_demo_smoke.py --browser` → 19 pass, 0 fail, 3 modeled_pass, 1 not_run (Windows);
   - X1–X3 pass;
   - smoke сборщика → 24 PASS, `git status` чистый: `tests/.gitignore` → `out/`, дефект I13 раунда 6 закрыт сборщиком.
2. **Функции what-if в `c58a3b2` нет** (`city-whatif-v1`, `proposed_object`, `control_point` не найдены).
3. `whatif_io.py` — изолированный эталон файлов `city-whatif-v1`:
   - строгий разбор: 256 KiB до разбора, UTF-8, дубликаты ключей, `NaN`/`Infinity`/`1e999`;
   - контракт: версия, город, snapshot, категория, 1..10 точек, уникальные NFC-ID ≤ 64 без URL и разметки, bbox, не больше одного проекта с `kind=hypothetical`, без лишних полей;
   - импортированные `results` отбрасываются;
   - канонический UTF-8 без BOM, LF, атомарная запись;
   - чтение байтами, CLI с ASCII-выводом.
4. `fixtures/`: 21 файл + `MANIFEST.json`. 5 принимаются: кириллица и казахский в именах и ID, пробелы, 10 точек, BOM+CRLF, `results`. 16 отвергаются с ожидаемыми кодами. Случай больше 256 KiB создаёт тест. Snapshot и bbox взяты из `data.js` `c58a3b2`.
5. `test_whatif_io.py`: 9 тестов, OK:
   - ожидаемые исходы из другого каталога;
   - сохранение под казахским именем, повторное открытие по относительному и абсолютному пути;
   - побайтная стабильность;
   - недопустимый сценарий не пишется;
   - CLI при stdout=cp1252 [MODELED Windows];
   - сверка snapshot с копией приложения.

   Проверка порчами: 3 из 3 ловятся (`runs/mutation_check.txt`).
6. `run_k11r7.py` — единый launch smoke (запуск, X1–X3, файлы сценария, наличие функции). На `c58a3b2` из чужого каталога: pass, pass, pass (9 OK), `not_present`, exit 0. Ветка `fixtures_stale` проверена на копии с изменённым `data.js`.
7. `RUNBOOK.md`: точная инструкция Linux (проверено) и Windows (не запускалось), работа с файлами сценария, коды отказов, команды повторения.

## Реально выполненные команды

Linux, Python 3.11.15, Node 22.22.0, Playwright 1.56.1:
- `extract_build.py --sha c58a3b2… --out <dir>`;
- `k11_demo_smoke.py --app-root … --browser`;
- `k11r6_launch_extra.py --app-root …`;
- `node tests/smoke.cjs` в чистом worktree + `git status --untracked-files=all`;
- `make_fixtures.py --app-root … --app-sha c58a3b2…`;
- `K11_APP_ROOT=… python3 test_whatif_io.py` → 9 OK; без `K11_APP_ROOT` → 8 OK + 1 skip (skip ≠ pass);
- проверка порчами (3 временные порченые копии);
- `run_k11r7.py --app-root … --browser` из `/tmp`;
- `run_k11r7.py` на копии с изменённым `data.js` → `fixtures_stale`.

Отчёты: `runs/`.

## Ограничения

- Windows не запускался: ни `run-demo.bat`, ни `py -3`, ни имена файлов на NTFS, ни браузер. cp1252 у CLI и M1–M3 смоделированы. macOS (NFD-имена) не проверялся.
- Интерфейса экспорта и импорта нет: эталон проверяет контракт файлов, а не будущий код сборщика.
- `source_snapshot` в fixtures — соглашение K11, а не формат сборщика.

## Следующий шаг

1. Когда сборщик добавит экспорт и импорт `city-whatif-v1`, прогнать `run_k11r7.py --app-root <копия нового SHA> --browser`. Если отпечаток сборщика другой, перегенерировать fixtures (`make_fixtures.py`) под его формат snapshot. Сессия с Windows выполняет раздел Windows из RUNBOOK.
