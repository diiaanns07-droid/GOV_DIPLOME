# R01 BUILD — раунд 11 (Астана)

Роль: R01 — BUILD и единственный интегратор общих app-файлов.
Ветка: `claude/affectionate-ride-bol5v8` (origin GOV_DIPLOME). Не прежний BUILD-сеанс.
Исходный HEAD: `834a25f` (= main). PACK_SHA: `9c2f5c0dae14b46c0697a9dfc7f854351bfd570d`.
Прикладной снимок: `b2cb2e0` (CODE_SHA прежнего BUILD `6de3f25`), импорт по путям.
Пути: ui/web_server.py, app.py, web/{index.html,map.js,interface.js,style.css,app.js},
web/govtech/shell.{js,css}, web/civic/shell/, requirements*.txt, run.{bat,sh},
.gitignore, .gitattributes, tests/civic/R01/, research/round-11-results/R01/, этот файл.

## Checkpoint 1 — аудит (PARTIAL, этап 00–25)
- DONE: импорт проверенных путей снимка b2cb2e0 (57 файлов) + .gitattributes из PACK_SHA.
- DONE: исходные проверки на импортированном дереве — pytest 133, web_check 14, node PASS
  (school_case 3621, school_vs_k05 7560). Подробно: research/round-11-results/R01/BASELINE_AUDIT.txt.
- DONE: MATRIX.json — поставок R02–R10 на 15:29Z нет.
- NOT_RUN: браузер, civic-слой (ещё не создан).

## Checkpoint 2 — шлюз civic-v1 и оболочка (PARTIAL, этап 25–75)
- DONE: ui/web_server.py — CivicGateway: явная таблица 18 маршрутов /api/civic/v1, Host для GET/POST,
  Origin/Sec-Fetch-Site для POST, 64 KiB, JSON-only, NaN/Infinity -> 400, 404/405/413/415 в конверте
  {ok:false,error}, 503 module_unavailable для непоставленных модулей, GET /modules (статусы),
  allowlist заголовков сервиса (Set-Cookie, Retry-After). Ленивое создание сервисов, БД .runtime/.
- DONE: web/civic/shell/shell.js — api.request(method,path,body) с X-CSRF-Token из памяти, повтор
  после 403 csrf один раз, режимы Город/Школы/Учебная модель (Город по умолчанию), mount/destroy
  модулей civic-v1 на той же карте. fallback.js — минимальные R01-модули до поставок R03/R04/R06.
- DONE: tests/civic/R01/test_r01_gateway.py 14 PASS; pytest всего 147 PASS; web_check 14 OK.
- DONE: tests/civic/R01/contract_double.py — ТЕСТОВЫЙ ДУБЛЁР (не backend) для e2e-смоука.
- Браузер (дублёр, офлайн-подложка): civic по умолчанию, 1 canvas, 390 без гориз. скролла.

## Checkpoint 3 — первый end-to-end смоук (PARTIAL)
- DONE: tests/civic/R01/browser/p0_flow.cjs — настоящая страница, Chromium 1440x900 и 390x844:
  вход редактора -> черновик -> 404 по прямому ID -> публикация -> 403 без/с поддельным CSRF ->
  409 при устаревшей версии -> перенос срока с причиной -> карточка жителя (исходный/текущий срок,
  история, метка synthetic) -> сообщение -> pending не публичен -> модерация -> публичный ответ,
  XSS-текст как текст -> logout закрывает staff -> F5 (permalink) -> режимы Учебная/Школы/Город.
- Итог на ТЕСТОВОМ ДУБЛЁРЕ: 37 PASS / 0 FAIL / 2 NOT_RUN (подложка/attribution: хост недоступен).
  research/round-11-results/R01/runs/cp3_p0_flow_test_double/. Это не рабочий backend.

## Checkpoint 5 — настоящий backend R02 + R06 встроены (PARTIAL)
- DONE: импорт по путям R02 @92f7aba (ui/civic_store, tests/civic/R02) и R06 @eaa113d
  (ui/civic_feedback, web/civic/feedback, tests/civic/R06). Независимое ревью R02 (workflow):
  блокеров нет. Решения D-01..D-05 в MATRIX.json (один транспорт — CivicGateway R01).
- DONE: P0 HTTP-приёмка на SQLite R02 — 8/8 PASS, включая сохранность после перезапуска.
- DONE: браузер P0 на R02+R06 — 39 PASS / 0 FAIL / 2 NOT_RUN (runs/cp5_p0_flow_real_r02_r06/).
- Полный pytest 440 passed, 2 skipped, 1 deselected (патч-тест R02 к исходному web_server —
  неприменим после интеграции, см. MATRIX R02); web_check 14 OK; node plan/resilience/whatif PASS.

## Checkpoint 6 — R07 сравнение ограничений встроено
- DONE: импорт R07 @22fa413 (engine/civic_scenarios, web/civic/scenarios без demo.html/devserver,
  tests/civic/R07: 51 PASS). Ревью workflow: блокеров нет; в шлюзе — GET-маршруты, guard graph_id,
  OverflowError->422, семафор 2. Кнопка «Сравнить ограничения» -> ящик с пределами данных и ODbL.
- DONE: браузер scenarios_smoke 16 PASS (1440/390): NOT_READY для автомобиля, метка СИНТЕТИКА,
  слои civic-r07-* снимаются при закрытии. runs/cp6_scenarios_r07/.
- DONE: блокировка параллельного входа (R02 M1), права 0600 на БД.

## Checkpoint 7 — R03 карта/карточки и R04 редактор встроены; резервные модули R01 удалены
- DONE: импорт R03 @f73745c (web/civic/map, tests/civic/R03: 17 PASS) и R04 @da46e1c
  (web/civic/editor, tests/civic/R04: 27 PASS). Idempotency-Key из api.request (R04 -> R02).
