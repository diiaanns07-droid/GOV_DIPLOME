# R10 · новые пункты волн 1–2 · 0f5101a3

```
{"root":"/home/user/bf2s4","sha":"0f5101a3","when":"2026-10-12T04:46:22.303Z","sizes":["1366x768","375x812"],"langs":["ru"],"node":"v22.22.0","runtime":{"BirgeNearby":true,"BirgeIdeas":false,"BirgeProjects":false,"BirgeComplaintList":true,"BirgeAsk":false,"BirgeQuestions":false,"BirgeShell":true}}
```

Итого: PASS 5, FAIL 2, ЖДЁТ 0, NOT_RUN 0

| Пункт | Что | Владелец | Готово, когда | Состояние |
|---|---|---|---|---|
| W1-8 | Мат и оскорбления | R04 (+R07, R09 вывод) | в публичных местах нет мата, текст для акимата не теряется | **FAIL** |
| W1-9 | Разъединить дубли | R04 + R09 (+R07 кнопка) | неверное «Я тоже» исправляется одним действием | **FAIL** |

| Пункт | Где | Проверка | Итог | Подробно | Кадр |
|---|---|---|---|---|---|
| W1-8 | сборка | Мат и оскорбления: есть в сборке — проверяю | **INFO** | {"static":{"emergency":["web/civic/feedback/categories_v2.js: emergency_phone","web/civic/feedback/complaint-strings.js: complaint.emergency","web/civic/feedback/complaint.js: emergency_phone","ui/civic_feedback/v2/categ |  |
| W1-8 | API | не сотрудникам (карточка, карта, похожие, «Мои обращения»): грубых слов нет, в тексте — звёздочки | **PASS** | {"raw_in":{"public":false,"heat":false,"similar":false,"mine":false},"masked_in_mine":true} |  |
| W1-8 | API | акимат видит оригинал и пометку «содержит грубые слова» (moderation.rude) | **PASS** | {"login":true,"moderation":{"rude":true,"count":2,"kinds":["mat"],"version":"r04-profanity-1"}} |  |
| W1-8 | 1366-ru | карточка места (R07) у акимата: пометка «содержит грубые слова» у текста жителя | **PASS** | {"card":true,"mark":true} | 1366-ru-W1-8-card.jpg |
| W1-8 | 1366-ru | «Обращения» (R09): пометка «содержит грубые слова» у такого обращения | **FAIL** | {"opened":true,"mark":false} | 1366-ru-W1-8-inbox.jpg |
| W1-9 | сборка | Разъединить дубли: есть в сборке — проверяю | **INFO** | {"static":{"emergency":["web/civic/feedback/categories_v2.js: emergency_phone","web/civic/feedback/complaint-strings.js: complaint.emergency","web/civic/feedback/complaint.js: emergency_phone","ui/civic_feedback/v2/categ |  |
| W1-9 | API | сотрудник отмечает дубль: люди дубля переходят к исходной | **PASS** | {"http":200,"before":1,"after":2} |  |
| W1-9 | 1366-ru | карточка места (R07): «Объединено с этим» → «Это разные проблемы» разделяет одним действием | **FAIL** | {"card":true,"block":false,"clicked":false,"duplicate_of":"c-b06e6bb6ca4a3737"} | 1366-ru-W1-9-card.jpg |
| W1-9 | API | «Это разные проблемы» (POST unduplicate): дубль снова отдельный, число людей у исходной пересчитано | **PASS** | {"http":200,"people":[1,2,1],"duplicate_of":null} |  |
