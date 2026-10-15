# R17 · раунд 15 · «Бірге: ведомства вместе» — штаб ведомств и кризисный штаб

Роль: R17
Ветка роли: claude/sweet-euler-5tiu5b (ветка сессии; claude/r15-R17 средой не разрешена)
Начато: 2026-10-15 16:25 по Астане (11:25 UTC)
База: origin/claude/clever-hypatia-q6ts4g @ e91acb6 (код FINAL-4 a4937462 + пакет раунда 15)

## Каждый круг
- Каждый круг: сначала читать AMENDMENTS.md из ветки пакета:
  `git fetch origin claude/clever-hypatia-q6ts4g && git show origin/claude/clever-hypatia-q6ts4g:research/round-15/AMENDMENTS.md`
  (координатор дописывает туда поправки; где поправка расходится с промптом или VISUAL_BRIEF — права поправка).
- Прочитанные поправки: П1 (15 окт 17:05, «Без ИИ-слопа») — применена 15 окт ~17:25, см. «Сделано».

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
- Checkpoint 1 (16:36, 30449d15): ui/civic_agencies/ — profiles.py (20 служб, §5.4), board.py (табло, совместные, передачи —
  чистые функции, метод в шапке), geo.py (районы и дворы OSM для зоны), fixture.py (синтетика §5.1 до R09),
  sources.py (R01 configure → R09 → фикстура), store.py (таблицы agency_* кризисного штаба). Сервиса HTTP ещё нет.

- Checkpoint 2 (16:41, 61558bd3): crisis.py, service.py (make_service(db).handle — 11 маршрутов §7), demo.py (пример кризиса
  + seed_world), __init__.py (updates, board_snapshot, agencies_week, active_incidents, incident_marks,
  service_profiles, crisis_link). pytest tests/civic/R17 — 39 PASS.
- Checkpoint 3 (17:00, e5b834f9): экран web/civic/agencies/ (agencies.js, agencies.css, crisis-layer.js, index.html):
  Табло (20 служб на одном экране 1366×768 — проверено кадром), Совместные, Передачи, Кризис (карточка, чипы служб
  с прогрессом, задачи, обновления ҚАЗ/РУС, закрытие, форма нового кризиса из шаблона, зона район/дворы);
  слой карты «Кризис» (registerLayer, зона дышит, под значками R07), баннер и карточка жителю зоны.
  Патч для R01 (маршруты, ассеты, теги): research/round-15-results/R17/patches/R01_agencies_routes_assets.patch —
  на стенде наложен локально, в ветку НЕ коммитится (чужие пути).

- Checkpoint 4 (~17:30): поправка П1 «Без ИИ-слопа» применена — пустые состояния: одна монохромная иконка ui-kit 48 px
  + текст + одна кнопка (вместо линейных иллюстраций ill-*); значки служб в табло монохромные (цвет — только у
  просрочки и сроков); пульс зоны кризиса оставлен (П1 п. 5 называет его «вау от данных»). Подмодуль расчёта
  переименован board.py → metrics.py: R03 ищет функцию ui.civic_agencies.board(days, district) — теперь это функция;
  добавлены board() и list_incidents() для R03. seed_world понимает формат демо-мира R02 (время объектами
  {"ago_hours": …}, повторяющиеся id задач, закрытые без closed_at) и сбрасывает демо-кризисы при каждом запуске.
  Сверка с EXPECTED.json R02 (world_v1 @ d8af32a0): по 20 службам совпадает, кроме open у совместной (считаю по части
  службы) и overdue (нужен due_at от засева R09) — объяснено в INTEGRATION §5.
  Тесты: pytest tests/civic/R17 — 42 PASS; браузер tests/civic/R17/agencies_browser.cjs — 104/104 PASS
  (1366/1024/375 × ru/kk, поток кризиса, житель зоны, reduced motion). Кадры: research/round-15-results/R17/screens/ (27).

- Поставка D1 для B1: research/round-15-results/R17/DELIVERY.json — code_sha 7530089671bc5976236bff5c52edd54b97faa1a8,
  RUN.txt, INTEGRATION.txt (patch R01: patches/R01_agencies_routes_assets.patch, ложится на e91acb69).

- Checkpoint 5 (~18:40): подстройка под оболочку R01 раунда 15 и схему R11 IA_ROUND15 §5.4/§5.12/§7: путь раздела
  #agencies/<вкладка>, #agencies/crisis/<id> (setPath, navigate), раздел crisis — публичная карточка (#crisis/<id>),
  вкладка «Календарь работ» с модулем R12 (embedded), точка-пульс у «Кризиса», «Кто за что отвечает» → #services,
  строки «Совместных» → «Обращения» с фильтром, кнопки «Отправить обновление жителям», «Закрыть с итогом»,
  «Хроника недели» (если есть хроника R07), баннер в BirgeShell.alertSlot() одной строкой; CSRF во всех запросах
  сотрудника (шлюз R01 требует его и в GET табло); фильтры периода/района — в строке KPI (5 вкладок на ҚАЗ в одну
  строку, 20 служб на 1366 × 768). Проверено: на ветке R01 @ 4dd0c8e6 с моим модулем — браузер 104/104; на FINAL-4 +
  patch — 108/108; pytest 42. Найдены стыки R01↔R12 (календарь 401) — INTEGRATION §9.

## Следующий шаг
- Ждать B1 (16 окт 14:00); до неё — круги по соседям: R09 v2.1, R16 (дворы устройства), R04 (moderate), R08/R13
  (кнопка «Открыть кризисный штаб» → crisis_link), R11 (ключи agencies.*), R01 (patch/сборка). Затем круг по соседям: R09 v2.1 (функции чтения, фильтр
  «Обращений» по службе), R01 (наложил ли patch), R11 (ключи, меню), R16 (имя функции дворов устройства), R04
  (moderate), R08/R13 (кнопка «Открыть кризисный штаб»). Проверять на каждом круге.

## Вопросы владельцу
- (пока нет)
