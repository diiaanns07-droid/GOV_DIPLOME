# R09 — AI-помощник с проверенными фактами (раунд 11, Астана)

- Роль: R09 (единственная роль этой сессии)
- Ветка: `claude/wizardly-ptolemy-qy8ltw`
- Исходный HEAD ветки: `834a25fb860dd5514d02c9274b70d7bf8a53a79c` (= origin/main)
- PACK_SHA (origin/codex/govtech-main-interface): `9c2f5c0dae14b46c0697a9dfc7f854351bfd570d` — PACK_STATUS READY
- Снимок приложения для сравнения: `b2cb2e02c602c166ba6d47c02d8e902e5478c791` (agent/school_ai.py, evidence.py, tools.py прочитаны через git show; подход «модель выбирает ID, код пишет текст» перенят)
- Собственные пути: `agent/civic_assistant/`, `web/civic/assistant/`, `tests/civic/R09/`,
  `research/round-11-results/R09/`, `research/handoffs/astana/R09/round-11/STATUS.md`
- Проверенный код: `97c01b1561213e83bf4db655f8ae392b8634fe3e`

## Статус: READY (модуль готов к интеграции R01) — checkpoint 6

### Что работает
- `facts.py` — серверный каталог фактов из публичного DTO civic-v1 (allowlist), публичной истории и
  результата R07; draft/archived -> отказ; неизвестное -> known=False («нет данных»), не 0 и не сегодня;
  digest контекста (подмена -> source=unavailable).
- `render.py` — текст RU/KK собирает код; у каждой фразы fact_ids/source_ids; synthetic/hypothesis/derived
  помечаются в каждом ответе; плановая дата != завершение; обязательные оговорки (required) не убираются
  выбором модели.
- `audit.py` — runtime-аудит каждой фразы: цифра без факта, недословная цитата, «официально одобрено/
  утверждено», «завершено» без status=completed -> фраза удаляется.
- `answer.py` — `build_answer(question, verified_context, provider=None)`; source = фактический путь
  (template / llm / unavailable); строгая валидация выбора провайдера, тайм-аут 8 с.
- `providers.py` — контракт civic-assistant-provider-v1, MockProvider, OpenAICompatibleProvider.
- `scenario.py` — A/B только по метрикам engine R07, без «лучше».
- `api.py` — AssistantEndpoint для POST /assistant и /staff/assistant/extract; r02_public_loader,
  r07_case_loader; 400/405/413/422/429; draft и несуществующий объект неразличимы.
- `extract.py` — черновик полей из ВСТАВЛЕННОГО текста: quote/span/source_id/confidence_kind; неполная
  дата и противоречия -> null; инструкции в тексте -> ignored_instructions; URL не скачивается.
- `web/civic/assistant/` — CivicAssistant.mount и mountDraftReview; только textContent; AbortController +
  номер запроса; ручной перенос полей редактором.
- `evaluate.py` — adversarial-оценка (37 кейсов + 17 браузерных).

### Проверки (выполнены на 97c01b1)
- `python3 -m pytest tests/civic/R09 -q` -> 108 passed (включая реальный Chromium).
- `python3 -m agent.civic_assistant.evaluate --ui` -> PASS 54 / FAIL 0 / NOT_RUN 1 (EVAL_REPORT.txt).
- `check_r02_r07_integration.py` на коде R02 92f7aba и R07 18f8ac8 -> 15/15 (integration_r02_r07.json).
- Совместимость с записями R05 (e477e5d, demo_synthetic.json — 9 СИНТЕТИЧЕСКИХ записей) -> 9/9
  (compat_r05_demo.json). Прогон нашёл и исправил: для отменённого объекта сроки показывались без
  пометки отмены; «Откуда эти данные?» уходило в overview.
- Реальные скриншоты: `ui_assistant_desktop.png`, `ui_assistant_mobile.png`.

### Не запускалось
- Живой LLM (платно, вне задания) — NOT_RUN. Встраивание в общий app — делает R01.
- Официальные страницы gov.kz из BRIEF (news 1193903, article 99399): CONNECT 403 от сетевой политики
  среды; не обходилось. Извлечение проверено только на синтетических текстах. Реальных записей у R05 — 0.

### Найдено по ходу (для R01/R02/R04)
- Шлюз R01 передаёт сервисам относительный путь, R02 (92f7aba) ждёт полный `/api/civic/v1/...`.
  R09 поддерживает обе формы; R01/R02 нужно договориться.
- В R02 публичная история содержит только события публикации: публичное объяснение переноса срока
  редактор пишет в reason публикации (R04 стоит подсказать это в форме).
- В CIVIC_ROUTES R01 нет `/staff/assistant/extract` — добавить по INTEGRATION.txt.

### Оставшийся риск
KK-тексты без носителя языка; шаблонный классификатор по ключевым словам; извлечение — шаблоны для
типовых форм; все проверки на синтетике.

### Следующий шаг
R01 подключает AssistantEndpoint и assets по `research/round-11-results/R09/INTEGRATION.txt`.
R09 далее (stretch): прогон помощника на пакете реальных объектов R05.
