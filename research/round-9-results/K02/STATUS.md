# K02 r9 — объяснения по фактам (REVIEW/модуль, не BUILD)
Ветка: claude/clever-mccarthy-pywscu. Проверяемая сборка: prototypes/city-evidence @ d865dd4a124291e10dd0b7bb1d9eada20d34c268 (claude/beautiful-clarke-sbzomj; diff с 3e1302a пуст; 199 файлов извлечены, git blob сверен, MANIFEST во временной копии).
Входы: свои r8 фикстуры и ожидания Python-оракула @ eedbf9d → inputs/r8 (git blob сверен, inputs/MANIFEST.json).

## Этап 1 — готово
tests/common.cjs (адаптер r8 фикстур → makeContext/validatePlanScenario сборки), tests/s1_build_explain.cjs.
`node tests/s1_build_explain.cjs --app-root <d865dd4>` → 20 PASS, 2 FAIL (runs/s1_d865dd4.json):
- PASS B0 ×14: optimizePlans/evaluatePlan/sensitivity сборки = независимый Python-оракул K02 r8 (radius/weights/required/excluded/budget/граница радиуса).
- PASS: числа объяснения из сценария/результата; неизвестное = «нет данных», не 0; совпавшие стратегии подписаны; старый digest → stale_explanation; infeasible объяснён; reportHtml экранирует и пишет «нет данных».
- FAIL E5: explainPlans принимает результат ДРУГОЙ задачи (result.problem_digest ≠ problemDigest(sc)), если вызывающий пересчитал explanationDigest. web/plan.js:338–340 (digest только по переданным объектам).
- FAIL E6: то же для оценки ручного плана другого selected_ids.
  Уровень: публичный API; UI защищён (plan-ui.js:443 сверяет problem_digest и сам вычисляет manual).
- Patch-предложение patches/explain_binds_facts.patch (plan.js + правка tests/plan.cjs:193, который сам передавал manual для [] при другом selected_ids). На копии: s1 22/22, plan.cjs/conformance/whatif/smoke/plan_smoke — pass; применяется к чистой d865dd4 и воспроизводит копию (cmp). НЕ применён к сборке — не FIXED.
Следующий шаг: этап 2 (renderer фактов устойчивости manual/nominal/robust).
