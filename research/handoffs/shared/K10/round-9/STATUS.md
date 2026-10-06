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
- python3 research/round-9-results/K10/regress.py --sha 33cc635 -> ok: resilience.js 19/19 пакетов, экспорт 10/10, мутанты 18/18; UI NOT_RUN (панели нет).
- python3 research/round-9-results/K10/regress.py --sha e1cbc3f -> ok, все 9 шагов PASS, включая импорт 10 конвертов и 68 файлов ввода в настоящем UI (Playwright, 103/103).
- unit 18 OK; мутанты оракула 17/17; мутанты предложения 16/16.
Не запускалось: UI на d865dd4 и 33cc635 — панели нет (NOT_RUN).

Ограничения: синтетические точки, веса, кандидаты и стоимости; исключение записей условное, не закрытие; Overture неполон; результат относится к двум SHA.
Следующий шаг: каждый новый SHA BUILD прогонять командой regress.py --sha <sha>; ожидания не пересоздавать из BUILD.
Подробно: research/round-9-results/K10/HANDOFF.md
