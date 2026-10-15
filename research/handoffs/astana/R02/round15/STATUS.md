# R02 · раунд 15 · STATUS

Роль: R02 — Демо-мир Астаны (одни согласованные данные для всех разделов)
Ветка роли: claude/affectionate-shannon-jm6ws5 (ветка сессии; push в claude/r15-R02 запрещён средой)
Начато: 2026-10-15 16:25 по Астане (11:25 UTC)
База: origin/claude/clever-hypatia-q6ts4g @ e91acb69 (FINAL-4 a4937462 + пакет раунда 15)
restored_from: — (роль начата с нуля, прежней ветки r15 не было)
Продолжение: задача по расписанию trig_01Dhq9GwEwVkapPj6zt97EHb (каждый час, :24 UTC) — удалить после 17 окт 23:59 Астаны.

## ОБРАЗЕЦ ГОТОВ (для R09, R06, R16, R17, R12, R13, R07, R08, R01, R10)
- Схема: `data/civic/astana/demo-world/SCHEMA.md` (birge-demo-world-v1, версия 1.0)
- Образец: `data/civic/astana/demo-world/world_v1.sample.json` (10–23 записи каждого вида, те же id, что в полном мире)
- Полный мир: `data/civic/astana/demo-world/world_v1.json` (719 жалоб, 43 работы, 5 задуманных конфликтов, 32 двора,
  12 идей, 10 инициатив, 3 кризиса, 3 встречи, 10 вопросов, 4 события, сцены step2/7/8/9)
- Помощник: `ml/datasets/demo_world_io.py` → `load_world()`, `materialize(world, now)` (относительное время → ISO),
  `demo_device(id, n)` (синтетический хэш «Я тоже»)
- Как взять свою часть: SCHEMA §2 (кто какой ключ берёт) и §4 (`seed_world(db_path, records, now=None)`).

## План (по research/round-15/prompts/R02.txt)
1. [x] Инвентаризация → research/round-15-results/R02/INVENTORY.md (карта «Нура 80», «Картина дня» 39/163,
   «Обращения» 2 группы — три разных демо-набора)
2. [x] SCHEMA.md + world_v1.sample.json — push 15 окт ~17:00 Астаны
3. [~] Генератор ml/datasets/demo_world.py (seed 15, без сети) → world_v1.json — первая версия готова, калибровка чисел
4. [ ] Проверка ml/datasets/demo_world_check.py + тесты tests/civic/R02/round15/ + EXPECTED.json (числа экранов кодом модулей)
5. [ ] DATASHEET.md
6. [ ] Помощь соседям: INTEGRATION.txt (patch R01: при CIVIC_DEMO_WORLD=1 не подмешивать синтетику R07; образцы seed_world)
7. [ ] LOCAL-14: import_form.py — проверить инструкции

## Сделано
- 11:25 UTC — роль занята, ветка сессии подтянута к пакету (fast-forward до e91acb69).
- 11:30 UTC — стенд FINAL-4 поднят, числа экранов сняты, INVENTORY.md.
- 11:50 UTC — SCHEMA.md, demo_world_io.py, генератор, world_v1.json + sample (все 719 жалоб проходят разбор R09
  record.parse_* и цели находятся картой R12 target_geometry; повторная сборка — тот же sha256).

## Дальше
- demo_world_check.py, EXPECTED.json (R07 heat, R08 summary, R09 inbox на опорном now), тесты, DATASHEET, INTEGRATION.

## Вопросы владельцу
- (пока нет)

## Заметки для соседей
- R09: вкладка «Ждут проверки» в мире будет большой (≈ 500 исправленных без голосов жителей за 60 дней — так и в
  жизни). Предложение: показывать в ней только ремонты последних 14 дней (как «проверено» на карте 7 дней) — решает R09.
- R01: в режиме CIVIC_DEMO_WORLD=1 синтетику R07 (ui.civic_heat.demo_seed) в карту не подмешивать — иначе числа
  снова разъедутся (patch будет в INTEGRATION.txt R02).
