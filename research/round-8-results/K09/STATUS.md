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

Этап 2 — ГОТОВ:
- k09plan/exact.py:
  - полный перебор допустимых масок (≤16 свободных кандидатов, иначе status=too_large, не optimal);
  - after по родительской маске, без гаверсинуса в цикле;
  - три победителя по ключам CORE_SPEC;
  - Парето (cost, weighted_sum_mm) только без unknown, равные пары свёрнуты к меньшим ids;
  - budget_sensitivity [0, B//2, B] без дублей;
  - infeasible с причиной для required;
  - problem_digest не зависит от порядка и не включает selected_ids.
- k09plan/greedy.py:
  - G1 (ключ цели, добавление только при строгом улучшении, ничьи — меньший id);
  - G2 (выгода/стоимость через Fraction, приоритет снижения unknown, сравнение с лучшим одиночным кандидатом).
- k09plan/gap.py: hit, abs, rel; rel = null, если знаменатель exact ≤ 0 или не определён; при unknown_worse числовой разрыв не считается.
- k09plan/suite.py: seeded генератор synthetic точек, кандидатов и стоимостей. Seed — строка, от PYTHONHASHSEED не зависит.
- k09plan/validate.py: strict import и validate.
- k09plan/api.py: адаптер validate_plan_scenario / evaluate_plan / optimize_plans, scenario_digest.
- tests/test_stage2.py (24 теста):
  - exact сверяется с наивным оракулом (своя формула расстояния, itertools.combinations, свои ключи) на 60 seeded задачах: 15 сценариев × 4 набора ограничений по трём срезам. Совпадают победители, метрики, feasible_count и Парето;
  - ручные победители и Парето;
  - ограничения и infeasible;
  - пустой baseline;
  - too_large;
  - чувствительность к бюджету;
  - независимость от порядка и digest;
  - ничьи по id;
  - ловушка, где G1 ≠ exact (разрыв > 0, rel определён);
  - G1/G2 допустимы, детерминированы и не лучше exact (90 прогонов);
  - разрыв при знаменателе 0 и null;
  - валидатор: 16 видов отказа, NaN, 1e999, дубликаты ключей, размер.

Проверки этапа 2: `python3 -m unittest discover -s tests -v` → 36 tests OK.
- Python 3.11.15 stdlib; повтор venv Python 3.12.3 → OK.
- Замер: exact на 16 кандидатах — 0.011 с (max_selected=3, 697 допустимых) и 0.057 с (max_selected=5, 6885 допустимых).
- В двух тестах сначала были ошибочные ожидания (бюджет 400//2 < стоимости required; rel=0.0 при знаменателе 7). Исправлены ожидания, модуль не менялся.

Этап 3 — далее: прогон предрегистрированной сетки со временем, CSV/JSON, RESULTS.md, финальный HANDOFF.
