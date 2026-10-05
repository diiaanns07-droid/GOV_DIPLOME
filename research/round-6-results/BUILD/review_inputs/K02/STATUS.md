Роль: REVIEW K02 (round 5) — регрессия JS-объяснений web/facts.js сборки
Ветка: claude/clever-mccarthy-pywscu
Статус: done для назначенного объёма (тест, baseline, patch-предложение проверено на копии). Сборка НЕ исправлена (FIXED не заявляется).
Вход: BUILD K04 claude/beautiful-clarke-sbzomj @ 0bf27deb8549b325b34a9610402613d745544edb, prototypes/city-evidence/ (git blob 57 файлов сверен; общая папка не менялась)

Сделано:
- tests/facts_regression.cjs (11 случаев; --app-root / --url; --json).
- baseline/app_root_0bf27de.json, baseline/url_0bf27de.json: 2 PASS / 9 FAIL (expected_baseline_failures).
- patches/facts_catalog_digest.patch (web/facts.js + tests/conformance.cjs) и baseline/proposal_check_0bf27de_plus_patch.json: 11/11 PASS на копии.
- REPORT.md: таблица, ожидаемое изменение API catalog_digest, команды для сборщика.

Проверки (Node v22.22.0): conformance.cjs и smoke.cjs baseline → pass; facts_regression baseline --app-root и --url → 9 FAIL (одинаково); копия+patch: node --check, conformance → all passed, smoke → exit 0, facts_regression → 11/11; git apply к чистой копии == проверенной копии (cmp).
Не запускалось: ручная браузерная проверка stale_catalog после смены фильтра; LLM.

Следующий шаг: сборщик применяет patch, перезапускает conformance.cjs и facts_regression.cjs --app-root на новом SHA; при желании перегенерировать эталон текста от K02 r4.
