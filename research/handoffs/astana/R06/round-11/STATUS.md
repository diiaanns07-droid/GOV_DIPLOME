# R06 — Обращения жителей и очередь модерации (раунд 11, Астана)

- Роль: R06
- Ветка: `claude/focused-hypatia-z8h0no`
- Исходный HEAD: `834a25fb860dd5514d02c9274b70d7bf8a53a79c` (origin/main на момент старта)
- PACK_SHA: `9c2f5c0dae14b46c0697a9dfc7f854351bfd570d` (origin/codex/govtech-main-interface)
- Снимок приложения для сравнения: `b2cb2e02c602c166ba6d47c02d8e902e5478c791` (только чтение через git show)
- Собственные пути: `ui/civic_feedback/`, `web/civic/feedback/`, `tests/civic/R06/`,
  `research/round-11-results/R06/`, `research/handoffs/astana/R06/round-11/STATUS.md`

## Статус: DONE (обязательная часть) — checkpoint 8

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
- Найдены 3 расхождения R01@341c554 <-> R02@6a28de2 (не код R06): нет экспорта CivicService, путь без
  префикса, нет host_allowed. Устранены в R01@eef5a7b и R02@92f7aba; сквозной тест через шлюз R01
  проходит БЕЗ обходов (INTEGRATION.txt §5).
- С 36a0604 R06 (как R02) обслуживает только полный путь `/api/civic/v1/...`.
- Stretch: CLI `python -m ui.civic_feedback stats|purge-antispam`; совместимость с onFeedback R03
  (геометрия объекта не путается с местом); фильтры очереди и счётчик pending уже были.
- `research/round-11-results/R06/r01_integration.patch` (против R01@eef5a7b, 3 файла R01): статика,
  3 маршрута, панель «Сообщения жителей» с mountModeration. Проверено в настоящем приложении R01
  (`tests/civic/R06/app_e2e_r06.cjs`, Chromium) → 9/9 PASS; снимки `screenshots/r06_app_*.png`.
  Снимок выявил сжатие очереди в узкой панели → сетка теперь по ширине контейнера (auto-fit).

Проверки:
- `python3 -m pytest tests/civic/R06 -q` → 129 passed, 2 skipped (PASS; skip = нет R01/R02 в ветке)
- `python3 -m pytest -q` → 241 passed, 2 skipped (PASS, весь репозиторий ветки)
- `node tests/civic/R06/browser_r06.cjs --screenshots research/round-11-results/R06/screenshots` → 29/29 PASS
- Независимая приёмка R10 (`tests/civic/R10/standalone/standalone_r06.py`, R10@9123af0) на eaa113d → 23/23 OK.
  На 417cc23 она нашла 2 дефекта (суррогат `\ud800` → исключение; перехват путей без префикса) —
  исправлены в 36a0604. Лог: `research/round-11-results/R06/checks/r10_standalone_r06.txt`.
- scratch R01@eef5a7b + R02@92f7aba + R06 без обходов → test_r06_gateway_smoke.py + test_r06_r02_compat.py
  3 passed; весь объединённый набор 439 passed, 1 failed (тест R02 ищет свой web_server.patch, которого
  я не копировал в scratch — артефакт сборки, не R06)
- `python3 -m pytest -q` → 115 passed (PASS, весь репозиторий)

Не запускалось: сборка R01 с картой R03 и кабинетом R04 (не объединены); R08 нет в GitHub.

Следующий шаг (R01): импорт путей R06 + `git apply research/round-11-results/R06/r01_integration.patch`, затем app_e2e_r06.cjs на CODE_SHA. R06: при появлении R08 — прогон с настоящим classify.

## Финал сессии
- Роль R06, ветка `claude/focused-hypatia-z8h0no`, код проверен на `91f2508` (DELIVERY.code_commit).
- Push: OK для всех checkpoint (462ecf5, 7effc8e, d8aff46, 591386e, 417cc23, 36a0604, a6c0260, eaa113d,
  0d97313, 91f2508 и этот коммит с handoff).
- Работает: FeedbackService (приём, лимиты, дубликаты, модерация с CSRF/ревизиями, согласие и его отзыв,
  скрытие контактов, журнал), CivicFeedback.mount / mountModeration, CLI обслуживания, адаптер R08.
- Команды: `python3 -m pytest tests/civic/R06 -q`; `node tests/civic/R06/browser_r06.cjs`;
  `R06_BASE=… node tests/civic/R06/app_e2e_r06.cjs` (на собранном приложении).
- Остаточный риск: подсказки о персональных данных — эвристики (имена/адреса находит только человек);
  лимит по IP делится за NAT; R08 не проверен с настоящей моделью; карта/подложка в песочнице не проверялись.
- Следующий шаг: R01 импортирует пути R06 и применяет `r01_integration.patch`.
