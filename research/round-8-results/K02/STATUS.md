# K02 r8 — факты и объяснение выбора city-plan-v2
Роль: K02 (не BUILD). Ветка: claude/clever-mccarthy-pywscu. База: prototypes/city-evidence @ a5b5e2ddbe087c4eab8e947748cdf69dbae84a0d (diff с кандидатом 4e93f30 по папке прототипа пуст; 191 файл извлечён, git blob сверен).
Статус: этап 1 готов; этапы 2–3 в работе.

Этап 1 (готово): plan_engine.js (validatePlanScenario/evaluatePlan/optimizePlans по CORE_SPEC, полный перебор ≤16), plan_facts.js buildPlanCatalog (факты baseline/manual/mean/minimax/coverage + constraints; kind/unit/scope/hypothetical обязательны; unknown = null). make_fixtures.cjs → fixtures/ (2 реальных среза с synthetic кандидатами + 3 synthetic).
Проверка: node tests/stage1_catalog.cjs --app-root <a5b5e2d prototypes/city-evidence> → all 6 passed (runs/stage1_a5b5e2d.json), Node v22.22.0.
Следующий шаг: этап 2 (рендерер ru/kk, stale problem digest, duplicate IDs).
