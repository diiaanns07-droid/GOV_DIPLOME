# R03 · раунд 15 · ИИ-аналитик акима

Роль: R03
Ветка роли: claude/modest-mccarthy-lrl98u
Начато: 2026-10-15 16:24 Астана (11:24 UTC)
База: origin/claude/clever-hypatia-q6ts4g @ e91acb6 (код FINAL-4 a4937462 + пакет раунда 15)
Автопилот: работаю сам до 17 окт 23:59 Астаны. Push в claude/r15-R03 запрещён средой — ветка сессии выше.

## План
1. agent/civic_assistant/api.py · ask(question, lang, principal) по CONTRACT §7: офлайн-намерения ru/kk/смешанные →
   вызовы модулей в процессе (R07 heat, R08 summary/pulse, R17 board, R12 conflicts, R16, R13) с запасным «модуля нет» →
   факты с источником → ответ блоками (ru/kk) → действия map.focus/open → журнал вызовов.
2. Необязательная языковая модель (OPENAI_* из окружения): только выбор блоков и переформулировка, числа вычёркиваются;
   нет ключа / сбой / > 8 с — офлайн-ответ с пометкой; инструкции внутри вопроса игнорируются.
3. web/civic/assistant/ — window.BirgeAsk.mount(root, {apiBase}): «Спросить Birge», чипы, карточка ответа,
   «Как получен ответ», метка офлайн-режима, ҚАЗ/РУС.
4. Оценка: 50 вопросов ru/kk/смешанные + 10 провокаций → results/ASSISTANT_EVAL.md.
5. eval_human.py (LOCAL-14) — если будут размеченные тексты, иначе NOT_RUN с причиной.

## Сделано
- 11:24 UTC: роль занята, ветка сессии переведена на пакет раунда 15 (fast-forward).
- 11:25 UTC: продолжение каждый час — scheduled task trig_01HDRqCuZR25GqKUWS9wJjpG (в :25). УДАЛИТЬ после 17 окт 23:59 Астаны
  (18:59 UTC): delete_trigger trig_01HDRqCuZR25GqKUWS9wJjpG.
- 12:25 UTC checkpoint 1: agent/civic_assistant/analyst/ (intents, sources, blocks, llm, core) + ask в api.py.
  Три вопроса сценария офлайн: «снег в Нуре + службы» 0,5 с (холодный старт), «службы отстают» 0,15 с, «буран» < 0,01 с.
  Пока нет R17: «отстающие службы» — запасной расчёт по срокам «Картины дня» (сумма просрочек = R08 overdue.count,
  проверено: 5 = 5, открытые 88 = 67 + 21); «буран» — пульс R08 с честной пометкой «штаб не подключён».

## Решения по умолчанию (автопилот)
- Экран аналитика — window.BirgeAnalyst, а не window.BirgeAsk из промпта: BirgeAsk уже занят R13 («Вопрос акиму»,
  web/civic/qa/qa.js, SCREENS.questions в birge.js). Два модуля с одним именем ломали бы друг друга.
- Шлюз R01: маршрут POST assistant/ask → agent.civic_assistant.api.ask (kind=function, staff=True); в arguments() нужна
  строка для ключа assistant.ask (patch — в INTEGRATION.txt). ask принимает и question/lang, и body.

## Следующий шаг
- Тесты tests/civic/R03/test_analyst_*.py (без сети, заглушка провайдера), затем экран web/civic/assistant/analyst.js.

## Вопросы владельцу
- Имя экрана: промпт R03 называет window.BirgeAsk, но это имя уже у R13. Сделал window.BirgeAnalyst (решение по
  умолчанию). Если нужно именно BirgeAsk — R13 должен переименовать свой экран.
