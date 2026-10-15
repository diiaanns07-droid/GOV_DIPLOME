# R02 · раунд 15 · STATUS

Роль: R02 — Демо-мир Астаны (одни согласованные данные для всех разделов)
Ветка роли: claude/affectionate-shannon-jm6ws5 (ветка сессии; push в claude/r15-R02 запрещён средой)
Начато: 2026-10-15 16:25 по Астане (11:25 UTC)
База: origin/claude/clever-hypatia-q6ts4g @ e91acb69 (FINAL-4 a4937462 + пакет раунда 15)
restored_from: — (роль начата с нуля, прежней ветки r15 не было)
Продолжение: задача по расписанию trig_01Dhq9GwEwVkapPj6zt97EHb (каждый час, :24 UTC) — удалить после 17 окт 23:59 Астаны.

**Каждый круг: сначала читать AMENDMENTS.md из ветки пакета**
  git fetch origin claude/clever-hypatia-q6ts4g
  git show origin/claude/clever-hypatia-q6ts4g:research/round-15/AMENDMENTS.md
  (где поправка расходится с промптом R02, COMMON, IDEA или VISUAL_BRIEF — права поправка)

## Поправки
- П1 (15 окт 17:05, «Без ИИ-слопа») — применена 15 окт ~17:20 Астаны: у R02 нет экранов демо; в мире нет фото и
  картинок (photos_after и report.photo_ids всегда [], правило в SCHEMA §0 и в demo_world_check, тест);
  web/labeling проверен — нет эмодзи, градиентов, свечения и картинок; R16 — строка «Фото появится после дела» (INTEGRATION §8).

## ОБРАЗЕЦ ГОТОВ (для R09, R06, R16, R17, R12, R13, R07, R08, R01, R10)
- Схема: `data/civic/astana/demo-world/SCHEMA.md` (birge-demo-world-v1, версия 1.0)
- Образец: `data/civic/astana/demo-world/world_v1.sample.json` (10–23 записи каждого вида, те же id, что в полном мире)
- Полный мир: `data/civic/astana/demo-world/world_v1.json` (719 жалоб, 43 работы, 5 задуманных конфликтов, 32 двора,
  12 идей, 10 инициатив, 3 кризиса, 3 встречи, 10 вопросов, 4 события, сцены step2/7/8/9)
- Помощник: `ml/datasets/demo_world_io.py` → `load_world()`, `materialize(world, now)` (относительное время → ISO),
  `demo_device(id, n)` (синтетический хэш «Я тоже»)
- Как взять свою часть: SCHEMA §2 (кто какой ключ берёт) и §4 (`seed_world(db_path, records, now=None)`).

## План (по research/round-15/prompts/R02.txt)
1. [x] Инвентаризация → research/round-15-results/R02/INVENTORY.md
2. [x] SCHEMA.md + world_v1.sample.json — push 15 окт ~16:50 Астаны (схема 1.0.1: события started_at/ended_at)
3. [x] Генератор ml/datasets/demo_world.py (seed 15, без сети) → world_v1.json (743 жалобы, Нура 36 %)
4. [x] demo_world_check.py (0 ошибок), EXPECTED.json (числа кодом R07/R08/R09), 24 теста tests/civic/R02/round15
5. [ ] DATASHEET.md
6. [~] Соседи: INTEGRATION.txt (patch R01 проверен на стенде: 14/14 чисел совпали), заметки R07/R09/R10/R12/R13/R16/R17
7. [ ] LOCAL-14: проверить инструкции import_form.py
8. [ ] DELIVERY.json, RUN.txt; кадры стенда в режиме мира (карта «Нура · N», «Обращения», «Картина дня»)

## Сделано
- 11:25 UTC — роль занята, ветка сессии подтянута к пакету (fast-forward до e91acb69).
- 11:30 UTC — стенд FINAL-4 поднят, числа экранов сняты, INVENTORY.md.
- 11:50 UTC — SCHEMA.md, demo_world_io.py, генератор, world_v1.json + sample (push 0b375fc3), черновой PR
  https://github.com/diiaanns07-droid/GOV_DIPLOME/pull/1 (база — ветка пакета, не сливать).
- 11:56 UTC — проверка мира, EXPECTED.json, помощник засева R09, 24 теста (push d8af32a0).
- 12:10 UTC — тест tests/civic/R02/test_r02_schema.py принимает таблицу R06 civic_notify_reads (миграция 10; проверено и
  на коде R06); patch R01 для CIVIC_DEMO_WORLD=1 (research/round-15-results/R02/patches/R01_demo_world.patch) проверен
  на стенде: числа стенда = числам мира 14/14 (stand_numbers_world.json); INTEGRATION.txt.

## Дальше
- DATASHEET.md, RUN.txt, DELIVERY.json; кадры стенда в режиме мира (1366, ru/kk).
- На каждом круге: find_branches.py → проверить seed_world соседей (R09, R06, R16, R17, R13, R07) и R12/R10 на мире;
  поля по запросам — в SCHEMA и генератор (версия схемы).

## Вопросы владельцу
- (пока нет)

## Заметки для соседей (подробно — research/round-15-results/R02/INTEGRATION.txt)
- ВСЕМ: время в мире относительное; R01 отдаёт в seed_world уже материализованный мир (ISO): materialize(load_world(), now).
  Кто читает файл сам (R12 works_calendar.load_world, R10 consistency.world_numbers) — тоже через materialize (§6, §10).
- R01: patch §1 готов и проверен (карта без синтетики R07 в режиме мира + засев всех модулей одним now).
- R09: готовый seed_world — ml/datasets/demo_world_seed.seed_world (reset демо-записей, настоящие не трогает).
  «Ждут проверки» в мире 419 — предложение: показывать ремонты последних 14 дней.
- R08/R09/R17/R10/R11: «Просрочено» у R08 (срок исправления) и у R09 (срок ответа) — разные числа (Нура 7 и 1);
  предложение подписей и сверки — INTEGRATION §3.
- R06: тест R02 schema больше не падает на civic_notify_reads (C.1 вашего INTEGRATION применён в ветке R02).
