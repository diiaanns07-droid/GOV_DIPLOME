# K06 round 3 — Корректные метрики автобусов (Астана)

Статус: partial — вычислитель, тесты и расчёт на реальном входе готовы; HTML-отчёт в работе.
Ветка: claude/ecstatic-curie-hzfzn0. Исходный SHA этапа: bf30f7f2c04d2059d99941fd00aba143bf7843cd (K06 next-round).
Задание: origin/codex/research-import-2026-10-05 @ 6602bb86f152d24edcb66f8b45122844323116bc, research/round-3/prompts/K06.txt.
Входы других агентов не использовались.

Сделано: headway_calc.py (stdlib), test_headway_calc.py (11 тестов, ручной пример двух дней), out/headways.json, out/summary.csv.
Проверки: `python3 -m unittest -v test_headway_calc` → 11 OK. Реальный вход: sha256 входов совпадает с research/next-round/K06/source_snapshot/SHA256SUMS_gtfs_data.txt.
Следующий шаг: HTML-отчёт со сравнением методов и поправками.
