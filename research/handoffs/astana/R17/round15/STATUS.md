# R17 · раунд 15 · «Бірге: ведомства вместе» — штаб ведомств и кризисный штаб

Роль: R17
Ветка роли: claude/sweet-euler-5tiu5b (ветка сессии; claude/r15-R17 средой не разрешена)
Начато: 2026-10-15 16:25 по Астане (11:25 UTC)
База: origin/claude/clever-hypatia-q6ts4g @ e91acb6 (код FINAL-4 a4937462 + пакет раунда 15)

## План
1. ui/civic_agencies/: профили служб поверх id R08, таблицы кризисов (миграция в той же SQLite), make_service(db_path), updates(device, since), seed_world (фикстура §5.5 до R02).
2. Табло служб GET agencies/board?days&district (данные R09 по §5.1, до поставки — фикстура).
3. GET agencies/joint и GET agencies/handoffs.
4. Кризисный штаб incidents/*: шаблоны, зона, задачи, обновления ru/kk, закрытие, публичный баннер.
5. web/civic/agencies/: «Штаб ведомств» (Табло · Совместные · Передачи · Кризис), слой «Кризис».
6. Тесты tests/civic/R17/, браузер 1366/1024/375 × ru/kk, сцены 8 и 9.

## Сделано
- Ветка занята, STATUS создан. Продолжение: задача по расписанию trig_0145naAMrgFxY3FPM88AsvHp (каждый час в :25 UTC,
  в эту же сессию) — удалить после 17 окт 23:59 по Астане (18:59 UTC).
- Checkpoint 1 (17:25): ui/civic_agencies/ — profiles.py (20 служб, §5.4), board.py (табло, совместные, передачи —
  чистые функции, метод в шапке), geo.py (районы и дворы OSM для зоны), fixture.py (синтетика §5.1 до R09),
  sources.py (R01 configure → R09 → фикстура), store.py (таблицы agency_* кризисного штаба). Сервиса HTTP ещё нет.

- Checkpoint 2 (17:55): crisis.py, service.py (make_service(db).handle — 11 маршрутов §7), demo.py (пример кризиса
  + seed_world), __init__.py (updates, board_snapshot, agencies_week, active_incidents, incident_marks,
  service_profiles, crisis_link). pytest tests/civic/R17 — 39 PASS.
- Checkpoint 3 (19:00): экран web/civic/agencies/ (agencies.js, agencies.css, crisis-layer.js, index.html):
  Табло (20 служб на одном экране 1366×768 — проверено кадром), Совместные, Передачи, Кризис (карточка, чипы служб
  с прогрессом, задачи, обновления ҚАЗ/РУС, закрытие, форма нового кризиса из шаблона, зона район/дворы);
  слой карты «Кризис» (registerLayer, зона дышит, под значками R07), баннер и карточка жителю зоны.
  Патч для R01 (маршруты, ассеты, теги): research/round-15-results/R17/patches/R01_agencies_routes_assets.patch —
  на стенде наложен локально, в ветку НЕ коммитится (чужие пути).

## Следующий шаг
- Браузерный тест tests/civic/R17/agencies_browser.cjs (1366/1024/375 × ru/kk, поток кризиса, баннер жителя),
  тест шлюза R01 с патчем, INTEGRATION.txt, RUN.txt, DELIVERY.json, кадры в research/round-15-results/R17/screens/.

## Вопросы владельцу
- (пока нет)
