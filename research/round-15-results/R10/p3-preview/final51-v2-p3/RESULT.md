# R10 · сценарий v2 · сцены 7–9 · e8d6cae6

```
{"root":"/tmp/claude-0/-home-user-GOV-DIPLOME/62d68526-d416-54f0-b206-35e3353bc4a5/scratchpad/builds/r01-final51","sha":"e8d6cae6","world":true,"seeds":["seed-demo","seed-r14-demo"],"sizes":["1366x768"],"langs":["ru"],"when":"2026-10-16T13:03:20.524Z","machine":{"cpu":"Intel(R) Xeon(R) Processor @ 2.10GHz","cores":4,"mem_gb":16,"platform":"linux 6.18.44-fc-v139","node":"v22.22.0"},"total_ms":103698}
```

Итого: PASS 86, FAIL 0, NOT_RUN 4

| Слой | Сцена | Проверка | Итог | Подробно | Владелец | Кадр |
|---|---|---|---|---|---|---|
| мир | 0 | файл демо-мира R02 и scenes (сцены 7–9) | **PASS** | {"scenes":["step2","scene7","scene8","scene9"],"counts":{"yards":32,"complaints":743,"works":43,"planned_conflicts":5,"ideas":12,"initiatives":10,"incidents":3,"meetings":3,"questions":17,"events":4}} | R02 |  |
| API | 7 | «Мой двор»: название, соседи — число, проблемы и инициативы двора | **PASS** | {"label":"Двор: BI City Tokyo","members":37,"problems":1,"initiatives":2} | R16 |  |
| API | 7 | в «Моём дворе» есть инициатива сцены i-w15-01 | **PASS** | {"items":["i-w15-01"]} | R16 |  |
| API | 7 | «Я приду» до сцены = 14 (демо-мир) | **PASS** | {"joined":14} | R16 + R02 |  |
| API | 7 | «Я приду» → 15 | **PASS** | {"status":200,"joined":15} | R16 |  |
| API | 7 | акимат «Поддержать: мешки и вывоз» → у инициативы «Поддержано акиматом» | **PASS** | {"status":200,"support":{"by_akimat":true,"inventory":true,"pickup_service":"waste","note":"Мешки и вывоз в 14:00","at":"2026-10-16T18:01:47+05:00"}} | R16 |  |
| API | 7 | сделанная инициатива: статус done, отчёт «Сделано вместе: N соседей» | **PASS** | {"status":"done","report":"Посадили 6 саженцев и покрасили скамейки — сделано вместе: 15 соседей","joined":15} | R16 |  |
| API | 8 | ИИ: «Нужны 2 службы» — маршрутизация жалобы сцены (вода + дороги) | **PASS** | {"services":["water","road"],"joint":true} | R04 |  |
| API | 8 | сотрудник: совместное исполнение — 2 службы у обращения | **PASS** | {"status":200} | R09 |  |
| API | 8 | сотрудник: часть «Водоканал — сделано» | **PASS** | {"status":200} | R09 |  |
| API | 8 | у жителя паспорт с двумя службами и их статусами | **PASS** | {"services":["water:done","road:todo"],"shape":"joint.services"} | R09 |  |
| API | 8 | «Штаб ведомств»: табло служб (строки служб, без имён людей) | **PASS** | {"rows":20} | R17 |  |
| API | 8 | «Календарь работ»: конфликт «асфальт раньше сетей — копаем дважды» и совет ru/kk | **PASS** | {"found":true,"n":2,"kind":"dig_after_surface"} | R12 |  |
| API | 9 | «Картина дня»: пульс «Снег в Нуре ×N» | **PASS** | {"pulse":["spike_city:snow_ice:-:×4","spike:transport:nura:×6.6","spike:lighting:nura:×5.3"]} | R08 + R02 |  |
| API | 9 | «Картина дня»: у тревоги «Снег» ссылка «Открыть кризисный штаб» (R17) | **PASS** | {"crisis":{"link":"/#agencies/crisis/inc-w15-buran","incident":"inc-w15-buran","kind":"blizzard"}} | R08 + R17 |  |
| API | 9 | кризисный штаб: зона «Нура», 4 службы с задачами, обновления ru/kk | **PASS** | {"status":"active","tasks":["street_cleaning","transport","heating","akimat"],"updates":3} | R17 |  |
| API | 9 | житель зоны получает обновления кризиса | **PASS** | {"n":3} | R17 |  |
| API | 9 | «Хроника города»: кадры недели с датой (и отметка «Буран») | **PASS** | {"frames":8,"annotations":true} | R07 |  |
| UI 1366-ru | 0 | оболочка: разделы раунда 15 (IA_ROUND15) | **PASS** | {"ids":["map","day","inbox","agencies","more","mine","yard","ideas","projects","together","meetings","analyst","board","qr"],"globals":["BirgeTogether","BirgeAgencies","BirgeWorksCalendar","BirgeRepla | R01 |  |
| UI 1366-ru | 7 | «Мой двор» открыт по адресу #yard/yard-1454082640 | **PASS** | {"title":"Мой двор","chars":752,"section":"yard"} | R16 | 1366-ru-7-yard.jpg |
| UI 1366-ru | 7 | в шапке двора — название и 3 числа (соседей · проблем · инициатив) | **PASS** | {"label":"Двор: BI City Tokyo"} | R16 |  |
| UI 1366-ru | 7 | нет прокрутки вбок | **PASS** | {"scrollW":1366,"w":1366} | R16 | 1366-ru-7-yard.jpg |
| UI 1366-ru | 7 | нет ключей перевода и технических слов | **PASS** | {"raw":[],"tech":[]} | R16 |  |
| UI 1366-ru | 7 | шрифт ≥ 13 px | **PASS** | {"tiny":0,"ex":[]} | R16 |  |
| UI 1366-ru | 7 | зоны нажатия ≥ 40 px (цель 44) | **PASS** | {"under40":[]} | R16 |  |
| UI 1366-ru | 7 | контраст текста ≥ 4,5:1 | **PASS** | {"n":0,"ex":[]} | R16 |  |
| UI 1366-ru | 7 | в «Обзоре» — инициатива «Субботник во дворе» | **PASS** | "" | R16 |  |
| UI 1366-ru | 7 | нет связи: понятное сообщение и «Повторить», после связи данные вернулись (#yard/yard-1454082640) | **PASS** | {"message":"Мой двор\nНазад\n\nНе удалось загрузить\n\nПроверьте связь и повторите.\n\nПовторить","retry":true,"recovered":true} | R16 | 1366-ru-7-offline.jpg |
| UI 1366-ru | 7 | карточка инициативы → «Я приду» → счётчик +1 (по миру 14 → 15) | **PASS** | {"pressed":true,"before":15,"after":16} | R16 | 1366-ru-7-join.jpg |
| UI 1366-ru | 8 | житель: «Мои обращения» — две службы и статус каждой (совместное исполнение) | **PASS** | {"metoo":200,"line":{"text":"Работают 2 службы: Водоканал — сделано Дорожная служба — ждёт","parts":["done","reported_fixed","todo","new"]}} | R09 | 1366-ru-8-mine-joint.jpg |
| UI 1366-ru | 8m | нет прокрутки вбок | **PASS** | {"scrollW":1366,"w":1366} | R09 | 1366-ru-8-mine-joint.jpg |
| UI 1366-ru | 8m | нет ключей перевода и технических слов | **PASS** | {"raw":[],"tech":[]} | R09 |  |
| UI 1366-ru | 8m | шрифт ≥ 13 px | **PASS** | {"tiny":0,"ex":[]} | R09 |  |
| UI 1366-ru | 8m | зоны нажатия ≥ 40 px (цель 44) | **PASS** | {"under40":[]} | R09 |  |
| UI 1366-ru | 8m | контраст текста ≥ 4,5:1 | **PASS** | {"n":0,"ex":[]} | R09 |  |
| UI 1366-ru | 8 | вход сотрудника для сцен 8–9 | **PASS** | {"status":200} | R01 |  |
| UI 1366-ru | 8 | «Штаб ведомств» → «Табло» открыт | **PASS** | {"title":"Штаб ведомств","chars":1298} | R17 | 1366-ru-8-board.jpg |
| UI 1366-ru | 8 | нет прокрутки вбок | **PASS** | {"scrollW":1366,"w":1366} | R17 | 1366-ru-8-board.jpg |
| UI 1366-ru | 8 | нет ключей перевода и технических слов | **PASS** | {"raw":[],"tech":[]} | R17 |  |
| UI 1366-ru | 8 | шрифт ≥ 13 px | **PASS** | {"tiny":0,"ex":[]} | R17 |  |
| UI 1366-ru | 8 | зоны нажатия ≥ 40 px (цель 44) | **PASS** | {"under40":[]} | R17 |  |
| UI 1366-ru | 8 | контраст текста ≥ 4,5:1 | **PASS** | {"n":0,"ex":[]} | R17 |  |
| UI 1366-ru | 8 | нет связи: понятное сообщение и «Повторить», после связи данные вернулись (#agencies/board) | **PASS** | {"message":"Штаб ведомств\nШтаб ведомств\nТабло\nСовместные\nПередачи\nКалендарь работ\nКризис\n· Идёт\n\nНет связи с сер","retry":true,"recovered":true} | R17 | 1366-ru-8-offline.jpg |
| UI 1366-ru | 8 | «Календарь работ» открыт | **PASS** | {"title":"Штаб ведомств","chars":2041} | R12 | 1366-ru-8-calendar.jpg |
| UI 1366-ru | 8c | нет прокрутки вбок | **PASS** | {"scrollW":1366,"w":1366} | R12 | 1366-ru-8-calendar.jpg |
| UI 1366-ru | 8c | нет ключей перевода и технических слов | **PASS** | {"raw":[],"tech":[]} | R12 |  |
| UI 1366-ru | 8c | шрифт ≥ 13 px | **PASS** | {"tiny":0,"ex":[]} | R12 |  |
| UI 1366-ru | 8c | зоны нажатия ≥ 40 px (цель 44) | **PASS** | {"under40":[]} | R12 |  |
| UI 1366-ru | 8c | контраст текста ≥ 4,5:1 | **PASS** | {"n":0,"ex":[]} | R12 |  |
| UI 1366-ru | 8 | конфликт сцены «копаем дважды» (улица Баян Сулу) по ссылке #works-calendar/cf-w15-01: улица и совет видны | **PASS** | {"advice":"Сначала замените сети, потом кладите асфальт. Водо","street":"Баян Сулу","seenAdvice":true,"seenStreet":true} | R12 | 1366-ru-8-conflict.jpg |
| UI 1366-ru | 9 | «Картина дня»: у пульса «Снег» кнопка «Открыть кризисный штаб» | **PASS** | {"button":true,"text":"Открыть кризисный штаб"} | R08 + R17 | 1366-ru-9-day.jpg |
| UI 1366-ru | 9 | подпись кнопки штаба — термин словаря R11 (board.crisis.open) | **PASS** | {"shown":"Открыть кризисный штаб","r11":"Открыть кризисный штаб"} | R08 + R11 |  |
| UI 1366-ru | 9 | кризис inc-w15-buran: штаб «Буран в Нуре» открыт по адресу | **PASS** | {"addr":"#agencies/crisis/inc-w15-buran","title":"Штаб ведомств","chars":1376} | R17 | 1366-ru-9-crisis.jpg |
| UI 1366-ru | 9 | в штабе видны задачи служб (4 в демо-мире) | **PASS** | {"seen":4,"of":4} | R17 |  |
| UI 1366-ru | 9 | нет прокрутки вбок | **PASS** | {"scrollW":1366,"w":1366} | R17 | 1366-ru-9-crisis.jpg |
| UI 1366-ru | 9 | нет ключей перевода и технических слов | **PASS** | {"raw":[],"tech":[]} | R17 |  |
| UI 1366-ru | 9 | шрифт ≥ 13 px | **PASS** | {"tiny":0,"ex":[]} | R17 |  |
| UI 1366-ru | 9 | зоны нажатия ≥ 40 px (цель 44) | **PASS** | {"under40":[]} | R17 |  |
| UI 1366-ru | 9 | контраст текста ≥ 4,5:1 | **PASS** | {"n":0,"ex":[]} | R17 |  |
| UI 1366-ru | * | консоль без ошибок (кроме шума среды) | **PASS** | [] | по тексту ошибки |  |
| UI board 1920-ru | 9 | открыта с данными (вход сотрудника принят) | **PASS** | {"state":"ready","login_form":false} | R08 | board-1920-ru.jpg |
| UI board 1920-ru | 9 | без прокрутки на весь экран | **PASS** | {"scrollH":1080,"h":1080,"scrollW":1920,"w":1920} | R08 | board-1920-ru.jpg |
| UI board 1920-ru | 9 | тёмная тема только здесь (.bk-dark, тёмный фон) | **PASS** | {"dark":true,"bg_luminance":0.005} | R08 | board-1920-ru.jpg |
| UI board 1920-ru | 9 | крупные живые числа (≥ 40 px) — читается с 3 м | **PASS** | {"big_numbers":4} | R08 | board-1920-ru.jpg |
| UI board 1920-ru | 9 | мелкого текста нет (≥ 14 px на большом экране) | **PASS** | {"min_font":21.1,"smallest":[[21.1,"Весь город"],[21.1,"Пример"],[21.1,"Пятница, 16 октября"],[21.1,"ҚАЗ"]]} | R08 | board-1920-ru.jpg |
| UI board 1920-ru | 9 | контраст текста ≥ 4,5:1 на тёмном | **PASS** | {"n":0,"ex":[]} | R08 | board-1920-ru.jpg |
| UI board 1920-ru | 9 | пометка «Пример» на синтетике | **PASS** | "" | R08 | board-1920-ru.jpg |
| UI board 1920-ru | 9 | «На весь экран» и «← В Birge» | **PASS** | {"full":true,"back":true} | R08 | board-1920-ru.jpg |
| UI board 1920-ru | 9 | консоль без ошибок | **PASS** | [] | R08 | board-1920-ru.jpg |
| UI board 1366-ru | 9 | открыта с данными (вход сотрудника принят) | **PASS** | {"state":"ready","login_form":false} | R08 | board-1366-ru.jpg |
| UI board 1366-ru | 9 | без прокрутки на весь экран | **PASS** | {"scrollH":768,"h":768,"scrollW":1366,"w":1366} | R08 | board-1366-ru.jpg |
| UI board 1366-ru | 9 | тёмная тема только здесь (.bk-dark, тёмный фон) | **PASS** | {"dark":true,"bg_luminance":0.005} | R08 | board-1366-ru.jpg |
| UI board 1366-ru | 9 | крупные живые числа (≥ 40 px) — читается с 3 м | **PASS** | {"big_numbers":4} | R08 | board-1366-ru.jpg |
| UI board 1366-ru | 9 | мелкого текста нет (≥ 14 px на большом экране) | **PASS** | {"min_font":15,"smallest":[[15,"Весь город"],[15,"Пример"],[15,"Пятница, 16 октября"],[15,"ҚАЗ"]]} | R08 | board-1366-ru.jpg |
| UI board 1366-ru | 9 | контраст текста ≥ 4,5:1 на тёмном | **PASS** | {"n":0,"ex":[]} | R08 | board-1366-ru.jpg |
| UI board 1366-ru | 9 | пометка «Пример» на синтетике | **PASS** | "" | R08 | board-1366-ru.jpg |
| UI board 1366-ru | 9 | «На весь экран» и «← В Birge» | **PASS** | {"full":true,"back":true} | R08 | board-1366-ru.jpg |
| UI board 1366-ru | 9 | консоль без ошибок | **PASS** | [] | R08 | board-1366-ru.jpg |
| UI show-ru | S | режим показа ?show=1 включён (html[data-birge-show]) | **PASS** | "" | R01 |  |
| UI show-ru | 0 | Ctrl+K: «Сцена 0 · ИИ-разбор» — первая среди сцен в режиме показа (П3) | **NOT_RUN** | "сцены 0 нет в палитре — экрана R04 нет в сборке" | R01 |  |
| UI show-ru | 0 | Ctrl+K «Сцена 0 · ИИ-разбор» → сцена ≤ 1 с | **NOT_RUN** | "сцены 0 нет в палитре — экрана R04 «Разбор обращений» нет в сборке (П3)" | R04 + R01 |  |
| UI show-ru | 7 | Ctrl+K «Сцена 7 · Двор вместе» → раздел yard ≤ 1 с | **PASS** | {"ms":456,"section":"yard","network_idle_before":true} | R01 | show-ru-scene7.jpg |
| UI show-ru | 8 | Ctrl+K «Сцена 8 · Ведомства вместе» → раздел inbox ≤ 1 с | **PASS** | {"ms":29,"section":"inbox","network_idle_before":true} | R01 | show-ru-scene8.jpg |
| UI show-ru | 8 | значок «ИИ» у подсказки «Похоже, нужны 2 службы» (П3) | **NOT_RUN** | "подсказки «нужны 2 службы» нет на экране сцены 8" | R11 + R09 | show-ru-scene8.jpg |
| UI show-ru | 9 | Ctrl+K «Сцена 9 · Буран» → раздел agencies ≤ 1 с | **PASS** | {"ms":15,"section":"agencies","network_idle_before":true} | R01 | show-ru-scene9.jpg |
| UI show-ru | S | Ctrl+K «Ситуационный центр» → своя страница /civic/board/ | **PASS** | {"ms":62,"url":"/civic/board/","text":1151,"shell_error":false} | R08 | show-ru-page-board.jpg |
| UI show-ru | S | страница /civic/board/: путь назад в Birge — ссылка «← В Birge» и Esc | **PASS** | {"link":{"text":"← В Birge","href":"/#day"},"esc":true} | R08 |  |
| UI show-ru | S | Ctrl+K «QR-таблички» → своя страница /civic/qr/print.html | **PASS** | {"ms":57,"url":"/civic/qr/print.html","text":477,"shell_error":false} | R12 | show-ru-page-qr.jpg |
| UI show-ru | S | страница /civic/qr/print.html: путь назад в Birge — ссылка «← В Birge» и Esc | **PASS** | {"link":{"text":"← В Birge","href":"/"},"esc":true} | R12 |  |
| UI 1366-ru | 0 | сцена 0 «ИИ-разбор»: экран R04 (window.BirgeIntake) | **NOT_RUN** | "модуля BirgeIntake нет на странице (П3: web/civic/intake/)" | R04 |  |

Время сцен (мс): API — сумма запросов сцены; UI — открытие экранов сцены на одном варианте.

| Слой | 0 | 7 | 8 | 9 |
|---|---:|---:|---:|---:|
| api |  | 371 | 523 | 570 |
| ui |  | 15471 | 16795 | 7232 |
