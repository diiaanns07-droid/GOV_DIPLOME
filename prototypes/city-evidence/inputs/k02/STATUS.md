Задача: K02 round 3 — проверяемое объяснение AI по ID фактов
Агент / город: K02 (Claude Code) / shared; каталог построен только из учебной модели Астаны (kind=model)
Обновлено: 2026-10-05, UTC
Статус: ready_for_review (прототип, demo, тесты, сравнение, REPORT); интеграция в agent/ — отдельная задача
Ветка: claude/clever-mccarthy-pywscu
Исходный коммит: c534321b45a6ceac5c9a71b378e05f8165ace2c4
Входы: research/next-round/K02 (своя ветка); K09 claude/save-work-handoff-qho6eq @ 9cc36c3485045a533ba60136c0c9561e4b8acf46 (STATUS.md, 03_thesis_topics.md Т4, 01_bibliography_verification.md §5). Ветки не сливались.

Сделано:
- verified_explainer.py: каталог фактов (ID = город/сценарий/путь), PLAN_SCHEMA, validate_plan, render ru/kk, StubSelector (помечен «not an LLM»).
- demo.py; test_verified_explainer.py (16 тестов); compare_current_filter.py → compare_result.json.
- kk_letters_anchor.patch для agent/evidence.py (не применён).
- REPORT.md: граница гарантий, результаты, место интеграции (agent/advisor.py:253 и 346–350).

Проверки (выполнены):
- unittest test_verified_explainer.py → 16 tests OK (Python 3.11.15, numpy во временном venv).
- demo.py --lang both (base) и --lang ru --event E2 → вывод в REPORT.
- compare_current_filter.py → таблица A/B/C; числа проверяемой части ru/kk все из каталога.
- git apply --check kk_letters_anchor.patch → применяется; поведение проверено на копии файла.
Не запускалось: вызов LLM (ключа нет), pytest/check.py продукта (agent/ не менялся).

Ограничения: kk-подписи — черновик для носителя; уместность выбора фактов моделью не измерена; реальных наблюдений нет (catalog_from_observations проверен на тестовой строке).

Следующий шаг: прогон LLM-селектора по PLAN_SCHEMA на 30 ru + 30 kk вопросах с разметкой людей; затем интеграция по REPORT §5.
