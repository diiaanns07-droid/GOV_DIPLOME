# K06 round 8 — независимый оракул city-plan-v2 (HANDOFF)

Роль: K06 (не BUILD). Ветка: claude/ecstatic-curie-hzfzn0 (начало раунда от 339fd3935ec4e3b57d8cd743cd02c26aba01c0a7).
Задание: origin/codex/research-import-2026-10-05 @ c3f6c00, research/round-8/tasks/K06.txt, CORE_SPEC.txt.
База прототипа: claude/beautiful-clarke-sbzomj @ a5b5e2ddbe087c4eab8e947748cdf69dbae84a0d (191 файл извлечён, blob id сверены).
В базе НЕТ реализации city-plan-v2 (есть только what-if v1) — интеграция не проверялась.

## Этап 1 — оракул (готово)
- `plan_oracle.py`: parse_strict, validate, evaluate, optimize (полный перебор ≤16, три лексикографических победителя,
  Парето по (cost, weighted_sum_mm)), sensitivity [0, B//2, B], problem_digest. Только stdlib, написан по CORE_SPEC.
- `test_plan_oracle.py`: 13 тестов на синтетическом меридиане (расстояния — замкнутая формула R·Δφ, победители и
  Парето выведены вручную в docstring), строгий JSON, отказы валидации, digest.
- Найдено и исправлено в собственном оракуле: ничья source/hypothetical сравнивалась строкой ("hypothetical" < "source"),
  теперь числовой ранг source=0.

Проверки: `python3 -m unittest -v test_plan_oracle` → 13 OK (Python 3.11.15).

## Следующие этапы
2. Фиксированные seeds маленьких задач с независимыми gold-ответами (budget=0, ties, required conflicts, no baseline/
   candidates, Pareto duplicates, перестановки) — `make_gold.py`, `gold_bruteforce.py`.
3. Метаморфные свойства, benchmark, `compare_candidate.py --candidate-json`.
