Роль: REVIEW K02 (round 6) — приёмка объяснений web/facts.js новой сборки
Ветка: claude/clever-mccarthy-pywscu
Статус: done (приёмка выполнена; T7 — минорный дефект, patch предложен, сборка не изменялась)
Target: claude/beautiful-clarke-sbzomj @ 064ed25368341edaa50289bc29e21dda7bdd9440, prototypes/city-evidence/ (174 файла извлечены, git blob сверен)
Источник теста: research/round-5-results/K02/tests/facts_regression.cjs @ 26fd30cf1ade3f21f554784420d1502b43cce0f2

Итог на 064ed25: 10 PASS / 1 FAIL / 0 SKIP (ACCEPTANCE.json).
- PASS: устаревание при изменении value/unit/coverage (stale_catalog), различимость digest, duplicate_id между секциями, null/0, смена города, NaN/Infinity при buildCatalog, неполный охват в ru/kk.
- FAIL T7: наблюдения kz.astana под ключом shymkent принимаются; web/facts.js:137; repro_t7_city_substitution.cjs; patches/facts_obs_city_check.patch (на копии: 11/11, conformance/smoke/parity pass).
- Тест r5 без изменений: TEST_INCOMPATIBLE (нет TextEncoder в vm-контексте, новое API, переименованные индикаторы; ложный PASS T7 в r5) → адаптер tests/facts_acceptance.cjs, повторный прогон выше.
- Python-эталон vs JS: explain_ref.py перегенерирован в копии == закоммиченный expected_explanations.json; py_js_parity.cjs 7/7 (text, catalog_digest, scenario, facts_used ids).

Проверки (Node v22.22.0, Python 3.11.15): facts_acceptance --app-root и --url (serve.py :8806) — одинаково 10/1; conformance.cjs all passed; smoke.cjs PASS; explain_ref.py + cmp; py_js_parity 7/7.
Не заявляется: точность LLM (StubSelector — заглушка); ручная браузерная проверка.

Следующий шаг: сборщик применяет patches/facts_obs_city_check.patch и повторяет tests/facts_acceptance.cjs --app-root на новом SHA (ожидание 11/11).
