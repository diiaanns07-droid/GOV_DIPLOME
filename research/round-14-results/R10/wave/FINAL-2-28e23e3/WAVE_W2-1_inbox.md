# R10 · новые пункты волн 1–2 · 28e23e3d

```
{"root":"<worktree 28e23e3>","sha":"28e23e3d","when":"2026-10-11T22:23:02.160Z","sizes":["1366x768"],"langs":["ru"],"node":"v22.22.0","runtime":{"BirgeNearby":true,"BirgeIdeas":false,"BirgeProjects":false,"BirgeComplaintList":true,"BirgeAsk":false,"BirgeShell":true}}
```

Итого: PASS 7, FAIL 5, ЖДЁТ 0, NOT_RUN 0

| Пункт | Что | Владелец | Готово, когда | Состояние |
|---|---|---|---|---|
| W2-1 | Центральная сцена: «Исправлено — проверьте» → житель подтвердил → зелёный «проверено» | R09, R07, R08 | исправили → житель подтвердил → объект зелёный «проверено»; при «осталось» — снова красный, история сохранена | **FAIL** |

| Пункт | Где | Проверка | Итог | Подробно | Кадр |
|---|---|---|---|---|---|
| W2-1 | сборка | Центральная сцена: «Исправлено — проверьте» → житель подтвердил → зелёный «проверено»: есть в сборке — проверяю | **INFO** | {"static":{"emergency":["web/civic/feedback/categories_v2.js: emergency_phone","web/civic/feedback/complaint-strings.js: complaint.emergency","web/civic/feedback/complaint.js: emergency_phone","ui/civic_feedback/v2/categ |  |
| W2-1 | 1366-ru | сотрудник (R07 + форма R09): «Отметить исправленным» → «Что сделали», «Фото «после»», «Увидят N человек» → «Сообщить жителям» | **FAIL** | {"logged":true,"card":true,"fix":true,"whatBox":false,"photo":false,"willSee":false,"send":false,"primary":[]} | 1366-ru-W2-1-1-staff.jpg |
| W2-1 | 1366-ru | запись (R09): «служба сообщила об устранении» — status fixed, этап reported, ещё не «проверено» | **PASS** | {"via":"интерфейс","status":"fixed","resolution":"reported"} |  |
| W2-1 | 1366-ru | карта (R07): цель — «Служба сообщила об устранении» (светло-зелёный с пунктиром), не зелёный | **FAIL** | {"heat":{"level":"fixed","weight":0,"count":3,"fixed_until":"2026-10-19T03:20:55+05:00","state":"fixed","fixed_kind":null,"color":"#639922","reopened":null,"derived":"fixed"},"card_text":false} | 1366-ru-W2-1-2-reported.jpg |
| W2-1 | 1366-ru | «Я тоже» (R09, другое устройство): в «Моих обращениях» блок «Ждут вашей проверки» и «Да, исправлено» | **PASS** | {"opened":true,"wait":true,"yes":true} | 1366-ru-W2-1-3-metoo.jpg |
| W2-1 | 1366-ru | автор (R09): «Проблема решена?» — «Да, исправлено» (одна главная) / «Проблема осталась» / «Не могу проверить» | **PASS** | {"opened":true,"yes":true,"no":true,"cant":true,"yesPrimary":true,"primary":["Да, исправлено"]} | 1366-ru-W2-1-4-verify.jpg |
| W2-1 | 1366-ru | «Да, исправлено» (R09) → «Спасибо, ответ учтён», запись — «проверено жителями» | **PASS** | {"thanks":true,"status":"fixed","resolution":"verified","history":["new","in_progress","fixed"]} | 1366-ru-W2-1-5-verified.jpg |
| W2-1 | 1366-ru | карта (R07): цель зелёная — «Проверено жителями» | **FAIL** | {"heat":{"level":"fixed","weight":0,"count":3,"fixed_until":"2026-10-19T03:20:55+05:00","state":"fixed","fixed_kind":null,"color":"#639922","reopened":null,"derived":"fixed"},"card":true,"verified":false} | 1366-ru-W2-1-6-akimat.jpg |
| W2-1 | 1366-ru | «Картина дня» (R08): сколько исправлений проверили жители | **PASS** | {"day":true,"counter":true} | 1366-ru-W2-1-7-day.jpg |
| W2-1 | 1366-ru | «Проблема осталась» (R09) → «Обращение снова в работе, история сохранена»: та же запись снова «в работе», этап reopened, история сохранена | **PASS** | {"staff_fix":{"ok":true,"body":{"status":"fixed","what_done":"Заменили крышу павильона"}},"button":true,"toast":true,"status":"in_progress","resolution":"reopened","history":["new","in_progress","fixed","in_progress"]} | 1366-ru-W2-1-8-reopened.jpg |
| W2-1 | 1366-ru | карта (R07): цель снова красная, в карточке «вернули жители» | **FAIL** | {"heat":{"level":1,"weight":1,"count":1,"fixed_until":null,"state":"active","fixed_kind":null,"color":"#FAC775","reopened":null,"derived":"open"},"card":true,"mark":false} | 1366-ru-W2-1-9-reopened-card.jpg |
| W2-2 | 1366-ru | сотрудник через «Обращения»: «Изменить» → 3 поля «Кто отвечает», «Следующий шаг», «Когда устраним (ориентир)» | **PASS** | {"logged":true,"opened":true,"row":true,"edit":true,"fields":[true,true,true]} | 1366-ru-W2-2-inbox-passport.jpg |
| W2-1 | 1366-ru | сотрудник через «Обращения» (форма R09): «Что сделали» + «Фото «после»» + «Увидят N человек» → «Сообщить жителям» → этап reported, строка сохранена | **FAIL** | {"logged":true,"opened":true,"row":true,"whatBox":true,"photo":true,"willSee":true,"button":true,"enabled":true,"send":true,"calls":[],"errors":["console: Fetch API cannot load blob:http://127.0.0.1:42549/ca951124-89b3-4 | 1366-ru-W2-1-inbox-form.jpg |
