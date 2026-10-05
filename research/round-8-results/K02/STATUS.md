# K02 r8 — факты и объяснение выбора city-plan-v2
Роль: K02 (не BUILD). Ветка: claude/clever-mccarthy-pywscu. База: prototypes/city-evidence @ a5b5e2ddbe087c4eab8e947748cdf69dbae84a0d (diff с кандидатом 4e93f30 по папке прототипа пуст; 191 файл извлечён, git blob сверен).
Статус: этапы 1–3 готовы (ready_for_review). Интеграция в BUILD не проверялась: модуль ещё не в сборке.

Этап 1 (готово): plan_engine.js (validatePlanScenario/evaluatePlan/optimizePlans по CORE_SPEC, полный перебор ≤16), plan_facts.js buildPlanCatalog (факты baseline/manual/mean/minimax/coverage + constraints; kind/unit/scope/hypothetical обязательны; unknown = null). make_fixtures.cjs → fixtures/ (2 реальных среза с synthetic кандидатами + 3 synthetic).
Проверка: node tests/stage1_catalog.cjs --app-root <a5b5e2d prototypes/city-evidence> → all 6 passed (runs/stage1_a5b5e2d.json), Node v22.22.0.
Этап 2 (готово): plan_facts.render/explain — таблица ручной/без объектов/3 оптимума, совпавшие победители одним набором, компромиссы из фактов compare.*, невыполнимость с причинами, изменение бюджета, Парето, блок ограничений; stale_problem и stale_catalog; duplicate_id.
Проверка: node tests/stage2_render.cjs --app-root <a5b5e2d> → all 8 passed (runs/stage2_a5b5e2d.json). Тест R7 сначала нашёл, что разности компромиссов считал рендерер, а не каталог; исправлено (факты compare.*), повторный прогон 8/8.
Этап 3 (готово): oracle/plan_oracle.py (независимый Python) → expected/ для 14 вариантов (radius/weights/required/excluded/budget/граница радиуса); tests/stage3_oracle.cjs; demo.cjs → examples/; HANDOFF.md (API, команды, фикстуры, ограничения).
Проверки (Node v22.22.0, Python 3.11.15, все на a5b5e2d): stage1 6/6, stage2 8/8, stage3 15/15 (runs/*.json); мутации движка (ключ minimax, floor вместо round, < вместо <= для радиуса) ловятся stage3; conformance.cjs и whatif.cjs сборки — pass.
SKIP: интеграция в BUILD/UI/Worker (не в сборке); LLM (заглушка).
Следующий шаг: BUILD подключает модули и повторяет тесты этапов 1–3 на новом SHA (см. HANDOFF.md).
