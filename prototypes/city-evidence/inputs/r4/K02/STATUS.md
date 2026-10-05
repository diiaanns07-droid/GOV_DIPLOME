Роль: REVIEW K02 (round 4) — проверка фактов и смены города в verified_explainer K02 r3
Ветка: claude/clever-mccarthy-pywscu
Статус: done для назначенного объёма (атаки, исправление, patch, тесты); интеграция в agent/ — не в этой задаче
Входы:
- свой K02 r3: research/round-3-results/K02/verified_explainer.py @ 24c1750f70d9e444ae551030d116bb6aa8ce5b7b (не изменён)
- K05 claude/optimistic-davinci-1oiqs9 @ d913554bf2617a74d921af260ab8c22743ccb4b5 → inputs/k05 (побайтно, git blob сверен, inputs/MANIFEST.json)

Сделано:
- attack_cases.py (10 атак, реальные записи K05 обоих городов) → attack_result_r3.json (10 defect), attack_result_fixed.json (11 ok).
- fixed/verified_explainer.py и fix.patch (к файлу r3; применение даёт побайтно fixed).
- test_fix.py (11 тестов). REPORT.md: дефекты, изменения, граница гарантий.

Проверки (выполнены, Python 3.11.15, numpy во временном venv):
- attack_cases.py r3 → 10 defect; attack_cases.py fixed → 11 ok.
- unittest test_fix.py → 11 OK; unittest round-3 test_verified_explainer.py → 16 OK (r3 не тронут).
- git apply --check fix.patch → ok; patched copy == fixed (cmp).
Не запускалось: LLM (StubSelector — не LLM), тесты продукта (agent/ не менялся), k05r3_contract.py.

Ограничения: выбор снимка не делается (отказ при двух); kk-подписи — черновик; районы K05 в подписях как slug; Overture — вторичный неполный источник.

Следующий шаг: перед интеграцией вызывать k05r3_contract.py до catalog_from_k05 и брать названия районов из реестра K03.
