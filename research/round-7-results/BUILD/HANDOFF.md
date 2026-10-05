# BUILD раунд 7 — HANDOFF

Продолжать в `claude/beautiful-clarke-sbzomj`; пути: `prototypes/city-evidence/`, `research/round-7-results/BUILD/`.
Проверенный код — 4e93f30 (см. STATUS.md). Здесь же: DEMO_GUIDE.txt, IMPLEMENTED_SPEC.json, SOURCE_HASHES.json, results/.

Новые файлы прототипа: `web/whatif.js`, `tools/whatif_ref.py`, `tests/expected_whatif.json`, `tests/whatif.cjs`,
`tests/test_whatif.py`, `tests/whatif_smoke.cjs`. Изменены: `web/app.js` (блок «Если добавить объект» в конце),
`web/index.html` (карточка, стили, `<script src="whatif.js">` перед app.js), `tools/check_all.py` (шаг whatif), `README.md`.
Не менялись: `web/data.js`, `web/evidence.js`, `web/facts.js`, `inputs/`, корневой сайт и `run.bat`.

Команды:
```
cd prototypes/city-evidence
python3 tools/check_all.py
NODE_PATH="$(npm root -g)" node tests/smoke.cjs
NODE_PATH="$(npm root -g)" node tests/whatif_smoke.cjs
python3 tools/whatif_ref.py          # пересоздать tests/expected_whatif.json после смены data.js
```
Если data.js изменится, отпечаток среза изменится и старые сохранённые сценарии будут отклонены (так и задумано).

Возможные следующие шаги (не начаты): проверка на Windows; программа чтения экрана; при желании — видимая
в UI проверка случая «нет записей категории» на учебном срезе (не подменяя реальные данные).
Не коммитить `tests/out/` и `__pycache__`.
