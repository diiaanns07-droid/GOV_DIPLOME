# R02 · раунд 14 · handoff

Задача: R02 — данные: 12 категорий, синтетика v3, инструмент разметки, LLM-скрипты (prompts/R02.txt).
Агент / город: Claude Code (облачная сессия), Астана, Birge.
Обновлено: 2026-10-10, Asia/Almaty (точное время — у коммита).
Статус: partial
Рабочая ветка: claude/r14-R02 (по новому правилу COMMON.txt; создана от claude/round-14-package @ 887ef4b).
Первый checkpoint 887ef4b до появления правила ушёл и в claude/round-14-package — там только пути R02;
решение об откате — за координатором. Дальше пушу только в claude/r14-R02.
Исходный коммит: c75a9ac (база пакета), затем 7ff639a (пакет с правилом о ветках)
Назначенные пути: ml/datasets/, ml/labeling/, web/labeling/, tests/civic/R02/round14/,
research/round-14-results/R02/, этот файл. Старые тесты tests/civic/R02/*.py (раунд 13, другой модуль) не трогаю.

## Что сделано
- [x] 1. web/labeling/ — офлайн-страница разметки (index.html, app.js, core.js, style.css, categories.js из
      categories_v2.json скриптом ml/labeling/gen_categories_js.py). 12 категорий + «Не жалоба», «Сомневаюсь»,
      «Пропустить», «Отменить», ← →, смена языка текста (L), Ctrl+S — экспорт JSONL; клавиши по event.code
      (работают в казахской и русской раскладке); автосохранение и «Продолжить»; режим второго разметчика
      (детерминированный поднабор по ключу, чужие метки не загружаются); ru/kk интерфейс; 375 и 1366 px.
- [x] 2. ml/labeling/anonymize.py (телефон, email, ИИН, ссылки, карты/длинные номера, госномера, дом/квартира/подъезд
      ru+kk, улица+номер, имена по явным шаблонам; отчёт только из чисел) и import_form.py (согласие, обезличивание,
      повторы, язык форма/авто, дата без времени, стабильный id f-…, перемешивание, вывод только в private/ +
      private/.gitignore '*', файл .review.txt для ручной проверки). text_utils.py — общие функции.
- [x] 3. ml/labeling/agreement.py — Cohen's kappa, бутстрэп-ДИ, по категориям, macro-F1 B относительно A, матрица,
      частые несогласия, Markdown/JSON; тексты в отчёте только с --with-texts и только в private/.
- [x] 4. ml/datasets/LABELING_GUIDE_v2.md — 12 категорий, 6 примеров ru+kk на каждую, сводная таблица 25 спорных случаев,
      «Не жалоба» и «Сомневаюсь». Казахские примеры ждут проверки владельцем.
- [x] 5. ml/datasets/synth_v3/ (slots.py, templates.py — 221 шаблон, build.py, seed 20261011):
      corpus_v3.jsonl — 4260 сообщений (train 2659 / val 945 / test 656),
      все 12 категорий в каждом split, ru/kk/mixed, 9 стилей, 1067 трудных случаев; обезличено; split по шаблонам.
      paraphrase_pairs_v3.jsonl — 781 пар для R04. ml/datasets/v1_in_v2/ — v1 (2725) → v2: label (уточнённая)
      и label_table (строго v1_to_v2), 393 строки отличаются.
- [x] 6. ml/labeling/llm_client.py (stdlib, OpenAI/NVIDIA, ключ только из окружения, кэш, повторы 429/5xx с
      Retry-After, бюджет --max-usd до отправки), ml/labeling/guide.py (правила для промптов из LABELING_GUIDE_v2),
      ml/datasets/llm_synth.py (корпус llm_v1, сетка категория×стиль×язык, --dry-run, --mock),
      ml/labeling/llm_label.py (строго одна метка, повтор при болтливом ответе, повторное обезличивание,
      --confirm-external). Проверено только на подставном транспорте — реальный API в облаке NOT_RUN.
- [ ] 7. ml/datasets/README.md, DELIVERY.json, RUN.txt, INTEGRATION.txt

## Проверки (Linux, Python 3.13, Node 22, Chromium из /opt/pw-browsers через playwright 1.56)
- node --test tests/civic/R02/round14/labeling_core.test.mjs — 12 PASS
- node --test tests/civic/R02/round14/labeling_browser.test.mjs — 7 PASS (file://, без сети, 1366×768 и 375×812)
- python -m pytest tests/civic/R02/round14 — 89 PASS (+ LLM-клиент/синтетика/разметчик на подставном транспорте)
- сквозная проверка: экспорт страницы (первый и второй разметчик) → agreement.py — PASS (в labeling_browser.test.mjs)
- Скриншоты: research/round-14-results/R02/screens/ (реально запущенная страница, синтетические фикстуры).

## Следующий шаг
Задача 7: ml/datasets/README.md, DELIVERY.json, RUN.txt (команды ноутбука + стоимость), INTEGRATION.txt
(private/ в .gitignore для R01, корпус для R03, пары для R04, ключи i18n для R11).
