# R08 — обучаемая модель обращений и честный эксперимент (раунд 12, Астана)

- Роль: R08 · ветка сессии: `claude/wizardly-ptolemy-qy8ltw` (назначена средой)
- CODE_BASE_SHA: `56538a3a7504d4589c38ab4d3c5107f12aa7f8a6` (codex/govtech-main-interface; пакет round-12 в 19f90e6)
- **BASE_MISMATCH**: ветка сессии уже содержит работу R09 раунда 11 и начинается от 834a25f; пересоздать её
  от CODE_BASE_SHA без force push нельзя. Поэтому: коммиты только в путях R08, проверка совместимости —
  в отдельном worktree от 56538a3, переносимый патч путей R08 — в research/round-12-results/R08/.
- Прежней работы R08 нет ни в одной ветке origin (проверено 2026-10-07).
- Пути: `ml/civic_classifier/`, `tests/civic/R08/`, `research/round-12-results/R08/`, этот файл.

## Статус: PARTIAL — checkpoint 1

### Сделано
- Контракт по фактическому коду базы: метки = `ui/civic_feedback/service.py CATEGORIES`; язык от
  `detect_language` (`ru|kk|unknown`); вызов в потоке с тайм-аутом 2 с; ответ проходит `_clean_suggestion`.
- `ml/civic_classifier`: `classify(text, language)`, загрузка JSON-модели (gzip, sha256, без pickle),
  безопасный fallback на эвристику (needs_review=True, score=None), обезличивание телефонов/e-mail/ИИН/ссылок.
- `LABELING_GUIDE.md`, `research/round-12-results/R08/DATA_SOURCES.json` (реальные источники: 403).

### Проверки
- `python3 -m pytest tests/civic/R08 -q` -> 15 passed.

### Следующий шаг
Синтетический корпус RU/KK/смешанный с группами шаблонов, dedup до split, манифест split.
