# R10 · новые пункты волн 1–2 · a002dc7e

```
{"root":"/home/user/bm11","sha":"a002dc7e","when":"2026-10-12T22:47:28.710Z","sizes":["1366x768","375x812"],"langs":["ru","kk"],"node":"v22.22.0","runtime":{"BirgeNearby":true,"BirgeIdeas":true,"BirgeProjects":false,"BirgeComplaintList":true,"BirgeAsk":true,"BirgeQuestions":false,"BirgeShell":true}}
```

Итого: PASS 15, FAIL 0, ЖДЁТ 0, NOT_RUN 1

| Пункт | Что | Владелец | Готово, когда | Состояние |
|---|---|---|---|---|
| W2-6 | QR-паспорт объекта | R12 (+R01 ссылка) | Скан распечатки телефоном → карточка этой остановки | **частично** |

| Пункт | Где | Проверка | Итог | Подробно | Кадр |
|---|---|---|---|---|---|
| W2-6 | сборка | QR-паспорт объекта: есть в сборке — проверяю | **INFO** | {"static":{"emergency":["web/civic/feedback/categories_v2.js: emergency_phone","web/civic/feedback/complaint-strings.js: complaint.emergency","web/civic/feedback/complaint.js: emergency_phone","ui/civic_feedback/v2/categ |  |
| W2-6 | 1366-ru | /?report=<id>: язык не сменился, вид «Житель» на этот заход, сохранённый вид не перезаписан | **PASS** | {"lang":"ru","saved_mode":"akimat","saved_lang":"ru","resident_pressed":true} | 1366-ru-W2-6-report-shell.jpg |
| W2-6 | 1366-kk | /?report=<id>: язык не сменился, вид «Житель» на этот заход, сохранённый вид не перезаписан | **PASS** | {"lang":"kk","saved_mode":"akimat","saved_lang":"kk","resident_pressed":true} | 1366-kk-W2-6-report-shell.jpg |
| W2-6 | 375-ru | /?report=<id>: язык не сменился, вид «Житель» на этот заход, сохранённый вид не перезаписан | **PASS** | {"lang":"ru","saved_mode":"akimat","saved_lang":"ru","resident_pressed":true} | 375-ru-W2-6-report-shell.jpg |
| W2-6 | 375-kk | /?report=<id>: язык не сменился, вид «Житель» на этот заход, сохранённый вид не перезаписан | **PASS** | {"lang":"kk","saved_mode":"akimat","saved_lang":"kk","resident_pressed":true} | 375-kk-W2-6-report-shell.jpg |
| W2-6 | 1366-kk | ссылка с ?lang=ru не меняет сохранённый ҚАЗ: следующий заход — снова ҚАЗ | **PASS** | {"lang":"kk","saved":"kk"} |  |
| W2-6 | 1366-ru | /?report=<id> → карточка «Хан Шатыр»: одна главная «Я тоже», «Сообщить о другом», «Подробнее» | **PASS** | {"card":true,"primary":["Я тоже"],"metoo":true,"other":true,"more":true} | 1366-ru-W2-6-card.jpg |
| W2-6 | 1366-ru | «Сообщить о другом» открывает мастер жалобы сразу на шаге текста с этим местом | **PASS** | {"textbox":true} |  |
| W2-6 | 1366-kk | /?report=<id> → карточка «Хан Шатыр»: одна главная «Мен де», «Басқа мәселе туралы хабарлау», «Толығырақ» | **PASS** | {"card":true,"primary":["Мен де"],"metoo":true,"other":true,"more":true} | 1366-kk-W2-6-card.jpg |
| W2-6 | 1366-kk | «Сообщить о другом» открывает мастер жалобы сразу на шаге текста с этим местом | **PASS** | {"textbox":true} |  |
| W2-6 | 375-ru | /?report=<id> → карточка «Хан Шатыр»: одна главная «Я тоже», «Сообщить о другом», «Подробнее» | **PASS** | {"card":true,"primary":["Я тоже"],"metoo":true,"other":true,"more":true} | 375-ru-W2-6-card.jpg |
| W2-6 | 375-ru | «Сообщить о другом» открывает мастер жалобы сразу на шаге текста с этим местом | **PASS** | {"textbox":true} |  |
| W2-6 | 375-kk | /?report=<id> → карточка «Хан Шатыр»: одна главная «Мен де», «Басқа мәселе туралы хабарлау», «Толығырақ» | **PASS** | {"card":true,"primary":["Мен де"],"metoo":true,"other":true,"more":true} | 375-kk-W2-6-card.jpg |
| W2-6 | 375-kk | «Сообщить о другом» открывает мастер жалобы сразу на шаге текста с этим местом | **PASS** | {"textbox":true} |  |
| W2-6 | 375-ru | неизвестный id → «Объект не найден» и кнопка «На карту» (не пустая карта) | **PASS** | {"not_found":true,"to_map":true} | 375-ru-W2-6-not-found.jpg |
| W2-6 | лист | лист для печати: QR ≥ 6 см, крупное название, «Объект № …», призыв на kk и ru, домен, стиль печати; без чисел жалоб | **PASS** | {"sheet":"/civic/qr/print.html?ids=osm-node-4109037549","qr":1,"qr_px":280,"big_text":1,"number":true,"call_ru":true,"call_kk":true,"call_kk_r11":true,"domain":true,"print":true,"counts":false} | 1366-ru-W2-6-sheet.jpg |
| W2-6 | лист | скан распечатки телефоном открывает карточку этой остановки; подмена ссылки | **NOT_RUN** | "только на устройстве — Codex/владелец (камера телефона); подмена ссылки — R15" |  |
