# R09 — AI-помощник с проверенными фактами (раунд 11, Астана)

- Роль: R09 (единственная роль этой сессии)
- Ветка: `claude/wizardly-ptolemy-qy8ltw`
- Исходный HEAD ветки: `834a25fb860dd5514d02c9274b70d7bf8a53a79c` (= origin/main)
- PACK_SHA (origin/codex/govtech-main-interface): `9c2f5c0dae14b46c0697a9dfc7f854351bfd570d` — PACK_STATUS READY
- Снимок приложения для сравнения: `b2cb2e02c602c166ba6d47c02d8e902e5478c791` (agent/school_ai.py, evidence.py, tools.py прочитаны через git show)
- Собственные пути: `agent/civic_assistant/`, `web/civic/assistant/`, `tests/civic/R09/`,
  `research/round-11-results/R09/`, `research/handoffs/astana/R09/round-11/STATUS.md`

## Статус: PARTIAL — checkpoint 5

### Сделано
- `agent/civic_assistant/facts.py`: серверный каталог фактов из публичного DTO civic-v1 (allowlist),
  публичной истории; draft/archived -> ContextError(object_not_public); неизвестное -> known=False;
  digest контекста (подмена фактов -> source=unavailable).
- `agent/civic_assistant/render.py`: тексты RU/KK собирает код; у каждой фразы fact_ids/source_ids;
  synthetic/hypothesis/derived помечаются в каждом ответе; плановая дата != завершение.
- `agent/civic_assistant/answer.py`: `build_answer(question, verified_context, provider=None)`,
  шаблонный классификатор RU/KK, строгая валидация выбора провайдера (код написан, тесты — CP2).
- `research/round-11-results/R09/QUESTIONS.txt`: 12 вопросов -> intent -> факты.
- CP2 `agent/civic_assistant/providers.py`: контракт civic-assistant-provider-v1, MockProvider,
  OpenAICompatibleProvider (проверен на поддельном клиенте, без платного вызова), provider_from_settings.
  Провайдер получает только {id,label,known} — без значений, цитат и служебных полей.
- CP2 `agent/civic_assistant/audit.py`: runtime-аудит каждой фразы: цифра без факта, цитата не дословно,
  «официально одобрено/утверждено», «завершено» без status=completed -> фраза удаляется, код в warnings.
- Причина переноса берётся только из публичной истории и не из первой (исходной) записи.
- CP3 `agent/civic_assistant/scenario.py`: факты из civic-scenario-result-v1 R07 (baseline/A/B/a_vs_b,
  покрытие графа); A/B объясняются только метриками engine, без «лучше». Fixture
  `tests/civic/R09/fixtures/r07_synthetic_result.json` — реальный вывод compare() R07
  (ветка claude/brave-hopper-bkc58b, SHA 18f8ac8, кейс synthetic-tiny-v1-demo; граф синтетический).
- CP3 `agent/civic_assistant/api.py`: AssistantEndpoint.handle(method,path,query,body,context) для
  POST /api/civic/v1/assistant; тело — ровно {question,object_id,scenario_id}; facts/context/role -> 400;
  draft и несуществующий объект неразличимы (unavailable); 413/422/429/405; r02_public_loader
  (публичный GET /objects/{id} без cookie), r07_case_loader (scenario_id = case_id, payload с сервера).
- CP4 `agent/civic_assistant/extract.py`: extract_draft(text, source_id, ...) из ПЕРЕДАННОГО текста (URL не
  скачивается). Поля: title, kind, planned_start, current_planned_end, amount_kzt, basis, organization,
  location_text; у каждого quote/span/source_id/confidence_kind/needs_review/alternatives. Неполная дата и
  противоречия -> null. Статус не извлекается. Инструкции в тексте -> ignored_instructions (данные).
  Провайдер возвращает только цитаты; код проверяет вхождение и сам разбирает значение.
  POST /api/civic/v1/staff/assistant/extract: 401/403 (роль, same-origin), 400/413/422; ничего не сохраняет.
- CP5 `web/civic/assistant/assistant.js|.css`: window.CivicAssistant.mount({root,api,objectId,scenarioId?}) -> {destroy}
  и mountDraftReview({root,api,onApplyField}) -> {destroy}. Только textContent; AbortController + номер запроса
  (запоздавший ответ/смена объекта/destroy); проверка object_id ответа; 429/сеть/timeout — понятные сообщения.
  Редактор отмечает поля вручную, onApplyField переносит их в форму; null-поля не принимаются.
  `web/civic/assistant/demo.html` + `tests/civic/R09/demo_server.py` (stdlib, 127.0.0.1) + `ui_check.cjs` (Playwright).
  Реальные скриншоты: research/round-11-results/R09/ui_assistant_desktop.png, ui_assistant_mobile.png.

### Проверки
- `R09_SCREENSHOT_DIR=research/round-11-results/R09 python3 -m pytest tests/civic/R09 -q` -> 104 passed
  (включая 17 проверок UI в Chromium через Playwright 1.56.1; CP4 100; CP3 79; CP2 49; CP1 16).

### Не запускалось
- Живой LLM (вне задания). Интеграция в app (делает R01).

### Следующий шаг
CP6: adversarial eval (таблица PASS/FAIL/NOT_RUN), EVAL_REPORT.txt, INTEGRATION.txt, contract_delta при необходимости.