- DONE: fallback.js удалён (одна реализация на функцию; отсутствующий модуль показывается честно).
- DONE: интегрированный браузерный P0 (R02+R03+R04+R06) — 41 PASS / 0 FAIL / 2 NOT_RUN;
  сценарии R07 — 16 PASS; pytest 491 passed. runs/cp7_p0_integrated_r02_r03_r04_r06/.

## Checkpoint 8 — R09 помощник встроен (шаблонный режим)
- DONE: импорт R09 @f895c30 (agent/civic_assistant, web/civic/assistant, tests/civic/R09: 119 PASS).
  Факты — только публичная проекция R02 и кейсы R07; LLM не настроен (NOT_RUN, без платных вызовов).
  /staff/assistant/extract — только с сессией+CSRF (require_staff R02 в шлюзе).
- DONE: браузер P0 + помощник — 44 PASS / 0 FAIL / 2 NOT_RUN (runs/cp8_p0_integrated_with_r09/).

## Checkpoint 9 — R05 данные Астаны (раздельно real/synthetic)
- DONE: импорт R05 @e477e5d (data/civic/astana, tests/civic/R05: 84 PASS, срез воспроизводим).
  Реальных подтверждённых записей 0 (официальные источники недоступны у R05) — импорт только черновики.
  Демо: synthetic-срез R05 через `seed-demo --package data/civic/astana/demo_synthetic.json`.
- DONE: браузер P0 на демо-срезе R05 — 45 PASS / 0 FAIL / 2 NOT_RUN (runs/cp9_p0_integrated_r05_demo/).

## Checkpoint 10 — переимпорт R02 @3d2b8b9 и R06 @91f2508; ящик модерации по схеме R06
- DONE: pytest 717 passed, 2 skipped; браузер P0 47 PASS / 0 FAIL / 2 NOT_RUN; независимый
  app-e2e R06 против собранного приложения 9/9 PASS (runs/cp10_*).

## Checkpoint 11 — исправления по R10 и найденная взаимоблокировка
- FIXED (R01): взаимоблокировка ленивого запуска feedback/assistant при первом запросе к ним
  (Lock -> RLock), регрессионный тест; R10-D001 (.runtime в .gitignore и .dockerignore — последний
  вне списка путей R01, см. D-11); R10-D002 (graph_id не строка -> 422 до R07).
- DONE: run.sh/run.bat — необязательный CIVIC_DEMO=1 (синтетический срез R05); учётная запись
  редактора только через CLI с getpass.

## Checkpoint 12 — (2026-10-07, после перерыва по лимиту) переимпорт R03 @1bc9c48 и R05 @ee7516f
- DONE: R03 core 23 PASS, R05 120 PASS (срез воспроизводим); удалены правила CSS удалённых
  резервных модулей; подвал панели переносит кнопки (3 кнопки сотрудника на 390 px).
- DONE: браузер P0 48 PASS / 0 FAIL / 2 NOT_RUN (runs/cp12_*).
- Повторно запущено состязательное ревью кода R01 (первый запуск сорвался на лимите сессии).

## Checkpoint 13–14 — найденные дефекты исправлены
- R03-кнопка «Задать вопрос по объекту» была невидима (CSS-специфичность в civic-map.css R03):
  адаптер в shell.css + проверка контраста в смоуке; дефект передан R03 (MATRIX open_defects).
- Состязательное ревью шлюза (воспроизведено, исправлено, тесты): глубоко вложенный JSON,
  HTML-ответы на OPTIONS/TRACE/неизвестные методы и 505/414 на civic-путях, PUT/DELETE без Allow,
  отсутствие X-Frame-Options/CSP frame-ancestors (кликджекинг с соседнего loopback-порта).
- Набор R10 (WIP 13de522) против сборки: 63 PASS / 1 NOT_RUN / 0 FAIL.

## ИТОГ (финальный раздел; SHA и push — в сообщении чата)
- CODE_SHA: см. research/round-11-results/R01/CODE_SHA.txt. Запуск: RUN.txt (порт 8611). Демо: DEMO.txt.
- Встроено в основное приложение (app.py/web, одна карта MapLibre): R02 хранилище/доступ (3d2b8b9),
  R03 карта/карточки (1bc9c48), R04 кабинет редактора (da46e1c, поставка partial), R05 данные
  (ee7516f: реальных 0, демо synthetic), R06 сообщения/модерация (91f2508), R07 сравнение ограничений
  (22fa413), R09 помощник в шаблонном режиме (f895c30). Подробно: MATRIX.json.
- Только в ветках / нет: R08 (ветки нет), R10 (приёмка WIP; финальный VERDICT за R10).
- Проверено на CODE_SHA: run_checks.sh — 11/11 PASS (pytest, web_check, node govtech x5, R03, R04,
  браузер P0 49/0/2 и сценарии 16/0). Кадры 1440x900 и 390x844: screens/final/.
- NOT_RUN: подложка OpenFreeMap/3D (хост закрыт), живой LLM, проверка людьми, реальные данные Астаны.
- Для муниципального пилота нужно: реальные опубликованные источники с правами на использование,
  HTTPS/реверс-прокси и корпоративная авторизация вместо локальных учёток SQLite, резервное
  копирование и журнал аудита в эксплуатации, проверка с сотрудниками и жителями, юридический
  статус сообщений (интеграция с iKOMEK/eOtinish не делалась), R08 с размеченным корпусом.
- Следующий шаг: финальный VERDICT R10 на CODE_SHA; R03 — исправить CSS кнопки (снять адаптер);
  переимпорт R04 после его финальной поставки.
