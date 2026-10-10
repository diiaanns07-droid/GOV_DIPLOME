# R04 · раунд 14 · handoff (дубли и ML-API)

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
