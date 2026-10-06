# R06 — Обращения жителей и очередь модерации (раунд 11, Астана)

- Роль: R06
- Ветка: `claude/focused-hypatia-z8h0no`
- Исходный HEAD: `834a25fb860dd5514d02c9274b70d7bf8a53a79c` (origin/main на момент старта)
- PACK_SHA: `9c2f5c0dae14b46c0697a9dfc7f854351bfd570d` (origin/codex/govtech-main-interface)
- Снимок приложения для сравнения: `b2cb2e02c602c166ba6d47c02d8e902e5478c791` (только чтение через git show)
- Собственные пути: `ui/civic_feedback/`, `web/civic/feedback/`, `tests/civic/R06/`,
  `research/round-11-results/R06/`, `research/handoffs/astana/R06/round-11/STATUS.md`

## Статус: PARTIAL — checkpoint 3 (backend + фронтенд + браузер)

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
- `web/civic/feedback/feedback.js|.css` — `window.CivicFeedback.mount` (форма жителя + публичные
  сообщения объекта + квитанция/отзыв согласия) и `mountModeration` (очередь, фильтры, счётчики,
  карточка рядом с объектом, решение с причиной/ответом/публичной версией, журнал).
- `tests/civic/R06/harness/` — FIXTURE-стенд (loopback, cookie-сессия fixture, CSRF, Origin).
- `tests/civic/R06/browser_r06.cjs` — прогон в реальном Chromium; скриншоты в
  `research/round-11-results/R06/screenshots/`.

Проверки:
- `python3 -m pytest tests/civic/R06 -q` → 118 passed (PASS)
- `node tests/civic/R06/browser_r06.cjs --screenshots research/round-11-results/R06/screenshots` → 26/26 PASS
- `python3 -m pytest -q` → 115 passed (PASS, весь репозиторий)

Не запускалось: интеграция с R02/R01 (их кода в GitHub на момент проверки нет).

Следующий шаг: INTEGRATION.txt, примеры DTO, DELIVERY.json, contract_delta.txt.
