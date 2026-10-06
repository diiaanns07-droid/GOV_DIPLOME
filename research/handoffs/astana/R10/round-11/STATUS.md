# R10 — независимая приёмка, безопасность и дипломные доказательства (раунд 11, Астана)

Задача / идентификатор: round-11 / R10
Агент / город / сфера: Claude Code (облачная сессия) / Астана / приёмка, безопасность, доказательства
Обновлено: 2026-10-06 15:53 UTC
Статус: partial (checkpoint 4)
Рабочая ветка: claude/fervent-dijkstra-1cqrg5
Исходный коммит ветки: 834a25f (= origin/main на момент старта)
PACK_SHA: 9c2f5c0dae14b46c0697a9dfc7f854351bfd570d (origin/codex/govtech-main-interface), все файлы раунда читаются через `git show PACK_SHA:...`
Исходник приложения для сравнения: b2cb2e02c602c166ba6d47c02d8e902e5478c791 (claude/beautiful-clarke-sbzomj), CODE_SHA сборщика 6de3f253d8ec0743450259f9f13722c16cd36099
Назначенные пути: tests/civic/R10/, research/round-11-results/R10/, этот файл.

## Цель и критерий готовности
Независимо установить, работает ли новый городской путь (CONTRACT civic-v1) на exact CODE_SHA R01, и где он ломается. Итог: VERDICT.json (incomplete / local-demo / pilot-candidate), DEFECTS.json, EVIDENCE_INDEX.json, журнал команд, скриншоты, дипломная матрица.

## Что реально сделано (checkpoint 1)
- Прочитаны BRIEF, CONTRACT, ROLES, REVIEW, START_HERE, prompts R01/R02/R06/R07/R10 из PACK_SHA.
- На момент 15:30 UTC ни одна ветка origin не содержит research/round-11-results/* — поставок R01–R09 нет. Интегрированный путь = NOT_RUN (BUILD не готов). В базовом b2cb2e0 civic API отсутствует (ui/web_server.py: только /api/validate…/api/school-ai).
- Независимый валидатор civic-v1 (tests/civic/R10/r10lib/contract.py) — не импортирует продуктовый код.
- HTTP-харнесс без зависимостей: client.py (точные Host/Origin/Content-Type/битые тела, cookie jar, CSRF), target.py (oracle | command | external; изолированный запуск на временной БД и свободном порту, создание редактора через CLI с getpass в pty — пароль не в argv/env/файлах; restart процесса), helpers.py, modrun.py (вызов модуля из pinned checkout в `python -I`, фиксирует module_file и SHA).
- Smoke на fixture: tests/civic/R10/test_fixture_contract.py — fixture байт-в-байт совпадает с PACK (sha256 e2ba1de7…), проходит civic-v1; 22 вручную испорченных варианта отклоняются по ожидаемой причине.
- research/round-11-results/R10/ACCEPTANCE.txt — матрица A01–A10, C01–C09, S01–S14, U01–U10, M01–M04, D01–D02 и независимые ожидания P0.
- Запущен (в фоне) набор HTTP-тестов + эталонный oracle R10 для самопроверки набора и mutation testing.

## Checkpoints 2–4 (15:46–15:52 UTC)
- run_acceptance.py (JSON-доказательства: per-test статус, rollup по ID, SHA цели, журнал процессов), delivery_scan.py (D01).
- browser/probe.cjs проверен на baseline b2cb2e0: 1 canvas, светлый фон, OSM attribution видна, подложка OpenFreeMap заблокирована сетью (в UI есть уведомление) → U06 basemap NOT_RUN; скриншоты research/round-11-results/R10/shots/baseline-b2cb2e0/.
- DEFECTS.json: R10-D001 (medium, R01: .runtime SQLite не в .gitignore/.dockerignore, patch проверен), R10-D002 (low, R07 d77ec45: graph_id list/dict → TypeError → 500, patch проверен 0/210), R10-O001 (наблюдение: публичная история показывает reason публикации, а не правки), R10-I001 (риск интеграции R01↔R02: host_allowed/is_https в context).
- r10lib/standalone_server.py: HTTP-обвязка R10 для R02(+R06) без собственных решений доступа; smoke на R02 6a28de2 + R06 d8aff46 — путь P0 по API работает.
- Поставки на origin (15:47): R02 6a28de2, R03 5275d0a, R04 597b14c, R05 b2c7c8e, R06 d8aff46 (без DELIVERY), R07 d77ec45 READY, R09 cdd2658; R01 341c554 (шлюз, без интеграции R02).
- В фоне: workflow набора HTTP-тестов + oracle + mutation; workflow standalone R06/R09/R05.

## Проверки
- `python3 -I -B -m unittest discover -s tests/civic/R10 -p 'test_fixture_contract.py' -v` → 11 tests OK (exit 0).
- `curl https://tiles.openfreemap.org/styles/liberty` → CONNECT 403 через прокси среды: подложка/3D в этой среде = NOT_RUN, проверяется только fallback.
- Не запускалось: интегрированный продукт (нет поставки R01), модули R02/R06/R07 (не запушены).

## Доказательства и ограничения
- Oracle R10 (tests/civic/R10/r10lib/oracle/) — эталон только для проверки тестов, не продукт и не замена R02.
- Никаких внешних запросов кроме git fetch; секреты/.env не читались.

## Следующий конкретный шаг
1. Принять результаты workflow (тесты/oracle/mutation, standalone R06/R09/R05), прогнать набор на oracle и на R02+R06 standalone, сохранить runs/*.json.
2. R07: собственные tiny graph на d77ec45 (R10_CODE_ROOT=<wt-r07>).
3. Как только R01 опубликует DELIVERY/CODE_SHA с интеграцией R02 — полный набор + браузер на этом SHA.

## Для воспроизведения
- Python 3.13 stdlib; Node 22 + Playwright 1.56 (браузерная часть), Chromium /opt/pw-browsers.

После commit/push актуальный SHA и результат отправки сообщаются в чате.
