# R06 — Обращения жителей и очередь модерации (раунд 11, Астана)

- Роль: R06
- Ветка: `claude/focused-hypatia-z8h0no`
- Исходный HEAD: `834a25fb860dd5514d02c9274b70d7bf8a53a79c` (origin/main на момент старта)
- PACK_SHA: `9c2f5c0dae14b46c0697a9dfc7f854351bfd570d` (origin/codex/govtech-main-interface)
- Снимок приложения для сравнения: `b2cb2e02c602c166ba6d47c02d8e902e5478c791` (только чтение через git show)
- Собственные пути: `ui/civic_feedback/`, `web/civic/feedback/`, `tests/civic/R06/`,
  `research/round-11-results/R06/`, `research/handoffs/astana/R06/round-11/STATUS.md`

## Статус: PARTIAL — checkpoint 1

Сделано:
- `ui/civic_feedback/service.py` — `FeedbackService(db_path, object_lookup, clock=None)`,
  `handle(method, path, query, body, principal, context)`; таблицы `feedback_meta`,
  `feedback_messages`, `feedback_events`.
- `ui/civic_feedback/fixtures.py` — FIXTURE object_lookup/principal (R02 ещё не запушен).
- Тесты: сохранение сообщения, receipt без персональных данных, pending не в публичном списке,
  сохранение после перезапуска.

Проверки:
- `python3 -m pytest tests/civic/R06 -q` → 3 passed (PASS)
- `python3 -m pytest -q` → 115 passed (PASS, весь репозиторий)

Не запускалось: фронтенд, браузерный прогон, интеграция с R02/R01 (их кода в GitHub нет).

Следующий шаг: тесты валидации/rate limit/модерации/приватности, затем фронтенд `web/civic/feedback/`.
