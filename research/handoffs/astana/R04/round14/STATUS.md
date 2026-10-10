# R04 · раунд 14 · handoff (дубли и ML-API)

Роль: R04 «Дубли и ML-API». Агент: Claude Code (облачная сессия), Астана, Birge.
Ветка: `claude/r14-R04` (создана от `claude/round-14-package` @ 83d64bd). В `claude/round-14-package` не пушу.
Свои пути: `ml/civic_dedup/`, `ui/civic_ml_api/`, `tests/civic/R04/round14/`, `research/round-14-results/R04/`, этот файл.
Обновлено: 2026-10-10 (точное время — у коммита).

## Статус: partial — checkpoint 1

## Что сделано
- [x] Прочитаны COMMON, CONTRACT, UX_BRIEF, prompts/R04, v1 (14c3384), ветки R02 (05b789e), R03 (f9370b0),
      R09 (4021818), R01 (2eaeacb: шлюз v2 уже ищет `ui.civic_ml_api.classify/similar`).
- [x] `ml/civic_dedup/`: normalize (латиница -> кириллица, казахские буквы -> русские двойники), concepts
      (двуязычный словарь понятий), scorers (n-граммы + понятия), e5 (ONNX, код без весов), search (Deduper:
      ≤ 200 м или та же цель, N дней, открытые, кэш), config/loader.
- [x] `ui/civic_ml_api/`: classify (v2 R03 -> v1 + словарь R03 -> словарь -> словарь v1), similar
      (источник — ComplaintStore R09 через connect_store), status, warmup.
- [ ] tune.py (порог на dev-парах R02, отчёт на test) -> dedup_config.json, RESULTS.md
- [ ] bench.py (classify ≤ 50 мс, similar ≤ 150 мс на 5 000)
- [ ] tests/civic/R04/round14 (пустой, длинный, kk без спецбукв, транслит, нет файлов модели, одновременные)
- [ ] export_e5.py (LOCAL), INTEGRATION.txt, RUN.txt, DELIVERY.json

## Важно для проверки
- v1 (`ml/civic_classifier/`), R03 (`ml/civic_classifier_v2/`), R02 (`ml/datasets/`) в моей ветке НЕ коммичу —
  это чужие пути. Для проверки они лежат локально неотслеживаемыми копиями (точные SHA выше).
  В сборке R01 они уже есть / будут; без них classify честно опускается по цепочке до «other».

## Следующий шаг
tune.py -> dedup_config.json -> тесты -> bench -> INTEGRATION/RUN/DELIVERY.
