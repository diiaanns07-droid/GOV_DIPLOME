# BUILD — HANDOFF (после этапа 2)

Работает: `cd prototypes/city-evidence && python3 serve.py` → http://127.0.0.1:8765/ (или открыть `web/index.html`).
Проверки: `python3 -m unittest discover -s tests -v`; `node tests/conformance.cjs`; `NODE_PATH=$(npm root -g) node tests/smoke.cjs`.

Незавершённых файлов нет. Этапы 1 и 2 BUILD.txt выполнены в объёме STATUS.md.

Возможные следующие шаги (не начаты):
1. Ручной просмотр владельцем в Windows (run из корня не трогали; `python serve.py` должен работать — не проверено).
2. Подключение реального LLM-селектора: заменить `StubSelector` объектом с тем же `select(view)`; `validatePlan` остаётся границей доверия.
3. Маршрутный режим — только после проверки прав прохода (`graph_check.py` K07) и явного решения.

Продолжение другим агентом: только после прямого переназначения пользователем; читать эту ветку и коммит, работать в своей ветке, без reset/force push.
