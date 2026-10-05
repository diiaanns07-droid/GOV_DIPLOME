# K10, раунд 8: статус

Задание: `research/round-8/tasks/K10.txt` («Два реальных среза и сложные сценарии») на `codex/research-import-2026-10-05` @ `c3f6c00`.
Ветка K10: `claude/save-work-handoff-j7pc05`. Целевая сборка: `claude/beautiful-clarke-sbzomj` @ `a5b5e2ddbe087c4eab8e947748cdf69dbae84a0d` (извлечена из git байтами; общий прототип не изменялся).

| Этап | Состояние | Проверка |
|---|---|---|
| 1. Базовые пакеты v2 (Шымкент/Астана × школа/поликлиника) | готово | `tests/check_packs.py` на a5b5e2d: SOURCE/VALID/RECOMPUTE/INDEX/JS = PASS ×4, IMMUTABLE = PASS |
| 2. Сложные задачи (бюджет, required/excluded, конфликты, QA, seed, неверный ввод, синтетика) | готово | `check_packs.py`: 37 пакетов, все проверки PASS на a5b5e2d и 60f44d9, IMMUTABLE PASS; `test_oracle.py` 23 OK; мутанты оракула 13/13 убиты |
| 3а. Прогон пакетов через `web/plan.js` сборки BUILD `60f44d9` | готово | `run_build_v2.cjs`: 37/37 пакетов без FAIL; мутанты plan.js 15/15 обнаружены |
| 3б. CLI-предпросмотр, итоговый пакет | в работе | — |

В a5b5e2d реализации `city-plan-v2` нет. Она появилась в BUILD `claude/beautiful-clarke-sbzomj` @ `60f44d9` (`web/plan.js`). Проверены только функции модуля без DOM. Импорт файла и интерфейс не проверялись.
С этого шага `source_snapshot` в пакетах имеет формат `plan.js` (`city-plan-v2`/`haversine-mm-v1`). Прежний формат v1 сохранён в `provenance.whatif_v1_snapshot_same_slice`. Расстояния не изменились.
