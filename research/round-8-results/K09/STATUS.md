Задача: K09 round-8 — эксперимент для диплома на оптимизации: жадный выбор против точного поиска, city-plan-v2.
Источник задания: research/round-8/tasks/K09.txt, CORE_SPEC.txt (codex/research-import-2026-10-05 @ c3f6c00).
Ветка: claude/save-work-handoff-qho6eq; snapshot раунда 9118515.
База прототипа: a5b5e2ddbe087c4eab8e947748cdf69dbae84a0d (= кандидат 4e93f30 по дереву). Кода city-plan-v2 в базе нет; интеграция не утверждается.
T1 (research/round-3-results/K09) не изменялся.

Этап 1 — ГОТОВ:
- EXPERIMENT_DESIGN.md: вопрос, условия, алгоритмы, метрики разрыва, ограничения.
- config/experiment_config.json: предрегистрация факторов и seeds 0–9 до прогона.
- k09plan/metric.py: haversine-mm-v1 (clamp, floor(d*1000+0.5)), Problem с предвычислением, метрики плана, rows (source/hypothetical), ключи трёх целей.
- k09plan/data.py: срез data.js из Git по SHA, проверка sha256.
- fixtures/hand_meridian.json (synthetic): ожидаемые мм вычислены независимой формулой R·|Δφ|.
- tests/test_stage1_metric.py.

Проверки: `python3 -m unittest discover -s tests -v` в research/round-8-results/K09 → 12 tests OK (Python 3.11.15, только stdlib).

Этап 2 — далее: exact, G1, G2, Парето, чувствительность к бюджету, seeded suite, разрыв, тесты.
