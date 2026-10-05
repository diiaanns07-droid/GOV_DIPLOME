Роль: REVIEW K02 (round 4) — проверка фактов и смены города в verified_explainer K02 r3
Ветка: claude/clever-mccarthy-pywscu
Статус: partial (атаки воспроизведены; patch и тесты исправления — следующий коммит)
Входы:
- свой K02 r3: research/round-3-results/K02/verified_explainer.py @ 24c1750f70d9e444ae551030d116bb6aa8ce5b7b (не изменён)
- K05 claude/optimistic-davinci-1oiqs9 @ d913554bf2617a74d921af260ab8c22743ccb4b5: cases.json, examples/*, k05r3_contract.py → inputs/k05 (побайтно, git blob сверен, inputs/MANIFEST.json)

Сделано:
- attack_cases.py: 10 атак; реальные записи K05 (city_mix, real_zero, missing, incomplete_sample, stale_check, period_mix).
- attack_result_r3.json: 10 из 10 — defect.

Проверки: python research/round-4-results/K02/attack_cases.py r3 (Python 3.11.15, numpy во временном venv) → 10 defect.
Не запускалось: LLM (нет ключа; StubSelector — не LLM), тесты продукта (agent/ не менялся).

Следующий шаг: fixed/verified_explainer.py + fix.patch + test_fix.py; прогон attack_cases.py fixed.
