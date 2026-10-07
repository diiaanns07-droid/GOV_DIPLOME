# R08 — обучаемая модель обращений и честный эксперимент (раунд 12, Астана)

- Роль: R08 · ветка сессии: `claude/wizardly-ptolemy-qy8ltw` (назначена средой)
- CODE_BASE_SHA: `56538a3a7504d4589c38ab4d3c5107f12aa7f8a6` (codex/govtech-main-interface; пакет round-12 в 19f90e6)
- **BASE_MISMATCH**: ветка сессии уже содержит работу R09 раунда 11 и начинается от 834a25f; пересоздать её
  от CODE_BASE_SHA без force push нельзя. Поэтому: коммиты только в путях R08, проверка совместимости —
  в отдельном worktree от 56538a3, переносимый патч путей R08 — в research/round-12-results/R08/.
- Прежней работы R08 нет ни в одной ветке origin (проверено 2026-10-07).
- Пути: `ml/civic_classifier/`, `tests/civic/R08/`, `research/round-12-results/R08/`, этот файл.

## Статус: PARTIAL — checkpoint 4

### Сделано
- Контракт по фактическому коду базы: метки = `ui/civic_feedback/service.py CATEGORIES`; язык от
  `detect_language` (`ru|kk|unknown`); вызов в потоке с тайм-аутом 2 с; ответ проходит `_clean_suggestion`.
- `ml/civic_classifier`: `classify(text, language)`, загрузка JSON-модели (gzip, sha256, без pickle),
  безопасный fallback на эвристику (needs_review=True, score=None), обезличивание телефонов/e-mail/ИИН/ссылок.
- `LABELING_GUIDE.md`, `research/round-12-results/R08/DATA_SOURCES.json` (реальные источники: 403).
- CP2/CP3 `corpus.py` — корпус **v2** (v1 заменён после анализа ошибок validation; test до финала не оценивался):
  191 шаблон (включая лексикон объектов и общие рамки «объект + состояние»), 2725 сообщений RU/KK/смешанный,
  обезличивание до сохранения, 103 точных дубликата удалены до split, group split по шаблонам
  (train 1512 / val 581 / test 631), фильтр близких дубликатов val/test — 1 исключён.
- CP3 `train.py`: NB (alpha 0.05–1.0) и логистическая регрессия (SGD, L2, усреднение) на char 2–5-граммах +
  префиксах слов; выбор по val macro-F1 -> logreg (val 0.725; NB 0.589); порог 0.75 на val
  (цель точности 0.90 достигнута при покрытии 37%). Артефакт `data/model.json.gz` (111 КБ, sha256 в файле).
  Для синтетической модели `needs_review` всегда True (порог не переносится на реальных жителей).
- CLI: `python -m ml.civic_classifier build-corpus|train|evaluate|predict|info`.
- CP4 оценка. Эксперимент 1 (logreg): test macro-F1 0.734 против эвристики 0.848 — эвристика лучше
  (сохранено в `research/round-12-results/R08/exp1/`). Эксперимент 2: гибрид logreg + признаки словаря,
  выбран по validation (0.888; эвристика на val 0.845): test 0.871 [0.780–0.928], probe 0.837;
  парная разница с эвристикой: test +0.022 [−0.048; +0.096], probe +0.005 [−0.024; +0.037] — преимущество
  НЕ доказано. Test использован второй раз — помечено. Отчёт `EVAL_REPORT.md` генерируется из `metrics.json`.
- Память: найден и исправлен 64-МБ буфер gzip при загрузке (пик 80 -> 5.2 МБ); classify ~1.8 мс.
- `data/probe_agent_v1.jsonl`: 112 сообщений, написаны вручную агентом вне генератора (другой стиль) —
  проверка переноса; разметка агентская, не экспертная.

### Проверки
- `python3 -m pytest tests/civic/R08 -q` -> 24 passed (включая побайтное воспроизведение модели переобучением, ~50 с).

### Следующий шаг
Model card, журнал экспериментов, проверка интеграции с ui/civic_feedback на 56538a3, RUN/INTEGRATION/DELIVERY.
