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

## ОБРАЗЕЦ И МИР ГОТОВЫ (для R09, R06, R16, R17, R12, R13, R07, R08, R01, R10)
- Схема: `data/civic/astana/demo-world/SCHEMA.md` (birge-demo-world-v1, версия **1.1**: + `day_at`, итог и точка встречи,
  `closed_at` кризиса; 1.0.1 — события `started_at/ended_at`)
- Полный мир: `data/civic/astana/demo-world/world_v1.json` — 743 жалобы (Нура 36 %, 1171 человек с «Я тоже»),
  39 работ + 4 отключения, 5 задуманных конфликтов, 32 двора, 12 идей, 10 инициатив, 3 кризиса, 3 встречи, 17 вопросов,
  4 события, сцены step2/7/8/9. Образец — `world_v1.sample.json` (замкнут по ссылкам). Числа экранов — `EXPECTED.json`.
- Помощник: `ml/datasets/demo_world_io.py` → `load_world()`, `materialize(world, now)` (относительное время → ISO).
- ГЛАВНОЕ для R01: модулям передавать МАТЕРИАЛИЗОВАННЫЙ мир (seed_world R09 на сыром мире — 743 invalid). Patch R01 так и делает.

## План (по research/round-15/prompts/R02.txt)
1. [x] Инвентаризация → research/round-15-results/R02/INVENTORY.md
2. [x] SCHEMA.md + world_v1.sample.json — push 15 окт ~16:50 Астаны (схема 1.0.1)
3. [x] Генератор ml/datasets/demo_world.py (seed 15, без сети) → world_v1.json (743 жалобы, Нура 36 %)
4. [x] demo_world_check.py (0 ошибок), EXPECTED.json (числа кодом R07/R08/R09), тесты 25 + все R02 361 passed
5. [x] DATASHEET.md
6. [x] INTEGRATION.txt (patch R01 проверен на стенде: 14/14), DELIVERY.json, RUN.txt
7. [~] Соседи на каждом круге: seed_world R09/R06/R16/R17/R13/R07, правки R12/R10 (materialize), «Просрочено» R08/R09
8. [x] LOCAL-14: инструкции import_form.py актуальны (CLI отвечает, тесты импорта PASS), команды — RUN.txt п. 5

## Сделано
- 11:25 UTC — роль занята, ветка сессии подтянута к пакету (fast-forward до e91acb69).
- 11:30 UTC — стенд FINAL-4 поднят, числа экранов сняты, INVENTORY.md.
- 11:50 UTC — SCHEMA.md, demo_world_io.py, генератор, world_v1.json + sample (push 0b375fc3), черновой PR
  https://github.com/diiaanns07-droid/GOV_DIPLOME/pull/1 (база — ветка пакета, не сливать).
- 11:56 UTC — проверка мира, EXPECTED.json, помощник засева R09, 24 теста (push d8af32a0).
- 12:10 UTC — тест tests/civic/R02/test_r02_schema.py принимает таблицу R06 civic_notify_reads (миграция 10; проверено и
  на коде R06); patch R01 для CIVIC_DEMO_WORLD=1 (research/round-15-results/R02/patches/R01_demo_world.patch) проверен
  на стенде: числа стенда = числам мира 14/14 (stand_numbers_world.json); INTEGRATION.txt.
- 12:15 UTC — финальная калибровка мира (пульс рассказывает буран, 3 «решения акима», A1/A2 R10 сходятся),
  DATASHEET.md, RUN.txt; поправка П1 применена; влит пакет 2d329b2c; DELIVERY.json (code_sha 4b67f69b).
- 12:20–12:35 UTC — стыки с соседями на их ветках (временные worktree, их пути не коммитил):
  R12 — с patch R12_works_calendar_world находит ровно 5 задуманных конфликтов (пара Айтеке Би / Култегин для
  параллельных перекрытий); R10 — patch R10_consistency_world (154 / 78); R16 — 42 записи (просьба reset);
  R17 — 3 + reset 3; R13 — 17 (встречи 18:30, итог; схема 1.1 day_at); R07 — 3 отметки (просьба читать events,
  closed_at); R09 — их world_seed на материализованном мире = EXPECTED, на сыром — 743 invalid → patch R09 и
  patch R01: R09 integration.seed_world с живым хранилищем и reset=True; перезапуск стенда — reset 743, 14/14.

- 12:30–12:50 UTC (круг по расписанию) — AMENDMENTS: новых поправок нет. PR: CI нет, отзывов нет, описание обновлено.
  По просьбам соседей: R04 — совместные жалобы переделаны под route() (743/743 совпадают, тест стыка); R17 — «открыто»
  у совместной по части службы в EXPECTED; R13 — время суток встреч и итог (схема 1.1) уже сделаны прошлым кругом.
  Живой стенд на новом мире — 14/14; R09 world_seed на новом мире = EXPECTED.

- 12:50 UTC — R13: общие вопросы (17 вопросов в мире); стыки R13 (24 записи, reset 24) и R16 (reset 42) перепроверены.

