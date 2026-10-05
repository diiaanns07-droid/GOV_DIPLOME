# K11 round 7 — STATUS

Задание: `research/round-7/tasks/K11.txt` («Запуск и инструкция сценария»). Спецификация: `research/round-7/FEATURE_SPEC.txt` (`codex/research-import-2026-10-05` @ `7927fa8`).
Ветка: `claude/save-work-handoff-fmjw6r`. Предыдущий результат: `3eaf08e` (раунд 6). Он же test_source для smoke.
Обновлено: 2026-10-05, UTC.
Статус: **partial**. Этап 1 готов: проверен запуск кандидата. Модуль сценария, fixtures и инструкция — следующий этап.

Проверяемый кандидат: `claude/beautiful-clarke-sbzomj` @ `c58a3b2b175cf978ad785fef7f88d8fd9b1338f2`, `prototypes/city-evidence/`. `git diff b3e4dc4 c58a3b2 -- prototypes/city-evidence/` пуст. На момент проверки `c58a3b2` — вершина ветки. Извлечено 185 файлов, id blob совпали.

## Этап 1: запуск кандидата (Linux)

- `k11_demo_smoke.py --app-root <c58a3b2> --browser` (без изменений из `3eaf08e`): **19 pass, 0 fail**, 3 modeled_pass (M1–M3), 2 info, 1 not_run (W1 Windows). Exit 0.
- `k11r6_launch_extra.py --app-root <c58a3b2>`: X1 (`8765 --open`), X2 (занятый порт), X3 (нет `data.js`) — все pass.
- Свой `tests/smoke.cjs` сборщика в чистом worktree `c58a3b2`: exit 0, 24 PASS, 0 FAIL. `git status --untracked-files=all` пуст: вывод идёт в `tests/out`, а его игнорирует `tests/.gitignore` (`out/`). Дефект I13 раунда 6 сборщик закрыл своим способом.
- **Функции «Если добавить объект» в `c58a3b2` нет**: `git grep -i 'whatif|city-whatif|proposed_object|control_point'` по `prototypes/city-evidence/` пуст. Интеграцию не заявляю.

Отчёты: `runs/launch_smoke_c58a3b2.*`, `runs/launch_extra_c58a3b2.json`, `runs/build_own_smoke_clean_worktree_c58a3b2.txt`.

## Ограничения

- Windows не запускался. M1–M3 — моделирование на Linux.

## Следующий шаг

1. Изолированный модуль `city-whatif-v1` для сохранения и открытия файлов сценария: UTF-8, кириллица и казахский в ID и именах файлов, повторное открытие из другого каталога. Плюс fixtures, тесты и инструкция Windows/Linux.
