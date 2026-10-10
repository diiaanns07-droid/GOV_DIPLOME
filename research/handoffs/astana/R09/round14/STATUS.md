# R09 round 14 — STATUS (жалоба жителя v2)

Роль: R09 · Ветка: claude/modest-shannon-0ki93p · База: claude/round-14-package @ c75a9ac
Восстановлено: ui/civic_feedback, web/civic/feedback из claude/focused-hypatia-z8h0no @ 933cd90 (код 12b3170, побайтно).
Статус: IN_PROGRESS (checkpoint 1)

## Сделано
- ui/civic_feedback/v2/: categories.py (читает research/round-14/categories_v2.json, сроки ответа),
  record.py (запись §5, язык ru/kk/mixed, цель, запасная ячейка ~150 м «примерное место», проекции без текста),
  store.py (SQLite: create/metoo/set_status/mark_duplicate/list/mine/target_summary/events_since/subscribe),
  migrate.py (v1 feedback_messages -> v2, legacy целиком, идемпотентно), api.py (/api/civic/v2/...).
- Модуль v1 (раунд 13) не менялся.

## Дальше
1. Тесты tests/civic/R09/test_r09v2_*.py.
2. web/civic/feedback/: путь жителя 5 шагов + «Мои обращения», i18n-ключи для R11.
3. DELIVERY.json, RUN.txt, INTEGRATION.txt (маршруты для R01, события для R07, ключи для R11).
