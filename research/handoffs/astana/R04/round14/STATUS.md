# R04 · раунд 14 · handoff (дубли и ML-API)

## ВОЛНА МЕЛОЧЕЙ (11 окт) — пункты 8 и 9 · статус: in_progress

База: FINAL-кандидат R01 `8e67c65` (claude/sharp-dijkstra-0t87gl); мои пути взяты оттуда (в т. ч. правка R01 R15-S13
в similar_search.py). Рабочая сборка для проверки: FINAL + мои пути + мои patch'и (в scratchpad, не в Git).

### п. 8 «Мат и оскорбления» — код готов, проверен
- `ui/civic_ml_api/profanity.py`: check / mask / is_rude / moderation / mask_json / public_response; ru + kk +
  латиница + обходы (xуй, 6лядь, бляяять, «х у й»); первая буква остаётся, остальное «*».
- Проверка: tests/civic/R04/round14/test_r04_profanity.py — 245 PASS; 0 ложных срабатываний на корпусах R02,
  словарях R11, подписях OSM (2,4 млн строк JSON + 172 тыс. строк текстов). Скорость: ~20 мкс на жалобу,
  ответ на 5 000 целей карты — 16 мс (первый раз 96 мс).
- Стыки (patch в research/round-14-results/R04/patches/): r01_web_server_profanity.patch (одна точка в шлюзе:
  всем, кроме сотрудника, — звёздочки), r09_moderation.patch (пометка moderation в записи и staff_view),
  r07_rude_tag.patch (метка «Содержит грубые слова» в «Что пишут жители»), r11_i18n_moderation.patch (ключ moderation.rude).
- Сквозная проверка в сборке (настоящий HTTP): tests/civic/R04/round14/test_r04_polish_joint.py — 3 PASS;
  тесты R09/R07/R11/R01/R04/R15 в сборке с patch'ами — 1264 passed, 2 skipped.

### п. 9 «Разъединить дубли» — следующий шаг
План: patch для R09 (журнал объединений, POST /complaints/{id}/separate, текст жителя при «Я тоже» из формы),
ml/civic_dedup/feedback.py (решения акимата -> пары для tune), тесты, скриншоты.

### Вопросы владельцу (утром)
1. Автор в «Мои обращения» тоже видит свой текст со звёздочками (всё, что уходит на устройство жителя, — без мата;
   так проще и надёжнее). Если нужно показывать автору оригинал — R01 исключает маршрут complaints.mine (1 строка).

---

Роль: R04 «Дубли и ML-API». Агент: Claude Code (облачная сессия), Астана, Birge.
Ветка: `claude/r14-R04` (создана от `claude/round-14-package` @ 83d64bd). В `claude/round-14-package` не пушу.
Свои пути: `ml/civic_dedup/`, `ui/civic_ml_api/`, `tests/civic/R04/round14/`, `research/round-14-results/R04/`, этот файл.
Обновлено: 2026-10-10 (точное время — у коммита).

## Статус: ready_for_review — запасные пути готовы (цель «12 октября» выполнена); e5 и v2 ждут LOCAL

Код: `deeb1de` (= code_sha = tested_sha в DELIVERY.json). Документы — следующим коммитом поверх.

## Что сделано (проверено)
- `ui/civic_ml_api/`: `classify(text)` и `similar(text, point, days, target)` по CONTRACT §7, имена совпадают с
  таблицей шлюза R01. Цепочка classify: v2 R03 (ONNX) -> v1 + словарь R03 -> словарь -> словарь v1 -> «other».
  Ленивая загрузка под блокировкой, без сети; сбой v2 -> запасной путь, 3 сбоя подряд -> v2 выключена.
  Сверх контракта: `suggest` (чип «Похоже на»), `source`, `score_kind`; `people`, `people_total` в similar.
  `connect_store(store)` (ComplaintStore R09) + фоновый прогрев кэша (при подключении и по событию `created`).
  CLI: `python -m ui.civic_ml_api status|classify|similar`.
- `ml/civic_dedup/`: правило «текст ≥ порога И (та же цель ИЛИ ≤ 200 м) И N дней И открыто»; запасной метод
  ngram-concept-v1 (n-граммы + двуязычный словарь 48 понятий, транслит, казахский без спецбукв); e5 (ONNX) — код,
  тесты на крошечной модели и LOCAL-скрипт export_e5; tune (порог на dev R02, отчёт на test), bench, fixtures.
- Метрики (синтетика R02): дубли test geo P 0.880 / R 0.906 / F1 0.893; classify test 0.784 (v1 одна 0.518);
  скорость (облако): classify p95 0.4 мс, similar p95 8 мс (город) / 39–67 мс (5 000 жалоб в одном круге).
- Тесты: 97 PASS в tests/civic/R04/round14; весь `pytest tests` 967 passed / 4 skipped; R03+R04 вместе 137/6 skipped.
- Стык со шлюзом R01 (@ 2eaeacb) проверен во временной папке: 200 / 400 / 503; patch для target — в результатах.
- Документы: research/round-14-results/R04/{RESULTS.md, INTEGRATION.txt, RUN.txt, DELIVERY.json,
  classify_eval.json, r01_similar_target.patch}.

## Ждём
- R01: перенос путей, patch target (3 строки), `connect_store` + `warmup` при старте (INTEGRATION.txt §R01).
- LOCAL-R04-1 (ноутбук): export_e5 -> tune --method all --write-config -> bench (INTEGRATION.txt, раздел LOCAL).
- LOCAL-4 (R03): файлы v2 в ml/civic_classifier_v2/artifacts/onnx — classify возьмёт их сам.

## Важно для следующего агента
- В ветке R04 НЕТ v1/R03/R02/R09 (чужие пути). Для проверки положите локальные неотслеживаемые копии:
  `git show <sha>:<путь> > <путь>` для ml/civic_classifier (14c3384), ml/civic_classifier_v2 (origin/claude/r14-R03),
  ml/datasets (origin/claude/r14-R02), ui/civic_feedback/v2 (origin/claude/modest-shannon-0ki93p) и добавьте их в
  .git/info/exclude. ui/civic_feedback/*.py в базе ОТСЛЕЖИВАЮТСЯ — не перезаписывайте их, только папку v2/.
- В tests/civic/R04/round14 нарочно нет conftest.py (конфликт с `from conftest import` у R03) — помощники в r04_helpers.py.
- Протокол tune: выбор только по dev; test уже просмотрен 5 раз (журнал в RESULTS.md) — новые изменения метода
  проверять на новых парах (после формы LOCAL-6), а не на этом test.

## Следующий шаг
1. После LOCAL-R04-1: проверить присланные dedup_config.json / e5_export.json / dedup_eval_all.json / bench_laptop.json,
   обновить RESULTS.md (раздел e5) и DELIVERY.json.
2. После сборки R01: прогнать `python -m pytest -q tests/civic/R04/round14` и `python -m ui.civic_ml_api status` в сборке.
3. После формы LOCAL-6: собрать пары дублей из настоящих обращений (вручную размеченные), повторить tune, отчитаться.
