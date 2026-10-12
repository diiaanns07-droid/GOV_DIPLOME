# R02 · раунд 14 · handoff

Задача: R02 — данные: 12 категорий, синтетика v3, инструмент разметки, LLM-скрипты (prompts/R02.txt).
Агент / город: Claude Code (облачная сессия), Астана, Birge.
Обновлено: 2026-10-10, Asia/Almaty (точное время — у коммита).
Статус: partial
Рабочая ветка: claude/round-14-package (эта ветка назначена облачной сессии; другие роли пишут в неё же
только свои пути, поэтому перед push делается fetch + rebase своих локальных коммитов, без force).
Исходный коммит: c75a9ac
Назначенные пути: ml/datasets/, ml/labeling/, web/labeling/, tests/civic/R02/round14/,
research/round-14-results/R02/, этот файл. Старые тесты tests/civic/R02/*.py (раунд 13, другой модуль) не трогаю.

## Что сделано
- [x] 1. web/labeling/ — офлайн-страница разметки (index.html, app.js, core.js, style.css, categories.js из
      categories_v2.json скриптом ml/labeling/gen_categories_js.py). 12 категорий + «Не жалоба», «Сомневаюсь»,
      «Пропустить», «Отменить», ← →, смена языка текста (L), Ctrl+S — экспорт JSONL; клавиши по event.code
      (работают в казахской и русской раскладке); автосохранение и «Продолжить»; режим второго разметчика
      (детерминированный поднабор по ключу, чужие метки не загружаются); ru/kk интерфейс; 375 и 1366 px.
- [ ] 2. ml/labeling/anonymize.py, import_form.py
- [ ] 3. ml/labeling/agreement.py
- [ ] 4. ml/datasets/LABELING_GUIDE_v2.md
- [ ] 5. ml/datasets/synth_v3/ + перевод v1 → v2 + пары перефразов для R04
- [ ] 6. ml/datasets/llm_synth.py, ml/labeling/llm_label.py (проверка на подставном клиенте)
- [ ] 7. ml/datasets/README.md, DELIVERY.json, RUN.txt, INTEGRATION.txt

## Проверки (Linux, Python 3.13, Node 22, Chromium из /opt/pw-browsers через playwright 1.56)
- node --test tests/civic/R02/round14/labeling_core.test.mjs — 12 PASS
- node --test tests/civic/R02/round14/labeling_browser.test.mjs — 7 PASS (file://, без сети, 1366×768 и 375×812)
- python -m pytest tests/civic/R02/round14 — 4 PASS
- Скриншоты: research/round-14-results/R02/screens/ (реально запущенная страница, синтетические фикстуры).

## Следующий шаг
Задача 2: anonymize.py + import_form.py (вывод только в private/).
