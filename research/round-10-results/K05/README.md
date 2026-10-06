# K05 round 10 — школьный кейс: сравнение Сейчас / A / B

| Путь | Что |
|---|---|
| `patch/plan_matrix.patch` | минимальный patch к `web/govtech/core/plan.js` (матрица расстояний, неизвестное ≠ 0) |
| `module/school-compare.js` | адаптер CONTRACT: `validateCase`, `validateMatrix`, `caseDigest`, `compareCase` |
| `ref/school_compare_ref.py`, `ref/test_ref.py` | независимая Python-реализация и проверка по ручным ожиданиям |
| `fixtures/make_hand_cases.py` → `hand_cases.json` | 7 SYNTHETIC ручных кейсов с числами, посчитанными вручную |
| `tests/test_school_compare.cjs`, `run_tests.py` | 966 проверок + тесты BUILD на временной пропатченной копии |
| `cases/make_city_cases.cjs`, `verify_city_cases.py`, `make_explanation.py` | кейсы Шымкента/Астаны, независимая сверка, шаблонное объяснение |
| `out/<city>/` | `case.json`, `matrix.json`, `compare.json`, `facts.json` (каталог фактов для K02/K08), `EXPLANATION.md` |
| `INTEGRATION.md` | шаги для BUILD и решения K05 |

## API `compareCase(case, matrix)`
Вход: `school-access-case-v1` + `{method, policy_id, entries:[{origin_id, target_id, distance_mm, status, method, policy_id,
route_edge_ids, geometry, assumptions}]}` (ровно одна запись на пару точка × школа/кандидат).
Выход: `{schema_version: "school-access-compare-v1", case_id, city_id, case_digest, method, policy_id, threshold_mm,
eligibility_policy, objective, cost_mode, evaluated_sets, plans[], facts[], limitations[]}`;
`plans[]`: `current`, `candidate:<id>`, `auto:contract-lex`, `auto:minimax` — у каждого `selected_candidate_ids`,
`rows[{origin_id, before_mm, after_mm, delta_mm, status, nearest_target_id, nearest_target_kind,
nearest_access_eligibility_unknown, unknown_target_ids, source_ids}]`, `metrics{total_origins, known_count, unknown_count,
partial_count, sum_distance_mm, mean_distance_mm, max_distance_mm, within_threshold_count,
within_threshold_share_of_all_points}`, `cost`, `limitations`. delta = после − до.

## Команды (из корня репозитория)
```
git archive d2ff344c5ec9b9a729ea59df50ec81f981e619de web/govtech tests/govtech | tar -x -C /tmp/d2
python3 research/round-10-results/K05/ref/test_ref.py
python3 research/round-10-results/K05/run_tests.py --app-root /tmp/d2 --keep /tmp/d2p
node research/round-10-results/K05/cases/make_city_cases.cjs /tmp/d2p/web/govtech research/round-10-results/K05/out d2ff344c5ec9b9a729ea59df50ec81f981e619de
python3 research/round-10-results/K05/cases/verify_city_cases.py
python3 research/round-10-results/K05/cases/make_explanation.py
```
