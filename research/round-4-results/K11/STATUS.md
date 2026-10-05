# K11 round 4 — STATUS

Роль: **REVIEW**, задание `research/round-4/review/K11.txt` («Проверка инструкции запуска»).
Ветка: `claude/save-work-handoff-fmjw6r`. Предыдущие результаты: `bbf3eee` (раунд 3), `bc0daed` (первый этап раунда 4).
Обновлено: 2026-10-05, UTC.
Статус: **done** в объёме «список точных проблем + рецепт; Linux проверен запуском, Windows смоделирован». Настоящий Windows не запускался, это ограничение, а не выполненная проверка.

Входы (`origin/codex/research-import-2026-10-05` @ `cadba4d`, `research/round-4/snapshots.json`):
- K07 `claude/save-work-handoff-ku3ej3` @ `6778deda6d3f3a7f27698f651c1b0046d2a9aae9`;
- K10 `claude/save-work-handoff-j7pc05` @ `ea703f1ddd3a411430a981164a78a7dda64ec909` (входы K07: `e91898d`);
- K02 `claude/clever-mccarthy-pywscu` @ `24c1750f70d9e444ae551030d116bb6aa8ce5b7b`.

Назначенный путь: `research/round-4-results/K11/`. `prototypes/city-evidence/`, `run.bat`, основной сайт и чужие ветки не менялись.

## Сделано

- `FINDINGS.md`: W01–W14 с файлом и строкой, меткой проверки и последствием для Windows, плюс таблица подтверждённо переносимого.
- `RUN_RECIPE.md`: команды для Linux (выполнены) и Windows (только прочитаны), с ожидаемыми отличиями.
- `CHECK_LOG.md`: 22 реально выполненные команды и их результаты.

## Главное

1. **K10 (W01):** на Windows ожидается 1 падение в unittest, `test_only_manifest_files_opened`. Причина: `os.path.relpath` возвращает пути с `\`, а манифест хранит их через `/`. Сам `offline_check.py` переносим.
2. **K07 (W02, W03, W05):** `run_all.sh` только для bash. В `user_path.cjs` URL собран как `file://C:\...` вместо `pathToFileURL`. Выходы на Windows будут записаны с CRLF. Python-шаги при этом переносимы. Колёса для Windows есть на Python 3.12 и 3.13.
3. **K02 (W07, W08):** рецепт `/tmp/k02/bin` только для Linux. `demo.py --lang both` падает при выводе в cp1251 на казахской букве, а в cp1252 падает и русский вывод. Лечение: `PYTHONIOENCODING=utf-8`.
4. Опровергнуто: W09 (патч K02 применяется и при `core.autocrlf=true`).
5. Для всех ОС: W11 (селекция K10 требует незакоммиченное сырьё раунда 2), W13 (скриншот K07 недетерминирован), W14 (numpy не закреплён).

## Реально выполненные проверки

См. `CHECK_LOG.md`. Кратко:
- K10: `offline_check` на Python 3.11/3.12/3.13 и unittest 8 OK; то же при cp1251/cp1252 и на выгрузке с autocrlf; `ntpath` подтверждает W01.
- K07: `run_all.sh` exit 0, 34/34. Выходы побайтно равны коммиту, в том числе на выгрузке с autocrlf.
- K02: 16 tests OK, `demo`/`compare`/`git apply` exit 0. Имитация cp1251/cp1252 воспроизвела W08.
- Наличие колёс `win_amd64` проверено через `pip download`.

## Ограничения

- Windows не запускался. [SIM-win] моделирует только кодировки (`PYTHONIOENCODING`), байты выгрузки (`core.autocrlf=true`) и строковую семантику путей (`ntpath`, `path.win32`).
- Поведение Chromium с URL вида `file://C:\` на Windows не проверено.
- Изменения `newline` и результатов на numpy 2.5.3 не проверены.
- Сеть: только PyPI и origin.

## Следующий шаг

1. Сессия с настоящим Windows выполняет раздел «Windows» из `RUN_RECIPE.md` и записывает фактические exit-коды. Ожидается: K10 unittest — 1 падение W01; K02 без `PYTHONIOENCODING` — `UnicodeEncodeError` при перенаправлении. Исправления (`relpath(...).replace(os.sep, "/")`, `pathToFileURL`, `newline="\n"`, `.bat`-аналог `run_all.sh`) — задача владельцев K10/K07/K02 или сборщика, не REVIEW.

## Воспроизведение

```bash
git fetch origin codex/research-import-2026-10-05 claude/save-work-handoff-ku3ej3 claude/save-work-handoff-j7pc05 claude/clever-mccarthy-pywscu
git worktree add --detach /tmp/wt-k10 ea703f1ddd3a411430a981164a78a7dda64ec909
git -c core.autocrlf=true worktree add --detach /tmp/wt-k10-crlf ea703f1ddd3a411430a981164a78a7dda64ec909
# дальше команды из CHECK_LOG.md; после проверки: git worktree remove <путь>
```
