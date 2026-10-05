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

## Этап 2 — gold на фиксированных seeds (готово)
- `gold_bruteforce.py` — отдельный решатель без общего кода с оракулом (битовые маски по всем кандидатам, расстояния
  пересчитываются в каждом подмножестве, сортировка всех планов, Парето попарным доминированием).
- `make_gold.py` → `fixtures/gold_cases.json` (seed 820261005, детерминирован): 96 задач —
  12 именованных SYNTHETIC (budget=0, полная/неполная квота, ничьи идентичных кандидатов, кандидат на исходной записи,
  required сверх бюджета / сверх числа, required+excluded, нет baseline, нет baseline при budget=0, нет кандидатов,
  дубликаты Парето, чужая категория в записях) + 24 их перестановки (порядок массивов; переименование ID с сохранением
  порядка) + 24 SYNTHETIC случайных + 12 SYNTHETIC с расходящимися целями (отбор по gold) + 24 на РЕАЛЬНЫХ записях
  Overture из data.js базы a5b5e2d (sha256 bb2a7e66…) с синтетическими точками/кандидатами/стоимостями.
  Итог: 87 optimal, 9 infeasible; в 18 задачах победители целей различаются.
- `test_gold.py`: оракул = gold на всех 96 задачах; перестановки дают тот же результат; problem_digest не зависит от
  порядка и меняется при переименовании ID; именованные ожидания (budget=0 → только пустой план и т.д.).

Проверки: `python3 -m unittest test_plan_oracle test_gold` → 17 OK; повторная генерация fixture побайтно идентична.

## Следующий этап
3. Метаморфные свойства, benchmark, `compare_candidate.py --candidate-json`.
