# BUILD — HANDOFF (после этапа 1)

Работает: демо `prototypes/city-evidence/` — `cd prototypes/city-evidence && python3 serve.py` → http://127.0.0.1:8765/ (или открыть `web/index.html`).
Проверка: `NODE_PATH=$(npm root -g) node tests/smoke.cjs` (9/9 PASS на момент записи).

Незавершённые файлы: `web/facts.js` — заглушка (`window.CITY_FACTS = null`), app.js уже умеет его использовать (districtOf, renderExplanation, provenanceNotes).

Следующий шаг (этап 2): скопировать по SHA из research/round-4/snapshots.json входы K03 (boundary_registry.json, boundary_validator.py, geo_common.py), K05 (k05r3_contract.py, schema v1.1), K02 (verified_explainer.py, demo.py, тесты), K08 (AUDIT/verdicts) через tools/copy_inputs.py (EXTRA), прочитать код, собрать facts.js генератором в tools/, добавить тесты: неизвестный fact ID, чужой город, устаревший scenario, null vs 0, повреждённый/отсутствующий вход.

Продолжение другим агентом: только после прямого переназначения пользователем; читать эту ветку и коммит, работать в своей ветке, без reset/force push.
