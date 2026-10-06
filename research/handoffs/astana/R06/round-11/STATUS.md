# R06 — Обращения жителей и очередь модерации (раунд 11, Астана)

- Роль: R06
- Ветка: `claude/focused-hypatia-z8h0no`
- Исходный HEAD: `834a25fb860dd5514d02c9274b70d7bf8a53a79c` (origin/main на момент старта)
- PACK_SHA: `9c2f5c0dae14b46c0697a9dfc7f854351bfd570d` (origin/codex/govtech-main-interface)
- Снимок приложения для сравнения: `b2cb2e02c602c166ba6d47c02d8e902e5478c791` (только чтение через git show)
- Собственные пути: `ui/civic_feedback/`, `web/civic/feedback/`, `tests/civic/R06/`,
  `research/round-11-results/R06/`, `research/handoffs/astana/R06/round-11/STATUS.md`

## Статус: DONE (обязательная часть) — checkpoint 5; дальше stretch

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
- `ui/civic_feedback/integration.py` — object_lookup поверх CivicService R02, dispatch_civic.
- `research/round-11-results/R06/INTEGRATION.txt`, `contract_delta.txt`, `examples/*.json`
  (make_examples.py), `checks/*.txt|json`.
- Совместимость с реальным Principal R02: `expires_at` — epoch-число (исправлено до коммита).
- Найдены 3 расхождения R01@341c554 <-> R02@6a28de2 (не код R06), описаны в INTEGRATION.txt §5:
  нет экспорта CivicService, путь без префикса, нет host_allowed в context.
- С 36a0604 R06 (как R02) обслуживает только полный путь `/api/civic/v1/...`.

Проверки:
- `python3 -m pytest tests/civic/R06 -q` → 128 passed, 2 skipped (PASS; skip = нет R01/R02 в ветке)
- `python3 -m pytest -q` → 240 passed, 2 skipped (PASS, весь репозиторий ветки)
- `node tests/civic/R06/browser_r06.cjs --screenshots research/round-11-results/R06/screenshots` → 27/27 PASS
- Независимая приёмка R10 (`tests/civic/R10/standalone/standalone_r06.py` из ветки R10) на 36a0604 → 23/23 OK.
  На 417cc23 она нашла 2 дефекта (суррогат `\ud800` → исключение; перехват путей без префикса) —
  исправлены в 36a0604. Лог: `research/round-11-results/R06/checks/r10_standalone_r06.txt`.
- scratch: R06 + R02@6a28de2 → test_r06_r02_compat.py 2 passed; R01@341c554 + R02 + R06 с тремя
  scratch-обходами стыка R01/R02 → test_r06_gateway_smoke.py 1 passed
- `python3 -m pytest -q` → 115 passed (PASS, весь репозиторий)

Не запускалось: сборка R01 с картой R03 и кабинетом R04 (не объединены); R08 нет в GitHub.

Следующий шаг: stretch — CLI обслуживания, сверка с R03/R04 точками монтирования.
