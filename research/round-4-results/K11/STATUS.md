# K11 round 4 — STATUS

Роль: **REVIEW**, задание `research/round-4/review/K11.txt` («Проверка инструкции запуска»).
Ветка: `claude/save-work-handoff-fmjw6r`. Мой предыдущий результат: `bbf3eee`.
Обновлено: 2026-10-05, UTC.
Статус: **partial**. Готов список проблем, K10 проверен запуском. Запуски K07/K02 и рецепт — следующий этап.

Входы (`origin/codex/research-import-2026-10-05` @ `cadba4d`, `research/round-4/snapshots.json`):
- K07 `claude/save-work-handoff-ku3ej3` @ `6778deda6d3f3a7f27698f651c1b0046d2a9aae9`;
- K10 `claude/save-work-handoff-j7pc05` @ `ea703f1ddd3a411430a981164a78a7dda64ec909`;
- K02 `claude/clever-mccarthy-pywscu` @ `24c1750f70d9e444ae551030d116bb6aa8ce5b7b`.

Назначенный путь: `research/round-4-results/K11/`.

## Сделано

- Прочитаны README, STATUS и все скрипты K07, K10 и K02 раунда 3.
- `FINDINGS.md`: 12 проблем переносимости с файлом и строкой (W01–W12) и список подтверждённо переносимых команд.

## Реально выполненные проверки

Всё на Linux, в detached worktree снимков во временном каталоге:
- K10 `scripts/offline_check.py` из корня репозитория: exit 0 на Python 3.11.15, 3.12.3 и 3.13.14.
- K10 `python3.11 -m unittest discover -s tests -v` из папки пакета: 8 tests OK.
- K10 `offline_check.py` с `PYTHONIOENCODING=cp1251` и `cp1252` при перенаправленном выводе: exit 0.
- K10 worktree, выгруженный через `git -c core.autocrlf=true worktree add`:
  - `selection/*.json` получили 91 CRLF, `data/*.geojson` — 0;
  - `offline_check.py` exit 0, unittest OK.
- Имитация путей Windows через `ntpath` для выражения из `offline_check.py` L254: subset `False`. Значит, тест W01 на Windows упадёт.
- Подсчёт CR во входных blob K10 для K07 (`e91898d`, 10 файлов): 0.

Не запускалось: Windows (его нет в среде), K07 Python- и Node-скрипты, K02-скрипты. Это следующий этап.

## Ограничения

- [SIM-win] — моделирование, не Windows.
- Интернет для проверки не использовался.

## Следующий шаг

1. Запустить в venv во временном каталоге K07 (`graph_check.py`, `build_data.py`, `user_path.cjs`) и K02 (unittest, demo, compare, `git apply --check` на выгрузке autocrlf). Затем написать `RUN_RECIPE.md` с разделением «проверено / прочитано».
