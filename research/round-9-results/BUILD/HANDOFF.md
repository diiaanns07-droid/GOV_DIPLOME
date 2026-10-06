# BUILD раунд 9 — HANDOFF
Ветка `claude/beautiful-clarke-sbzomj`; пути `prototypes/city-evidence/`, `research/round-9-results/BUILD/`, `research/handoffs/shared/BUILD/round-9/STATUS.md`.
Проверенный код — **e82214e**. Все 4 этапа BUILD.txt выполнены: см. STATUS.md, ISSUE_LOG.md, COMPLETION_MATRIX.json, INTEGRATED_PACKAGES.json, ADAPTER_API.md.

Модули: `web/resilience.js` (чистый city-resilience-v1 поверх `plan.js`), `web/resilience-ui.js` (карточка в режиме v2),
`tools/resilience_oracle.py` (независимый оракул), `tools/bench_resilience.cjs`. v2: `plan.js` валидирует все публичные входы; `plan-ui.js` — фокус, `defer/flush`, `loadScenario`.
`serve.py` — явные MIME, сообщение о занятом порте.

Команды:
```
cd prototypes/city-evidence
python3 serve.py 8765 --open
python3 tools/check_all.py                                    # 20 шагов
node tests/resilience.cjs ; node tests/plan.cjs ; node tests/whatif.cjs
NODE_PATH="$(npm root -g)" node tests/resilience_smoke.cjs
NODE_PATH="$(npm root -g)" node tests/plan_keyboard.cjs ; NODE_PATH="$(npm root -g)" node tests/plan_smoke.cjs
NODE_PATH="$(npm root -g)" node tests/whatif_smoke.cjs ; NODE_PATH="$(npm root -g)" node tests/smoke.cjs
NODE_PATH="$(npm root -g)" node tools/bench_resilience.cjs out.json
python3 tools/resilience_oracle.py          # пересоздать tests/expected_resilience.json (после смены data.js / фикстур)
cd ../.. && node research/round-9-results/BUILD/adapters/r8_independent.cjs out.json   # K06 + K10 r8
```
Следующие шаги (не начаты): проверка на настоящем Windows и экранным диктором; запуск r9-пакетов коллег через `ADAPTER_API.md`,
когда их SHA будут закреплены. Не коммитить `tests/out/` и `__pycache__`.
