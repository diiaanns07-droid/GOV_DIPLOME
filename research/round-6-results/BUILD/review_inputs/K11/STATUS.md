# K11 round 5 — STATUS

Роль: **REVIEW**, задание `research/round-5/review/K11.txt` («Проверка запуска демо»).
Ветка: `claude/save-work-handoff-fmjw6r`. Предыдущие результаты: `03fa7fa` (раунд 4), `55b10d8` (первый этап раунда 5).
Обновлено: 2026-10-05, UTC.
Статус: **done** в объёме: «smoke-тест `--app-root`/`--url` + baseline + проверка на копии с предложением». Windows-часть modeled/not_run. Патч только предложен, **не FIXED**.

Входы:
- назначение: `origin/codex/research-import-2026-10-05` @ `2883aeb6eb68babc9b346b0aa927d4c633f5163d` (`research/round-5/snapshots.json`, `review/K11.txt`);
- проверяемый BUILD (база): `claude/beautiful-clarke-sbzomj` @ `0bf27deb8549b325b34a9610402613d745544edb`, `prototypes/city-evidence/`. Извлечён `extract_build.py`: 57 файлов, id blob совпали;
- информационно: более новый BUILD `fd43f9a9179c7b49382337d9fe82e2770d5b48f3` (150 файлов, id blob совпали).

Мой путь: `research/round-5-results/K11/`. `prototypes/city-evidence/`, ветка сборщика и чужие отчёты не менялись.

## Сделано

- `k11_demo_smoke.py` (stdlib):
  - `--app-root` — статические проверки, свой `serve.py` на свободном порту, HTTP-проверки localhost, явная остановка своего процесса (SIGINT → terminate → kill) с проверкой, что порт освобождён;
  - `--url` — только HTTP-проверки;
  - `--browser` — headless Chromium по http и по `file://` через `pathToFileURL`;
  - моделирование Windows: M1/M2 cp1251/cp1252, M3 `path.win32`; W1 not_run.
- `extract_build.py`: побайтное извлечение снимка по SHA.
- Отчёты:
  - `baseline_0bf27de.*`: 15 pass / 4 fail (S4, S5, S6, S8) / modeled_fail M2, M3 / modeled_pass M1 / not_run W1;
  - `proposal_on_0bf27de.*`: 19 pass / 0 fail / 3 modeled_pass;
  - `url_mode_0bf27de.*`: 8 pass;
  - `info_fd43f9a.*`: как baseline.
- `proposed_launch_fix.patch`: `serve.py`, `run-demo.bat`, `tests/smoke.cjs`, README. Это предложение сборщику.
- `README.md`: команды, проверки, ожидаемые падения baseline. `CHECK_LOG.md`: журнал команд.

## Реально выполненные проверки (Linux, Python 3.11.15, Node 22.22.0, Playwright 1.56.1 Chromium)

См. `CHECK_LOG.md`. Ключевое:
- smoke на `0bf27de`: exit 1, ожидаемо, падения перечислены в README;
- на копии с патчем: exit 0;
- `git apply --check` патча на `0bf27de`: OK;
- `tests/smoke.cjs` сборщика на копии с патчем: 16 PASS;
- `--url` против отдельно запущенного сервера: exit 0;
- `fd43f9a`: exit 1 по тем же проверкам.
- Найдены и исправлены ошибки самого теста:
  - регистр заголовков;
  - ложное совпадение `run.bat`;
  - `argv` в Node;
  - M3 теперь зависит от S4;
  - заголовок B1 в режиме `--url`.

  Baseline пересобран финальной версией.

## Ограничения

- Windows не запускался. M1–M3 моделируют только кодировку перенаправленного stdout и семантику путей. `run-demo.bat` проверен лишь чтением. Ветка остановки для Windows (`CREATE_NEW_PROCESS_GROUP`, `terminate`) не исполнялась.
- Заголовки `Content-type` без charset — info, а не fail: кодировку задаёт `<meta charset>`. Поведение `mimetypes` реестра Windows для `.js` не проверено.
- Рецепт Linux не является проверенным запуском на Windows.

## Следующий шаг

1. Сборщик, если сочтёт нужным, переносит патч на этапе C и повторяет: `python research/round-5-results/K11/k11_demo_smoke.py --app-root <копия нового SHA>/prototypes/city-evidence --browser --label <SHA>`. Сессия с настоящим Windows запускает `run-demo.bat` и smoke и закрывает W1.
