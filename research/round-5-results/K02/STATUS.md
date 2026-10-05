Роль: REVIEW K02 (round 5) — регрессия JS-объяснений web/facts.js сборки
Ветка: claude/clever-mccarthy-pywscu
Статус: partial (тест и baseline готовы; patch-предложение — следующий коммит)
Вход: BUILD K04 claude/beautiful-clarke-sbzomj @ 0bf27deb8549b325b34a9610402613d745544edb, prototypes/city-evidence/ (извлечено во временную папку, git blob 57 файлов сверен; общая папка не менялась)

Сделано:
- tests/facts_regression.cjs: 11 независимых случаев, вход --app-root <извлечённая prototypes/city-evidence> или --url <serve.py>.
- baseline/app_root_0bf27de.json и baseline/url_0bf27de.json: 2 PASS, 9 FAIL (ожидаемые падения baseline перечислены в expected_baseline_failures).

Проверки (выполнены, Node v22.22.0):
- node tests/conformance.cjs и tests/smoke.cjs сборки → all passed (исходная точка).
- node tests/facts_regression.cjs --app-root … → 9 FAILED of 11.
- то же через --url http://127.0.0.1:8799/ (serve.py сборки) → те же результаты.

Следующий шаг: patch-предложение для web/facts.js (catalogDigest, duplicate_id, проверка city_id и конечности, unit/coverage в факте) и прогон теста на копии с patch.
