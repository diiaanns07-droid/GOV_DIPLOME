# K10, раунд 9: статус

Задание: `research/round-9/tasks/K10.txt` («Готовые демонстрационные сценарии двух городов»), координация `codex/research-import-2026-10-05` @ `0ab1667`.

- Ветка K10: `claude/save-work-handoff-j7pc05`, начало раунда — `c8df74b`.
- Проверяемая сборка: `claude/beautiful-clarke-sbzomj` @ `d865dd4a124291e10dd0b7bb1d9eada20d34c268`.
- Новой сборки BUILD r9 на момент проверки нет.

| Этап | Состояние | Проверка |
|---|---|---|
| 1. Быстрая регрессия нового SHA по замороженным пакетам r8, хеши и ID источников | готово | `regress.py --sha d865dd4`: EXTRACT, FROZEN_PACKS, SOURCE_HASHES, SOURCE_IDS, R8_SUITE — PASS (15 с); `test_regress.py` 5 OK |
| 2. Конверты `city-resilience-v1` для Шымкента и Астаны + независимый оракул устойчивости | готово | 10 конвертов (Шымкент 6, Астана 4); `check_envelopes.py` на d865dd4: SOURCE, VALID, RECOMPUTE, ORDER, CROSS_R8, INDEX — PASS, IMMUTABLE PASS |
| 3а. Синтетические крайние случаи и неверные конверты | готово | 5 синтетических пакетов с ручным расчётом (HAND PASS), «неизвестная база» — отказ, 2×33 случая неверного ввода; `check_envelopes.py`: 18/18 PASS |
| 3б. Unit-тесты и мутанты оракула устойчивости; предложение `proposals/resilience.js` поверх `plan.js` BUILD | готово | unit 18 OK; мутанты оракула 17/17; предложение на `plan.js` d865dd4: 19/19 пакетов PASS, мутанты 16/16; `regress.py --sha d865dd4` все шаги PASS |
| 3в. Проверка `resilience.js` BUILD на `33cc635` | в работе | BUILD опубликовал r9 (`7077ff7`, `33cc635`) во время работы |
| Импорт demo-пакетов настоящим UI r9 | в работе | — |
