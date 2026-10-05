# K11 round 6 — STATUS

Роль: **REVIEW**, задание `research/round-6/review/K11.txt` («Готовность к запуску»).
Ветка: `claude/save-work-handoff-fmjw6r`. Предыдущий результат: `6aea792` (раунд 5). Он же **test_source_sha**.
Обновлено: 2026-10-05, UTC.
Статус: **done** для приёмки `064ed25`. Windows — только modeled/not_run. Патч к I13 только предлагается.

Целевая сборка (**target_sha**): `064ed25368341edaa50289bc29e21dda7bdd9440`, `claude/beautiful-clarke-sbzomj`, `prototypes/city-evidence/`. На момент проверки это вершина ветки. Извлечено 174 файла, id blob всех совпали. Назначение: `codex/research-import-2026-10-05` @ `edee718`.

## Итог (`ACCEPTANCE.json`)

- **PASS (run, Linux):**
  - I1 файлы;
  - I2 UTF-8;
  - I3 нет абсолютных путей;
  - I4 `pathToFileURL` (+ M3 modeled);
  - I5 `run-demo.bat` есть, аргументы проверены через `serve.py`;
  - I6 README;
  - I7 сервер, loopback, 404, path traversal;
  - I8 остановка своего сервера с кодом 0 без трассировки;
  - I10 браузер по http и `file://`;
  - I11 режим `--url`;
  - I12 занятый порт и отсутствующие файлы.
- **MODELED_PASS:** I9 — cp1251/cp1252 stdout больше не роняет `serve.py`.
- **FAIL (minor):** I13. `tests/smoke.cjs` L8 по умолчанию пишет в `../../research/round-5-results/BUILD/smoke`.
  - В полном checkout это задокументированная папка сборщика, `git status` остаётся чистым.
  - В отдельной копии папки прототипа создаёт 6 файлов за её пределами (минимальное воспроизведение в `ACCEPTANCE.json`).
  - Это не блокирует запуск демо.
- **NOT_RUN:** I14, реальный Windows.

Несовместимостей теста нет: smoke раунда 5 запущен без изменений.

## Реально выполненные команды

Linux, Python 3.11.15, Node 22.22.0, Playwright 1.56.1:
1. `extract_build.py --sha 064ed25… --out <dir>` → 174 files, 0 mismatches.
2. `k11_demo_smoke.py --app-root <dir>/prototypes/city-evidence --browser`, ×2 → оба раза 18 pass, 1 fail (S8), 3 modeled_pass, 2 info, 1 not_run. Статусы всех проверок совпали.
3. `k11r6_launch_extra.py --app-root …` → X1–X3 pass.
4. Свой `serve.py` + `k11_demo_smoke.py --url … --browser` → 8 pass, 1 info. Сервер остановлен SIGINT, код 0, порт свободен.
5. `git worktree add --detach … 064ed25`; `node tests/smoke.cjs` (команда из README) → exit 0, 23 PASS; `git status --porcelain` пуст до и после.
6. Отдельная копия `city-evidence`, `node tests/smoke.cjs` → exit 0, но 6 файлов в `<parent>/research/round-5-results/BUILD/smoke`.

Отчёты: `runs/*.json|txt`, пути временного каталога заменены метками.

## Ограничения

- Windows не запускался: ни `run-demo.bat`, ни `py -3`, ни браузер. `chcp 65001`, `%~dp0` и `pause` проверены только чтением.
- M1–M3 — моделирование на Linux.
- `--open` проверен с `BROWSER=true`: браузер не открывался.
- Сообщение при занятом порте — трассировка `OSError`. Отмечено как информация, не как fail.

## Следующий шаг

1. Минимальный `proposed_smoke_outdir.patch` к I13 в этой папке. Затем сессия с настоящим Windows выполняет `run-demo.bat` и `k11_demo_smoke.py --url http://127.0.0.1:8765/` и закрывает I14.