- 13:25–14:00 UTC (круг по расписанию) — AMENDMENTS: новых поправок нет (только П1). R01 собрал B0 (c9069723) и сам
  сделал засев мира (взял мир 907bfc9d). Стенды (облако, research/round-15-results/R02/stand_numbers_builds.json):
  B0 + мир — 14/14, перезапуск 14/14; «B1-симуляция» (B0 + backend соседей с голов веток) — 14/14, перезапуск 14/14,
  табло R17 19/19 служб, совместные 18/8, передачи 14, сцены 2/7/8/9 на месте.
  Найдено и исправлено/передано:
  · мой тест test_expected_file_is_current упал бы в B1 (R09 r15: «Ждут проверки» = 14 дней, 159 вместо 424) →
    EXPECTED.json хранит отпечатки кода R07/R08/R09, блок чужого кода сверяется только при том же коде (3d8db494);
  · R01: при перезапуске строка «civic-world: R09 0, R17 0, R13 0» (reset не считается) и R06 не получает reset=True →
    patches/R01_world_reset.patch (tests/civic/R01 359 passed);
  · R07: отметки «Хроники» при повторном засеве остаются на старом времени, жалобы R09 уезжают (через 2 дня — «Буран»
    на 2 дня раньше всплеска) → patches/R07_world_marks_reseed.patch (tests/civic/R07 203 passed);
  · R06 seed_world на мире: 55 (39 работ + 4 отключения + 12 идей), повтор/reset, идеи и даты работ = миру.

- 14:25–14:50 UTC (круг по расписанию) — AMENDMENTS: новых нет. R01, R06, R13, R16, R17 с прошлого круга не коммитили;
  R07 (f42f4347) patch повторного засева пока не взял. Модерация R04 (e796acd1, строже к номерам) по 4277 текстам мира —
  0 находок. Просьба R09 (их INTEGRATION F2) выполнена: EXPECTED.json пересчитан кодом R09 97342bdf
  (inbox.waiting_check_days = 14; город {21, 72, 159, 5, 5}, Нура {8, 24, 54, 2, 0}, групп 88), поле code_note —
  откуда код; R09 test_r02_world_counts_match_expected — PASS; тесты R02 362 passed.

## Дальше
- Каждый круг: AMENDMENTS.md → find_branches.py → у соседей: seed_world на мире (R09, R06, R16, R17, R13, R07),
  R12 works_calendar.load_world и R10 consistency.world_numbers через materialize; ответы на просьбы о полях.
- К B1 (16 окт 14:00 Астаны): стенд R02 с ветками соседей (локально, без коммита чужих путей) → обновить
  consistency_table в DELIVERY.json.
- Проверять, взяли ли R01 и R07 свои patch (R01_world_reset, R07_world_marks_reseed); по B1 — те же проверки на сборке.

## Вопросы владельцу
- (пока нет)

## Заметки для соседей (подробно — research/round-15-results/R02/INTEGRATION.txt)
- ВСЕМ: время в мире относительное; R01 отдаёт в seed_world уже материализованный мир (ISO): materialize(load_world(), now).
  Кто читает файл сам (R12 works_calendar.load_world, R10 consistency.world_numbers) — patch в research/round-15-results/
  R02/patches/ (R12_works_calendar_world.patch, R10_consistency_world.patch; проверены на их ветках).
- R01: засев мира в вашей ветке (B0) проверен — 14/14 и после перезапуска. Просьба взять patches/R01_world_reset.patch
  (110 строк с тестами): строка civic-world считает reset (сейчас перезапуск пишет «R09 0, R17 0, R13 0»), seed_world с
  параметром reset получает reset=True (R06 по умолчанию False). patches/R01_demo_world.patch — только для голого FINAL-4.
- R07: просьба взять patches/R07_world_marks_reseed.patch — отметки «Хроники» едут с миром при повторном засеве, как
  жалобы R09 (INTEGRATION §4, проверка: засев 16 и 18 окт на одной базе).
- R09: ваш world_seed на материализованном мире = EXPECTED; в сборке R01 (db_path без хранилища) — 743 сразу на экранах;
  EXPECTED.json пересчитан вашим кодом 97342bdf с inbox.waiting_check_days = 14 (ваш тест сверки — PASS);
  «Ждут проверки» 14 дней принято (город 159 на опорный момент). Сырой мир ваш seed_world понимает сам — patch-страховка не нужна.
- R16, R13: reset демо-записей при повторном засеве уже сделали (R16 c5836427 — reset 42; R13 2a89f178 — reset 24).
- R13: 9 общих вопросов «Вопроса акиму» добавлены (8 опубликованных, 2 с ответом, 1 на проверке) — вкладки 6 / 8 / 2.
- R07: events и closed_at — сделано (52dee9a4, 6 отметок); осталось — reset отметок при повторном засеве (выше).
- R06: seed_world проверен на мире (55, reset 55, идеи и работы = миру); reset=True передаст R01 (patch R01_world_reset).
- R08/R09/R17/R10/R11: «Просрочено» у R08 (срок исправления) и у R09 (срок ответа) — разные числа (Нура 14 и 0 на опорный
  момент); предложение подписей и сверки — INTEGRATION §3.
- R06: тест R02 schema принимает civic_notify_reads (C.1 вашего INTEGRATION применён в ветке R02).
