# R10 · новые пункты волн 1–2 · 0f5101a3

```
{"root":"/home/user/bf2s4","sha":"0f5101a3","when":"2026-10-12T04:50:03.235Z","sizes":["1366x768","375x812"],"langs":["ru","kk"],"node":"v22.22.0","runtime":{"BirgeNearby":true,"BirgeIdeas":false,"BirgeProjects":false,"BirgeComplaintList":true,"BirgeAsk":false,"BirgeQuestions":false,"BirgeShell":true}}
```

Итого: PASS 20, FAIL 0, ЖДЁТ 0, NOT_RUN 0

| Пункт | Что | Владелец | Готово, когда | Состояние |
|---|---|---|---|---|
| W2-3 | Один ответ всем «Я тоже» + W2-10 «Что изменилось» | R09 | одно действие оператора → обновление у всех; житель видит смысл участия | **PASS** |
| W2-5 | «Нужно решение акима» + W2-8 «Пульс района» | R08 (+R13) | 1–3 решения; 1–5 тревог с причиной и ссылкой на карту | **PASS** |

| Пункт | Где | Проверка | Итог | Подробно | Кадр |
|---|---|---|---|---|---|
| W2-3 | сборка | Один ответ всем «Я тоже» + W2-10 «Что изменилось»: есть в сборке — проверяю | **INFO** | {"static":{"emergency":["web/civic/feedback/categories_v2.js: emergency_phone","web/civic/feedback/complaint-strings.js: complaint.emergency","web/civic/feedback/complaint.js: emergency_phone","ui/civic_feedback/v2/categ |  |
| W2-3 | API | одно обновление сотрудника → его видят автор и все «Я тоже» (в «Что изменилось») | **PASS** | {"http":200,"notified":3,"seen":{"автор":true,"«Я тоже» 1":true,"«Я тоже» 2":true}} |  |
| W2-10 | API | «Что изменилось»: события по своим обращениям с id (status, note, …) и итог | **PASS** | {"kinds":["note","status"],"summary":{"verified":0,"waiting":1,"total":1}} |  |
| W2-10 | 1366-ru | житель («Я тоже»): «Мои обращения» → «Что изменилось» с обновлением сотрудника | **PASS** | {"opened":true,"box":true,"text":true} | 1366-ru-W2-10-changes.jpg |
| W2-10 | 1366-ru | уведомление открывает конкретное изменение (#mine/event=…), а не главную | **PASS** | {"event":"B-0003.note.20261012T094827","row":true,"card":true} | 1366-ru-W2-10-event.jpg |
| W2-10 | 1366-kk | житель («Я тоже»): «Мои обращения» → «Что изменилось» с обновлением сотрудника | **PASS** | {"opened":true,"box":true,"text":true} | 1366-kk-W2-10-changes.jpg |
| W2-10 | 1366-kk | уведомление открывает конкретное изменение (#mine/event=…), а не главную | **PASS** | {"event":"B-0003.note.20261012T094827","row":true,"card":true} | 1366-kk-W2-10-event.jpg |
| W2-10 | 375-ru | житель («Я тоже»): «Мои обращения» → «Что изменилось» с обновлением сотрудника | **PASS** | {"opened":true,"box":true,"text":true} | 375-ru-W2-10-changes.jpg |
| W2-10 | 375-ru | уведомление открывает конкретное изменение (#mine/event=…), а не главную | **PASS** | {"event":"B-0003.note.20261012T094827","row":true,"card":true} | 375-ru-W2-10-event.jpg |
| W2-10 | 375-kk | житель («Я тоже»): «Мои обращения» → «Что изменилось» с обновлением сотрудника | **PASS** | {"opened":true,"box":true,"text":true} | 375-kk-W2-10-changes.jpg |
| W2-10 | 375-kk | уведомление открывает конкретное изменение (#mine/event=…), а не главную | **PASS** | {"event":"B-0003.note.20261012T094827","row":true,"card":true} | 375-kk-W2-10-event.jpg |
| W2-5 | сборка | «Нужно решение акима» + W2-8 «Пульс района»: есть в сборке — проверяю | **INFO** | {"static":{"emergency":["web/civic/feedback/categories_v2.js: emergency_phone","web/civic/feedback/complaint-strings.js: complaint.emergency","web/civic/feedback/complaint.js: emergency_phone","ui/civic_feedback/v2/categ |  |
| W2-5 | API | «Нужно решение акима»: 1–3 решения, у каждого — проблема, что блокирует, 2 варианта, нужное решение (ru и kk) | **PASS** | {"available":true,"n":3,"complete":3,"source":"example","demo":true} |  |
| W2-8 | API | «Пульс района»: 1–5 тревог с причиной (рост к обычному уровню) и местом на карте | **PASS** | {"available":true,"n":5,"kinds":["spike_city","spike_new","spike","spike","spike"],"method":{"min_reports":5,"spike_ratio":2,"base_weeks":4,"min_metoo_week":8}} |  |
| W2-5 | 1366-ru | «Картина дня»: блок «Нужно решение акима» виден; демо помечено «пример» | **PASS** | {"day":true,"block":true,"demoMark":true} | 1366-ru-W2-5-decisions.jpg |
| W2-8 | 1366-ru | «Картина дня»: «Пульс района» — 1–5 тревог, у тревоги ссылка «на карте» открывает карту | **PASS** | {"rows":5,"link":true,"toMap":true} | 1366-ru-W2-8-pulse.jpg |
| W2-5 | 1366-kk | «Картина дня»: блок «Әкімнің шешімі керек» виден; демо помечено «пример» | **PASS** | {"day":true,"block":true,"demoMark":true} | 1366-kk-W2-5-decisions.jpg |
| W2-8 | 1366-kk | «Картина дня»: «Аудан пульсі» — 1–5 тревог, у тревоги ссылка «на карте» открывает карту | **PASS** | {"rows":5,"link":true,"toMap":true} | 1366-kk-W2-8-pulse.jpg |
| W2-5 | 375-ru | «Картина дня»: блок «Нужно решение акима» виден; демо помечено «пример» | **PASS** | {"day":true,"block":true,"demoMark":true} | 375-ru-W2-5-decisions.jpg |
| W2-8 | 375-ru | «Картина дня»: «Пульс района» — 1–5 тревог, у тревоги ссылка «на карте» открывает карту | **PASS** | {"rows":5,"link":true,"toMap":true} | 375-ru-W2-8-pulse.jpg |
| W2-5 | 375-kk | «Картина дня»: блок «Әкімнің шешімі керек» виден; демо помечено «пример» | **PASS** | {"day":true,"block":true,"demoMark":true} | 375-kk-W2-5-decisions.jpg |
| W2-8 | 375-kk | «Картина дня»: «Аудан пульсі» — 1–5 тревог, у тревоги ссылка «на карте» открывает карту | **PASS** | {"rows":5,"link":true,"toMap":true} | 375-kk-W2-8-pulse.jpg |
