# K02 r8 — факты и объяснение выбора city-plan-v2
Роль: K02 (не BUILD). Ветка: claude/clever-mccarthy-pywscu. База: prototypes/city-evidence @ a5b5e2ddbe087c4eab8e947748cdf69dbae84a0d (diff с кандидатом 4e93f30 по папке прототипа пуст; 191 файл извлечён, git blob сверен).
Статус: этапы 1–2 готовы; этап 3 в работе.

Этап 1 (готово): plan_engine.js (validatePlanScenario/evaluatePlan/optimizePlans по CORE_SPEC, полный перебор ≤16), plan_facts.js buildPlanCatalog (факты baseline/manual/mean/minimax/coverage + constraints; kind/unit/scope/hypothetical обязательны; unknown = null). make_fixtures.cjs → fixtures/ (2 реальных среза с synthetic кандидатами + 3 synthetic).
Проверка: node tests/stage1_catalog.cjs --app-root <a5b5e2d prototypes/city-evidence> → all 6 passed (runs/stage1_a5b5e2d.json), Node v22.22.0.
Этап 2 (готово): plan_facts.render/explain — таблица ручной/без объектов/3 оптимума, совпавшие победители одним набором, компромиссы из фактов compare.*, невыполнимость с причинами, изменение бюджета, Парето, блок ограничений; stale_problem и stale_catalog; duplicate_id.
Проверка: node tests/stage2_render.cjs --app-root <a5b5e2d> → all 8 passed (runs/stage2_a5b5e2d.json). Тест R7 сначала нашёл, что разности компромиссов считал рендерер, а не каталог; исправлено (факты compare.*), повторный прогон 8/8.
Следующий шаг: этап 3 (независимый Python-оракул, ожидаемые факты, смена radius/weights/required, demo, HANDOFF).
