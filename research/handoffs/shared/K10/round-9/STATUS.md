Задача / идентификатор: round-9 K10 — готовые демонстрационные сценарии двух городов
Агент / город / сфера: K10 / Шымкент + Астана / city-plan-v2 и city-resilience-v1
Обновлено: 2026-10-06, UTC
Статус: ready_for_review
Рабочая ветка: claude/save-work-handoff-j7pc05
Исходный коммит: c8df74b500dd1d1c1ea39496307062e6c2db1ba3
Назначенные пути: research/round-9-results/K10/, research/handoffs/shared/K10/round-9/

Цель: регрессия нового SHA по замороженным ожиданиям r8; конверты устойчивости по 2+ на город; синтетические крайние случаи с независимым оракулом; проверка импорта настоящей сборкой.

Что реально сделано:
- regress.py (одна команда на SHA), frozen/ (пакеты r8 @ c8df74b, пакет источников K10 @ 602f0c0), test_regress.py.
- k10res: независимый оракул city-resilience-v1, 10 реальных конвертов, 7 синтетических, 2x34 случая ввода.
- Проверки: check_envelopes.py; run_build_resilience.cjs для web/resilience.js BUILD; предложение proposals/resilience.js поверх plan.js; три набора мутантов.

Проверки (фактически):
- python3 research/round-9-results/K10/regress.py --sha d865dd4 -> ok, BUILD_RESILIENCE NOT_RUN (модуля нет).
- python3 research/round-9-results/K10/regress.py --sha 33cc635 -> ok, все 8 шагов PASS: resilience.js 19/19 пакетов, экспорт 10/10, мутанты 18/18.
- unit 18 OK; мутанты оракула 17/17; мутанты предложения 16/16.
Не запускалось: UI устойчивости в браузере — в 33cc635 нет панели (NOT_RUN).

Ограничения: синтетические точки, веса, кандидаты и стоимости; исключение записей условное, не закрытие; Overture неполон; результат относится к двум SHA.
Следующий шаг: при появлении UI-панели устойчивости проверить импорт envelopes/inputs/*.json в браузере; новый SHA прогнать regress.py.
Подробно: research/round-9-results/K10/HANDOFF.md
