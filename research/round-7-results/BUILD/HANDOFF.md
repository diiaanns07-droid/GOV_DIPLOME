# BUILD раунд 7 — HANDOFF

Продолжать в `claude/beautiful-clarke-sbzomj`, папки `prototypes/city-evidence/` и `research/round-7-results/BUILD/`.
Сначала прочитать STATUS.md рядом.

Новые файлы прототипа: `web/whatif.js`, `tools/whatif_ref.py`, `tests/expected_whatif.json`, `tests/whatif.cjs`,
`tests/test_whatif.py`, `tests/whatif_smoke.cjs`. Изменены: `web/app.js` (блок «Если добавить объект» в конце),
`web/index.html` (карточка, стили, `<script src="whatif.js">` перед app.js), `tools/check_all.py` (шаг whatif), `README.md`.

Не менялись: `web/data.js`, `web/evidence.js`, `web/facts.js`, входы `inputs/`, корневой сайт и `run.bat`.

Команды:
```
cd prototypes/city-evidence
python3 tools/check_all.py
NODE_PATH="$(npm root -g)" node tests/smoke.cjs
NODE_PATH="$(npm root -g)" node tests/whatif_smoke.cjs
python3 tools/whatif_ref.py          # пересоздать tests/expected_whatif.json после смены data.js
```
Не коммитить `tests/out/` и `__pycache__`.
