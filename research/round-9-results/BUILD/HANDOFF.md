# BUILD раунд 9 — HANDOFF
Ветка `claude/beautiful-clarke-sbzomj`; пути `prototypes/city-evidence/`, `research/round-9-results/BUILD/`, `research/handoffs/shared/BUILD/round-9/STATUS.md`.
Читать STATUS.md и ISSUE_LOG.md.

Команды:
```
cd prototypes/city-evidence
python3 tools/check_all.py
node tests/plan.cjs ; node tests/whatif.cjs
NODE_PATH="$(npm root -g)" node tests/plan_keyboard.cjs
NODE_PATH="$(npm root -g)" node tests/plan_smoke.cjs ; NODE_PATH="$(npm root -g)" node tests/whatif_smoke.cjs ; NODE_PATH="$(npm root -g)" node tests/smoke.cjs
cd ../.. && node research/round-9-results/BUILD/adapters/r8_independent.cjs research/round-9-results/BUILD/r8_independent_result.json
```
Продолжение: этап 2 — `web/resilience.js` поверх `plan.js` (`internal.*`, `KEYS`, `cmpIds`), оракул `tools/resilience_oracle.py`.
