# BUILD раунд 8 — HANDOFF

Ветка `claude/beautiful-clarke-sbzomj`; пути `prototypes/city-evidence/`, `research/round-8-results/BUILD/`.
Проверенный кандидат (код): **3e1302a**. Все 4 этапа BUILD.txt выполнены — см. STATUS.md, COMPLETION_MATRIX.json, ISSUE_LOG.md.

Модули: `web/plan.js` (чистый city-plan-v2: validate / evaluate / createSearch / optimizePlans / sensitivity / export / import /
explain / reportHtml; Node и браузер), `web/plan-ui.js` (UI v2 через EXT-хуки `web/app.js`), `tools/plan_oracle.py` (независимый оракул),
`tools/bench_plan.cjs` (замер). v1: `web/whatif.js` (в раунде 8 — ID любого алфавита в NFC и отказ для не-UTF-8).

Команды:
```
cd prototypes/city-evidence
python3 serve.py 8765 --open                       # запуск
python3 tools/check_all.py                         # 18 шагов, включая plan и whatif
node tests/plan.cjs ; node tests/whatif.cjs
NODE_PATH="$(npm root -g)" node tests/plan_smoke.cjs
NODE_PATH="$(npm root -g)" node tests/whatif_smoke.cjs ; NODE_PATH="$(npm root -g)" node tests/smoke.cjs
NODE_PATH="$(npm root -g)" node tools/bench_plan.cjs out.json
python3 tools/plan_oracle.py                       # пересоздать tests/expected_plans.json (после смены data.js/фикстур)
node research/round-8-results/BUILD/adapters/r7_independent_fixtures.cjs   # из корня репозитория
```
Возможные следующие шаги: проверка на Windows и экранным диктором; просмотр и запуск остальных r7-пакетов;
если нужно — явная миграция v1→v2 с обязательным вводом стоимостей. Не коммитить `tests/out/` и `__pycache__`.
