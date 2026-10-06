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

Следующий шаг: ревью и импорт поставок R02/R03/R04 (первые checkpoint появились 15:38–15:45Z).
