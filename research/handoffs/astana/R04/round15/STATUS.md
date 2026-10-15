# R04 · раунд 15 · STATUS

Роль: R04 (ИИ для ведомств: выбор служб, черновики ответов, модерация текстов сообщества)
Ветка роли: claude/gifted-maxwell-i66wwi (ветка сессии; push в claude/r15-R04 средой не разрешён)
Начато: 2026-10-15 16:25 Астана (11:25 UTC)
База: origin/claude/clever-hypatia-q6ts4g @ e91acb69 (FINAL-4 a4937462 + пакет раунда 15)
Прошлая передача: claude/r14-R04 (в FINAL-4 — 8e2b2ae)

## План (prompts/R04.txt, по порядку)
1. route(text?, category?, subtopic?, point?) → services[] + joint + model_version; набор 150+ фраз ru/kk/смешанных.
2. reply_draft(complaint_id | text, status, lang) — шаблоны ru/kk, факты кодом из записи R09.
3. moderate(text, lang?) → {text_public, flags} + POST /moderate: мат, телефоны, ИИН, e-mail, карты.
4. similar_initiatives(text, point, days) для R16 на основе поиска дублей.
5. Тесты без сети, скорость (route < 30 мс, moderate < 5 мс), DELIVERY с числами, INTEGRATION.

## Сделано
- (claim) ветка занята, STATUS создан.
- CP1 16:50: набор route_cases.json (208 фраз ru/kk/смешанных/латиница; dev 114 / test 94; совместных 92) зафиксирован
  коммитом ДО правил совместных случаев — протокол для диплома (правила подбираются только по dev).
- Продолжение: scheduled task trig_01M5zb65s5mTuk6bSDHfWwyq (раз в час, :25) в эту сессию; удалить после 17 окт 23:59 Астаны.

## Дальше
- Задача 1: ui/civic_ml_api/routing.py — route(); затем оценка на dev.
- Шлюз FINAL-4: arguments() не знает ключей route/reply_draft/moderate (вернёт {}): patch для R01 — в INTEGRATION.txt.

## Вопросы владельцу
- (пока нет)

## SHA
- claim: см. git log этой ветки
