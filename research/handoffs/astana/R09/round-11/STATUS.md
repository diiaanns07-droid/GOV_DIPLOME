# R09 — AI-помощник с проверенными фактами (раунд 11, Астана)

- Роль: R09 (единственная роль этой сессии)
- Ветка: `claude/wizardly-ptolemy-qy8ltw`
- Исходный HEAD ветки: `834a25fb860dd5514d02c9274b70d7bf8a53a79c` (= origin/main)
- PACK_SHA (origin/codex/govtech-main-interface): `9c2f5c0dae14b46c0697a9dfc7f854351bfd570d` — PACK_STATUS READY
- Снимок приложения для сравнения: `b2cb2e02c602c166ba6d47c02d8e902e5478c791` (agent/school_ai.py, evidence.py, tools.py прочитаны через git show)
- Собственные пути: `agent/civic_assistant/`, `web/civic/assistant/`, `tests/civic/R09/`,
  `research/round-11-results/R09/`, `research/handoffs/astana/R09/round-11/STATUS.md`

## Статус: PARTIAL — checkpoint 1

### Сделано
- `agent/civic_assistant/facts.py`: серверный каталог фактов из публичного DTO civic-v1 (allowlist),
  публичной истории; draft/archived -> ContextError(object_not_public); неизвестное -> known=False;
  digest контекста (подмена фактов -> source=unavailable).
- `agent/civic_assistant/render.py`: тексты RU/KK собирает код; у каждой фразы fact_ids/source_ids;
  synthetic/hypothesis/derived помечаются в каждом ответе; плановая дата != завершение.
- `agent/civic_assistant/answer.py`: `build_answer(question, verified_context, provider=None)`,
  шаблонный классификатор RU/KK, строгая валидация выбора провайдера (код написан, тесты — CP2).
- `research/round-11-results/R09/QUESTIONS.txt`: 12 вопросов -> intent -> факты.

### Проверки
- `python3 -m pytest tests/civic/R09 -q` -> 16 passed (CP1).

### Не запускалось
- Живой LLM (вне задания). Интеграция в app (делает R01).

### Следующий шаг
CP2: тесты провайдера (неизвестный ID, свободный текст, тайм-аут, лишние ключи), provider adapter contract.
