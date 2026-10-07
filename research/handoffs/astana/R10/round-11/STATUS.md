# R10 — независимая приёмка, безопасность и дипломные доказательства (раунд 11, Астана)

Задача / идентификатор: round-11 / R10
Агент / город / сфера: Claude Code (облачная сессия) / Астана / приёмка, безопасность, доказательства
Обновлено: 2026-10-07 05:15 UTC
Статус: ready_for_review (вердикт выдан на кандидатной сборке R01)
Рабочая ветка: claude/fervent-dijkstra-1cqrg5
Исходный коммит ветки: 834a25f (= origin/main)
PACK_SHA: 9c2f5c0dae14b46c0697a9dfc7f854351bfd570d
Проверенный CODE_SHA: 8c6add919efa9ed965cb05a57626744fed750da1 — голова ветки R01 claude/affectionate-ride-bol5v8 (checkpoint 11, 06.10 16:34 UTC). R01 не опубликовал DELIVERY.json/CODE_SHA/RUN.txt; другой SHA этим вердиктом не покрыт.
Назначенные пути: tests/civic/R10/, research/round-11-results/R10/, этот файл.

## Вердикт
**local-demo** (research/round-11-results/R10/VERDICT.json). Не pilot-candidate из-за: R10-D009 (high, невидимая кнопка «Задать вопрос по объекту», патч проверен), R10-D010 (medium, панель конфликта 409 под липкой панелью действий), нет CODE_SHA/RUN.txt R01, подложка/3D не наблюдаемы (прокси), 0 реальных записей. Не production-ready.

## Что сделано (DONE)
- Матрица приёмки ACCEPTANCE.txt (A01–A10, C01–C09, S01–S14, U01–U10, M01–M04, D01–D02) и независимые ожидания P0.
- Набор тестов без зависимостей: test_api_objects/feedback/security (52 теста), test_fixture_contract, test_scenarios_tinygraph (собственные tiny graph R10, ожидания вручную + перебор простых путей), standalone/ для R05/R06/R09, integrated_checks.py, browser/probe.cjs и browser/walkthrough.cjs.
- Самопроверка набора: oracle R10 (только для тестов) 69 PASS / 0 FAIL; mutation score 28/28; два состязательных ревью (ложный FAIL / ложный PASS) — 22 исправления, каждое доказано отдельным внедрённым дефектом.
- R01 8c6add9 (изолированная копия, временная БД, редакторы через CLI продукта с getpass в pty): HTTP 82/82 PASS; браузер 1440x900 и 390x844 — 48 PASS / 5 FAIL / 1 NOT_RUN после скептической проверки; проба UI; помощник через /assistant — даты прослеживаются, бюджет «нет данных», метка template.
- Модули: R07 d77ec45 19/19; R06 (в сборке) 23/23; R09 f895c30 16/22 (3 low дефекта); R05 e477e5d 16/20 (1 low дефект).
- DEFECTS.json: 12 дефектов (5 исправлены и перепроверены, 7 открыты: 1 high, 1 medium, 5 low), 9 наблюдений, 2 опровергнутых кандидата. Патчи: R01-gitignore-runtime (применён R01), R07-graph-id-type (закрыт шлюзом R01), R03-cta-contrast (контраст 1.00 → 14.79 в Chromium).
- DIPLOMA_MATRIX.md H1–H8 с фактическими результатами/«не измерено»; USER_TEST_SCRIPT.md (люди не участвовали); CONTRACT_AMBIGUITIES.md (12 пунктов для contract_delta); EVIDENCE_INDEX.json (генерируется скриптом, sha256 каждого файла); COMMANDS.md.

## Не запускалось (NOT_RUN)
Реальная подложка и 3D (OpenFreeMap: CONNECT 403); живой LLM; R08 (нет поставки); официальные страницы лицензий (403); истечение сессии по времени (нужен контроль часов сервера); исследование с людьми.

## Для воспроизведения
- `git worktree add --detach <tmp>/wt-r01 8c6add9` (без .env, БД во временном каталоге).
- HTTP: `R10_TARGET=command R10_CODE_ROOT=<wt-r01> R10_START_CMD='{python} -E -s -B app.py --port {port} --civic-db {db}' R10_CREATE_EDITOR_CMD='{python} -E -s -B -m ui.civic_store --db {db} create-editor {username}' python3 -I -B tests/civic/R10/run_acceptance.py --label r01-<sha7> --out research/round-11-results/R10/runs/r01-<sha7>.json`
- Браузер: `python3 -I -B tests/civic/R10/browser/run_walkthrough.py` (см. --help; Playwright из /opt/node22/lib/node_modules, Chromium /opt/pw-browsers).
- Самопроверка: `python3 -I -B tests/civic/R10/mutation_selftest.py`; индекс: `python3 -I -B tests/civic/R10/build_evidence_index.py`.
- `python3 -I` для модулей; `-E -s -B` для app.py (ему нужен каталог скрипта в sys.path).

## Следующий конкретный шаг
1. Когда R01 применит исправления D009/D010 и опубликует CODE_SHA — перезапустить две команды выше на этом SHA и обновить VERDICT.json.

## Известные зависимости
R01 (CODE_SHA/RUN.txt, исправления), R03 (CSS кнопки), R04 (липкая панель редактора), R09 (D003–D005), R05 (D008), R08 (нет поставки).

После commit/push актуальный SHA и результат отправки сообщаются в чате.
