Задача / идентификатор: round-9 K10 — готовые демонстрационные сценарии двух городов
Агент / город / сфера: K10 / Шымкент + Астана / city-plan-v2 и city-resilience-v1
Обновлено: 2026-10-06, UTC
Статус: partial
Рабочая ветка: claude/save-work-handoff-j7pc05
Исходный коммит: c8df74b500dd1d1c1ea39496307062e6c2db1ba3
Назначенные пути: research/round-9-results/K10/, research/handoffs/shared/K10/round-9/

Цель: регрессия нового SHA по замороженным ожиданиям r8; конверты устойчивости по 2+ на город; синтетические крайние случаи с независимым оракулом.

Что сделано: этап 1 — regress.py, frozen/, tests/test_regress.py (d865dd4 PASS); этап 2 — k10res (оракул устойчивости, генератор), 10 конвертов, check_envelopes 10/10 PASS.
Проверки: python3 research/round-9-results/K10/regress.py --sha d865dd4 -> ok=true (15 с); test_regress 5 OK.
Не запускалось: интеграция city-resilience-v1 с BUILD — сборки r9 нет.
Подробно: research/round-9-results/K10/STATUS.md и HANDOFF.md.
Следующий шаг: этап 3 (синтетические крайние случаи, тесты, итог).
