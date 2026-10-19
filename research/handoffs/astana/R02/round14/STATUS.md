# R02 · раунд 14 · handoff

Задача: R02 — данные: 12 категорий, синтетика v3, инструмент разметки, LLM-скрипты (prompts/R02.txt).
Агент / город: Claude Code (облачная сессия), Астана, Birge.
Обновлено: 2026-10-10, Asia/Almaty (точное время — у коммита).
Статус: ready_for_review (7 задач промпта + probe_v2 и DATASHEET; LLM-скрипты с настоящим API — NOT_RUN, запуск у владельца)
Рабочая ветка: claude/r14-R02 (по правилу COMMON.txt; создана от claude/round-14-package @ 887ef4b).
Первый checkpoint 887ef4b до появления правила ушёл и в claude/round-14-package — там только пути R02;
решение об откате — за координатором (см. research/round-14-results/R02/INTEGRATION.txt).
Исходный коммит: c75a9ac (база пакета при старте), пакет с правилом о ветках — 7ff639a.
Код проверен на: 229f1aa (основная работа) и f62cc93 (probe_v2); затем — DATASHEET и документация.
Назначенные пути: ml/datasets/, ml/labeling/, web/labeling/, tests/civic/R02/round14/,
research/round-14-results/R02/, этот файл. Старые тесты tests/civic/R02/*.py (раунд 13, другой модуль) не трогал.

Цель и критерий готовности (из промпта): владелец за 2 часа размечает 300 текстов без мыши, экспорт открывается
agreement.py; корпус v3 лежит в ветке, R03 может обучать с утра 12 октября.

## Что сделано
- [x] 1. web/labeling/ — офлайн-страница разметки (index.html, app.js, core.js, style.css, categories.js из
      categories_v2.json скриптом ml/labeling/gen_categories_js.py). 12 категорий с иконками и подписями ru/kk,
      клавиши 1…9, 0, -, = по event.code (работают в казахской и русской раскладке), N «Не жалоба», F «Сомневаюсь»,
      Пробел «Пропустить», Backspace/Z «Отменить», ← →, L — язык текста, Ctrl+S — экспорт JSONL, «57 / 300»,
      скорость и остаток времени; автосохранение после каждого действия и «Продолжить»; режим второго разметчика
      (детерминированный поднабор по ключу, чужие метки не загружаются, отдельное хранение); ru/kk интерфейс;
      1366×768 без прокрутки, 375 px без горизонтальной прокрутки; пустой/битый файл — понятная ошибка.
- [x] 2. ml/labeling/anonymize.py (телефон, email, ИИН, ссылки, карты/длинные номера, госномера, дом/квартира/
      подъезд ru+kk, улица+номер, имена по явным шаблонам; отчёт только из чисел) и import_form.py (согласие,
      обезличивание, повторы, язык форма/авто, дата без времени, стабильный id f-…, перемешивание, вывод только
      в private/ + private/.gitignore '*', .review.txt для ручной проверки). text_utils.py — общие функции.
- [x] 3. ml/labeling/agreement.py — Cohen's kappa, бутстрэп-ДИ, по категориям, macro-F1 B относительно A, матрица,
      частые несогласия, Markdown/JSON; тексты в отчёте только с --with-texts и только в private/.
- [x] 4. ml/datasets/LABELING_GUIDE_v2.md — 12 категорий, 6 примеров ru+kk на каждую, 25 спорных случаев,
      «Не жалоба» и «Сомневаюсь». Казахские примеры ждут проверки владельцем.
- [x] 5. ml/datasets/synth_v3/ (221 шаблон, seed 20261011): corpus_v3.jsonl — 4260 сообщений
      (train 2659 / val 945 / test 656), все 12 категорий в каждом split, ru 2060 / kk 1542 / mixed 658,
      9 стилей, 1067 сообщений из трудных случаев; обезличено; split по шаблонам; --check воспроизводит sha256.
      paraphrase_pairs_v3.jsonl — 781 пара для R04. ml/datasets/v1_in_v2/ — v1 (2725) → v2: label (уточнённая)
      и label_table (строго v1_to_v2), 393 строки отличаются.
- [x] 6. ml/labeling/llm_client.py (stdlib, OpenAI/NVIDIA, ключ только из окружения, кэш, повторы 429/5xx с
      Retry-After, бюджет --max-usd до отправки), ml/labeling/guide.py (правила для промптов из LABELING_GUIDE_v2),
      ml/datasets/llm_synth.py (корпус llm_v1, сетка категория×стиль×язык, --dry-run, --mock),
      ml/labeling/llm_label.py (строго одна метка, повтор при болтливом ответе, повторное обезличивание,
      --confirm-external, текст в выход не пишется). Проверено только на подставном транспорте.
- [x] 7. ml/datasets/README.md; research/round-14-results/R02/: DELIVERY.json, RUN.txt (команды ноутбука и
      стоимость), INTEGRATION.txt (patch private/ для R01; R03, R04, R11, LOCAL), KK_STRINGS.md (84+9 строк ru/kk).

## Дополнительно (задание после приёмки)
- [x] П. 1. ml/datasets/probe_v2/ — 300 проверочных сообщений, написанных вручную вне шаблонов (25 × 12),
      ru 155 / kk 97 / mixed 48, 9 стилей, 94 спорных случая; source="agent_probe_v2"; split=test.
      Близость к synth_v3 по Jaccard 3-грамм: медиана 0.18, максимум 0.61 (< 0.8). Сборка: python -m ml.datasets.probe_v2.build.
- [x] П. 2. ml/datasets/DATASHEET.md — описание пяти корпусов по схеме «Datasheets for Datasets» (мотивация, состав,
      сбор, разметка, обезличивание, использование, ограничения, лицензии, сопровождение) + схема экспериментов
      A–E для R03: synth_v3, v1_in_v2, llm_v1 (будущий), probe_v2, human_form (будущий, только private/).
      Числа взяты из манифестов. README.md дополнен разделом probe_v2.
      Тест pytest для probe_v2 не добавлен (задание ограничило пути ml/datasets/ и ml/labeling/); все проверки
      встроены в build.py (сборка падает при нарушении) и build.py --check.

## Проверки (Linux, Python 3.13.16, pytest 9.1.1, Node 22.22.0, playwright 1.56.1 + Chromium /opt/pw-browsers)
- python -m pytest tests/civic/R02/round14 — 89 PASS
- node --test tests/civic/R02/round14/labeling_core.test.mjs — 12 PASS
- node --test tests/civic/R02/round14/labeling_browser.test.mjs — 7 PASS (file://, ни одного сетевого запроса,
  1366×768 и 375×812, ru и kk, сквозной экспорт A и B → agreement.py)
- python -m ml.datasets.synth_v3.build --check — ok; python -m ml.labeling.gen_categories_js --check — ok
- Скриншоты: research/round-14-results/R02/screens/ (реально запущенная страница, синтетические фикстуры).
- Не запускалось: LLM-скрипты с настоящим API (нет доступа из облака); Firefox/Safari; реальная разметка владельцем.

## Доказательства и ограничения
- Все данные в Git — синтетика (evidence synthetic). Реальных текстов людей в Git нет.
- Казахский (шаблоны, примеры, интерфейс) не проверен носителем; списки — KK_STRINGS.md и ⚠ в правилах.
- Обезличивание — регулярные выражения; имена и «голые» адреса могут остаться → .review.txt.
- Подробно — DELIVERY.json, known_limits.

## Следующий конкретный шаг
1. R01: применить patch из INTEGRATION.txt (private/ в .gitignore).
2. Владелец: CSV формы → python -m ml.labeling.import_form private\form.csv → web/labeling (300 текстов) →
   второй разметчик (100, ключ birge-2026) → agreement.py.
3. Владелец (LOCAL-8): llm_label и llm_synth по RUN.txt (dry-run → проба → основной запуск); закоммитить
   ml/datasets/llm_v1/corpus_llm_v1.jsonl + manifest в claude/r14-R02.
4. Если у роли останется лимит: помочь R03 с экспериментами (train v3 / llm_v1 / v3+v1 → test людей, разрезы
   по lang/style/hard); внести правки владельца по казахскому в STR.kk / LABELING_GUIDE_v2 / templates.py
   и пересобрать: python -m ml.datasets.synth_v3.build.

## Для воспроизведения
Команды — research/round-14-results/R02/RUN.txt. Секретов нет; ключи API — только переменные окружения.

## Зависимости от других ролей
- R03 берёт ml/datasets/synth_v3/data/corpus_v3.jsonl (и позже llm_v1, тексты людей у владельца).
- R04 берёт paraphrase_pairs_v3.jsonl; может использовать ml.labeling.anonymize.
- R11 может перенести KK_STRINGS.md в свой KK_REVIEW.md.
