# R03 · раунд 15 · ИИ-аналитик акима

Роль: R03
Ветка роли: claude/modest-mccarthy-lrl98u
Начато: 2026-10-15 16:24 Астана (11:24 UTC)
База: origin/claude/clever-hypatia-q6ts4g @ e91acb6 (код FINAL-4 a4937462 + пакет раунда 15)
Автопилот: работаю сам до 17 окт 23:59 Астаны. Push в claude/r15-R03 запрещён средой — ветка сессии выше.

**Каждый круг: сначала читать AMENDMENTS.md из ветки пакета** (поправки владельца и координатора; где расходятся с
промптом или VISUAL_BRIEF — права поправка):
    git fetch origin claude/clever-hypatia-q6ts4g
    git show origin/claude/clever-hypatia-q6ts4g:research/round-15/AMENDMENTS.md
Прочитано: П1 (15 окт 17:05 Астаны, «Без ИИ-слопа») — применено 15 окт ~12:40 UTC.

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
- 11:40 UTC checkpoint 1 (a85e4765): agent/civic_assistant/analyst/ (intents, sources, blocks, llm, core) + ask в api.py.
  Три вопроса сценария офлайн: «снег в Нуре + службы» 0,5 с (холодный старт), «службы отстают» 0,15 с, «буран» < 0,01 с.
  Пока нет R17: «отстающие службы» — запасной расчёт по срокам «Картины дня» (сумма просрочек = R08 overdue.count,
  проверено: 5 = 5, открытые 88 = 67 + 21); «буран» — пульс R08 с честной пометкой «штаб не подключён».

- 11:45 UTC checkpoint 2 (5126861f): тесты tests/civic/R03/round15 — 62 passed (без сети, заглушка модели, сверка с R07/R08).
- 11:55 UTC checkpoint 3 (6c7777e2): экран web/civic/assistant/analyst.js/.css + стенд; браузер 1366/1024/375 × ru/kk —
  92 PASS, 0 FAIL (кадры research/round-15-results/R03/screens/).
- 12:01 UTC checkpoint 4 (8a715e8a): проверено ПОДКЛЮЧЕНИЕ в настоящей оболочке (копия ветки + мои patch для R01):
  401 без входа, 200 сотрудник 117 мс, 400 пустой вопрос, /modules ready; #analyst → ответ → «Показать на карте» →
  карточка R07 «Участок ул. Е-308 · 8 человек» (то же 8, что в ответе); Ctrl+K → вопрос → ответ.
  INTEGRATION.txt (patch R01: CIVIC_ASSETS, маршрут, arguments, index.html; patch палитры), i18n_analyst.json (56 ключей).

- 12:09 UTC checkpoint 5 (10f90adc = code_sha поставки): оценка для диплома — results/ASSISTANT_EVAL.md.
  Отложенные прогоны: набор 1 (50) — факты 92 %, сцены 9/9, провокации 9/10; набор 2 (30, записан после правок 1) —
  факты 86,7 % (93,3 % без бага оракула). После общих правок — 100 % на обоих, провокации 10/10. Задержка p95 ≤ 51 мс.
  Тесты: R03 round15 65 passed; вместе с R09/R01/R03 r14 — 842 passed, 9 skipped (нет torch), 1 xfailed.
- 12:12 UTC: DELIVERY.json (code_sha 10f90adc), RUN.txt — поставка готова к B1.

- ~12:40 UTC: ПОПРАВКА П1 «Без ИИ-слопа» применена к экрану R03: пустое состояние и ошибки — один значок набора
  R11 48 px (ic--48, один цвет) + короткий текст + одна кнопка («Главное за сегодня» → «Что сегодня главное?»);
  иллюстрации ill-* убраны; декоративных картинок на экране нет (крупные числа, точки уровня = цвет + число — это данные).
- ~12:40 UTC: ревью R11 круг 1 применено (62e1c63a): термины словаря, короткие чипы, источники названиями.
- ~12:40 UTC: подключение соседей по их функциям «для R03»: R17 board_snapshot / active_incidents (progress вместо задач),
  R12 conflicts_summary, R16 initiatives_summary, R13 board_block; «Открыть …» вызывает BirgeAgencies.openCrisis /
  BirgeWorksCalendar.openConflict. Проверка на их настоящем коде — следующий шаг.

- ~13:05 UTC (650d5ef6 = code_sha DELIVERY): соседи проверены на их настоящем коде (временная копия: R17 e5b834f9,
  R12 8ecfbd37, R16 aef7b79f, R13 455b8950, CIVIC_DEMO=1): оценка 100 % фактов на обоих наборах, провокации 10/10.
  Тесты: 71 passed + 1 skipped (с соседями — 72 passed); с R09/R01/R03 r14 — 848 passed, 10 skipped, 1 xfailed.

## Решения по умолчанию (автопилот)
- Экран аналитика — window.BirgeAnalyst, а не window.BirgeAsk из промпта: BirgeAsk уже занят R13 («Вопрос акиму»,
  web/civic/qa/qa.js, SCREENS.questions в birge.js). Два модуля с одним именем ломали бы друг друга.
- Шлюз R01: маршрут POST assistant/ask → agent.civic_assistant.api.ask (kind=function, staff=True); в arguments() нужна
  строка для ключа assistant.ask (patch — в INTEGRATION.txt). ask принимает и question/lang, и body.

## Следующий шаг
- Каждый круг: find_branches.py — появились ли R17/R12/R16/R13; подключить их функции (имена в sources.py).
- eval_human.py для LOCAL-14 (или NOT_RUN с причиной).

## Вопросы владельцу
- Где кнопка «Спросить Birge» в меню акимата? «Ещё» уже полное (4 пункта) — решение R11; я предложил кнопку в «Картине
  дня» + палитру Ctrl+K (INTEGRATION §3). По умолчанию: раздел #analyst + Ctrl+K.
- Имя экрана: промпт R03 называет window.BirgeAsk, но это имя уже у R13. Сделал window.BirgeAnalyst (решение по
  умолчанию). Если нужно именно BirgeAsk — R13 должен переименовать свой экран.
