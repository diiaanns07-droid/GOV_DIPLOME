# BUILD раунд 8 — HANDOFF

Ветка `claude/beautiful-clarke-sbzomj`; пути `prototypes/city-evidence/`, `research/round-8-results/BUILD/`. Читать STATUS.md.

Новое: `web/plan.js` (чистый модуль city-plan-v2), `web/plan-ui.js` (UI v2), `tools/plan_oracle.py` (независимый оракул),
`tests/expected_plans.json`, `tests/plan.cjs`, `tests/test_plan_oracle.py`, `tests/plan_smoke.cjs`.
Изменено: `web/app.js` (EXT-хуки для plan-ui, переключатель v1/v2), `web/index.html` (карточки, стили, скрипты), `tools/check_all.py` (шаг plan).
Не менялись: data.js, evidence.js, facts.js, whatif.js, inputs/, корневой сайт, run.bat.

Команды:
```
cd prototypes/city-evidence
python3 tools/check_all.py
node tests/plan.cjs
NODE_PATH="$(npm root -g)" node tests/plan_smoke.cjs
NODE_PATH="$(npm root -g)" node tests/smoke.cjs ; NODE_PATH="$(npm root -g)" node tests/whatif_smoke.cjs
python3 tools/plan_oracle.py      # пересоздать expected_plans.json после смены оракула/фикстур
```
Продолжение: этап 4 — бенчмарк (`tools/bench_plan.cjs`), прогон на чистом worktree, COMPLETION_MATRIX.json, ISSUE_LOG, DEMO_GUIDE.
