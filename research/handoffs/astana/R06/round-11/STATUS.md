# R06 — Обращения жителей и очередь модерации (раунд 11, Астана)

- Роль: R06
- Ветка: `claude/focused-hypatia-z8h0no`
- Исходный HEAD: `834a25fb860dd5514d02c9274b70d7bf8a53a79c` (origin/main на момент старта)
- PACK_SHA: `9c2f5c0dae14b46c0697a9dfc7f854351bfd570d` (origin/codex/govtech-main-interface)
- Снимок приложения для сравнения: `b2cb2e02c602c166ba6d47c02d8e902e5478c791` (только чтение через git show)
- Собственные пути: `ui/civic_feedback/`, `web/civic/feedback/`, `tests/civic/R06/`,
  `research/round-11-results/R06/`, `research/handoffs/astana/R06/round-11/STATUS.md`

## Статус: PARTIAL — checkpoint 2 (backend + тесты)

Сделано:
- `ui/civic_feedback/service.py` — `FeedbackService(db_path, object_lookup, clock=None)`,
  `handle(method, path, query, body, principal, context)`; таблицы `feedback_meta`,
  `feedback_messages`, `feedback_events`.
- `ui/civic_feedback/fixtures.py` — FIXTURE object_lookup/principal (R02 ещё не запушен).
- Тесты: сохранение, receipt без персональных данных, pending не публичен, перезапуск;
  валидация (object_id/черновик/город/место/противоречие), 413/400/422, лишние поля и поддельная роль,
  rate limit (5 локальных запросов), дубликаты/повтор client_request_id, модерация с CSRF/Origin,
  истёкшая сессия, 409 по ревизии, согласие и его отзыв, скрытие контактов, ответ не цитирует скрытое,
  XSS как текст, классификатор (ошибка/мусор/зависание), похожие сообщения, маршрутизация.
- `ui/civic_feedback/classifier_adapter.py` — необязательная загрузка `ml.civic_classifier.classify`.

Проверки:
- `python3 -m pytest tests/civic/R06 -q` → 111 passed (PASS)
- `python3 -m pytest -q` → 115 passed (PASS, весь репозиторий)

Не запускалось: фронтенд, браузерный прогон, интеграция с R02/R01 (их кода в GitHub нет).

Следующий шаг: фронтенд `web/civic/feedback/` (CivicFeedback.mount, mountModeration) и браузерная проверка.
