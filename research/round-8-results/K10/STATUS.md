# K10, раунд 8: статус

Задание: `research/round-8/tasks/K10.txt` («Два реальных среза и сложные сценарии») на `codex/research-import-2026-10-05` @ `c3f6c00`.
Ветка K10: `claude/save-work-handoff-j7pc05`. Целевая сборка: `claude/beautiful-clarke-sbzomj` @ `a5b5e2ddbe087c4eab8e947748cdf69dbae84a0d` (извлечена из git байтами; общий прототип не изменялся).

| Этап | Состояние | Проверка |
|---|---|---|
| 1. Базовые пакеты v2 (Шымкент/Астана × школа/поликлиника) | готово | `tests/check_packs.py` на a5b5e2d: SOURCE/VALID/RECOMPUTE/INDEX/JS = PASS ×4, IMMUTABLE = PASS |
| 2. Сложные задачи (бюджет, required/excluded, конфликты, QA, seed, неверный ввод, синтетика) | готово | `check_packs.py` на a5b5e2d: 31 пакет, все проверки PASS, IMMUTABLE PASS; `test_oracle.py` 23 OK; мутанты 13/13 убиты |
| 3. CLI-предпросмотр, неизменность исходников, итоговый пакет | не начат | — |

Реализации `city-plan-v2` в сборке a5b5e2d нет. Пакеты проверены против её данных и JS-гаверсинуса, но не против её планировщика.
