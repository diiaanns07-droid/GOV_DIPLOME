# R10 e2e · сценарий демо · 29b4ae9d

```
{"world":true,"root":"/tmp/claude-0/-home-user-GOV-DIPLOME/62d68526-d416-54f0-b206-35e3353bc4a5/scratchpad/builds/r01-29b4","sha":"29b4ae9d","base":"(свой сервер)","seeds":["seed-demo","seed-r14-demo"],"sizes":["1366x768","375x812"],"langs":["ru"],"when":"2026-10-16T01:44:15.085Z","node":"v22.22.0","total_ms":370648}
```

Итого: PASS 92, FAIL 2, NOT_RUN 2

| Слой | Шаг | Проверка | Итог | Подробно | Кадр |
|---|---|---|---|---|---|
| API | 0 | шлюз v2: маршруты FINAL-4 на месте и ready | **PASS** | {"not_ready":[],"missing":[]} |  |
| API | 0 | шлюз v2: новые маршруты раунда 15 ready | **NOT_RUN** | "модулей ещё нет в сборке (503 по CONTRACT §7): {\"R06 module_not_ready\":3}" |  |
| API | 2 | текст DEMO_SCRIPT (смесь kk/ru) → «Освещение» с подсказкой | **PASS** | {"status":200,"category":"lighting","score":0.5,"suggest":true,"model":"civic-clf-logreg-kw-cf4464341-pe9ba054a+civic-kw12-r03"} |  |
| API | 2 | /similar сразу после запуска сервера (до первой загрузки страницы) отвечает 200 | **PASS** | {"status":200} |  |
| API | 2 | чистая база демо: /similar по тексту DEMO_SCRIPT у остановки находит похожие (иначе «Я тоже» не будет) | **PASS** | {"status":200,"n":1,"stop":"Хан Шатыр"} |  |
| API | 1 | /targets у остановки: первый кандидат — реальный объект OSM ≤ 60 м с подписью | **PASS** | {"status":200,"first":{"id":"osm-node-13394597038","label":"Остановка «Республиканский диагностический центр»","d":0},"n":1} |  |
| API | 2 | /classify (ru) → «Остановки и транспорт», ответ по §7 | **PASS** | {"status":200,"category":"transport","score":1,"needs_review":true,"model":"civic-clf-logreg-kw-cf4464341-pe9ba054a+civic-kw12-r03"} |  |
| API | 2 | /classify (kk) → «Остановки и транспорт», ответ по §7 | **PASS** | {"status":200,"category":"transport","score":1,"needs_review":true,"model":"civic-clf-logreg-kw-cf4464341-pe9ba054a+civic-kw12-r03"} |  |
| API | 2 | /classify (mixed) → «Остановки и транспорт», ответ по §7 | **PASS** | {"status":200,"category":"transport","score":1,"needs_review":true,"model":"civic-clf-logreg-kw-cf4464341-pe9ba054a+civic-kw12-r03"} |  |
| API | 1 | POST /complaints: запись §5 (id c-…, status new, target сохранён) | **PASS** | {"status":201,"id":"c-676cd84da097d810","st":"new"} |  |
| API | 2 | /similar находит только что поданную жалобу на ту же остановку | **PASS** | {"status":200,"n":1,"top":{"complaint_id":"c-676cd84da097d810","score":0.798,"target":{"id":"osm-node-13394597038","kind":"object","label_kk":"«Республиканский диагностический центр» аялдамасы","label_ru":"Остановка «Рес |  |
| API | 2 | «Я тоже» другим устройством: metoo +1 | **PASS** | {"status":200,"metoo":1} |  |
| API | 2 | повторное «Я тоже» с того же устройства не увеличивает счёт | **PASS** | {"status":200,"metoo":1} |  |
| API | 3 | /heat (Нура, 30 дней, z16): цель жалобы есть, level ≥ 1, count ≥ 1, форма есть | **PASS** | {"status":200,"items":18,"target":{"level":1,"count":2,"weight":2,"kind":"object"}} |  |
| API | 3 | смысловой зум: z10 отдаёт районы, а не отдельные остановки | **PASS** | {"status":200,"n":6,"kinds":["district"]} |  |
| API | 4 | /akim/summary: KPI, темы, районы, горячие места, просрочки, отставание, текст ru/kk | **PASS** | {"status":200,"complaints_available":true,"sources":{"complaints":"r07","objects":"r06","proposals":"r06","heat":"r07","together":"r16","meetings":"r13","forecast":"r13-week","crisis":"r17"},"hot":10} |  |
| API | 5 | вход сотрудника акимата (сессия + CSRF) | **PASS** | {"ok":true,"status":200} |  |
| API | 5 | сотрудник вошёл заранее: похожая жалоба для «Я тоже» с его сессией — то же число людей, что без входа (LOCAL_FINAL P1) | **PASS** | {"similar":200,"id":"c-demo4eca27874085ec47","public":{"status":200,"reporters":3,"metoo":2,"people":3},"staff":{"status":200,"reporters":3,"metoo":2,"people":3}} |  |
| API | 5 | GET /proposals: демо-предложения (seed-r14-demo) со статусом | **PASS** | {"status":200,"n":5,"statuses":["proposal"]} |  |
| API | 5 | POST /proposals (сквер) от сотрудника | **PASS** | {"status":201,"id":"p-91173f176c36","st":"proposal"} |  |
| API | 5 | голос «За» +1, повтор с того же устройства не удваивает | **PASS** | {"first":[200,1],"second":[200,1]} |  |
| API | 6 | сотрудник: «Взять в работу» → «Исправлено» | **PASS** | {"in_progress":200,"fixed":200} |  |
| API | 6 | после «исправлено» цель зелёная (fixed_until задан, вес обнулён) — с волны 2: fixed_kind reported, ждёт проверки жителей | **PASS** | {"item":{"level":"fixed","weight":0,"fixed_until":"2026-10-23T06:38:19+05:00","fixed_kind":"reported","color":"#97C459"}} |  |
| API | 6 | GET /complaints: статус fixed и история статусов | **PASS** | {"status":200,"st":"fixed","history":3} |  |
| UI 1366-ru | 0 | шапка: ҚАЗ/РУС на виду, язык страницы переключился | **PASS** | {"lang":"ru"} | 1366-ru-0-start.jpg |
| UI 1366-ru | 0 | нет горизонтальной прокрутки | **PASS** | {"scrollW":1366,"w":1366} |  |
| UI 1366-ru | 0 | надписи не закрыты другими панелями (частично) | **PASS** | {"n":0,"ex":[]} |  |
| UI 1366-ru | 0 | короткие надписи не обрезаны многоточием (название в шапке, кнопки) | **PASS** | {"n":0,"ex":[]} |  |
| UI 1366-ru | 0 | контраст текста ≥ 4.5:1 (крупный ≥ 3:1), UX_BRIEF правило 2 | **FAIL** | {"n":1,"ex":["3.90:1 «35» rgb(226, 75, 74) на rgb(254,254,254)"]} |  |
| UI 1366-ru | 0 | нет ключей перевода и технических слов | **PASS** | {"raw":[],"tech":[]} |  |
| UI 1366-ru | 0 | шрифт: нет текста мельче 13 px (основной ≥ 15 px, CLEAN_PASS §4) | **PASS** | {"tiny":0,"ex":[],"under15":36,"ex15":["13px «Нура ·»","13px «Сарайшык ·»","13px «Есиль ·»","13px «Сарыарка ·»","13px «Алматы ·»","13px «Байконур ·»"]} |  |
| UI 1366-ru | 0 | зоны нажатия ≥ 40 px (цель — 48 px) | **PASS** | {"under40N":0,"under40":[],"under48":"17/27"} |  |
| UI 1366-ru | 0 | выбор ҚАЗ/РУС сохраняется после перезагрузки страницы | **PASS** |  |  |
| UI 1366-ru | 1 | клавиатура: Tab доходит до главной кнопки (≤ 40), рамка фокуса видна | **PASS** | {"tabs":1,"via":"skip-link + Enter","primary":true,"ring":true,"text":"Сообщить о проблеме"} |  |
| UI 1366-ru | 1 | главная кнопка «Сообщить о проблеме» есть и открывает шаг «Где проблема?» | **PASS** | {"resident_view":true} | 1366-ru-1-start.jpg |
| UI 1366-ru | 1 | нажатие по значку на остановке выбирает место (значок не перехватывает нажатие) | **PASS** | {"under":"r07-badge r07-badge--new maplibregl-mark"} |  |
| UI 1366-ru | 1 | после нажатия на карту в форме предложена остановка «Хан Шатыр» | **PASS** | {"point":{"x":682.9999998897221,"y":345.5999999902519,"onCanvas":false,"under":"r07-badge r07-badge--new maplibregl-mark","near":{"x":682.9999998897221,"y":375.5999999902519,"r":30}},"names":["Хан Шатыр"]} | 1366-ru-1-target.jpg |
| UI 1366-ru | 2 | модель предложила категорию «Освещение» («Похоже на:») | **PASS** | {"textbox":true,"suggested":true,"catShown":true} | 1366-ru-2-category.jpg |
| UI 1366-ru | 2 | после отправки: «Я тоже» (если уже сообщали) → «Ваш голос учтён», иначе «Обращение отправлено» | **PASS** | {"sent":true,"next":true,"metoo":true,"done":true} | 1366-ru-2-sent.jpg |
| UI 1366-ru | 3 | тепловая карта у остановки: цвет нарисован, рядом число людей, легенда с числами видна (с FINAL-3 — строка «мало ▬ много», числа под «?») | **PASS** | {"map":true,"layers":14,"rendered":52,"badges":6,"legend":true} | 1366-ru-3-heat.jpg |
| UI 1366-ru | 3 | фильтры: «Освещение» + «30 дней» → «Сбросить» → снова «Все категории» | **PASS** | {"opened":true,"chip":true,"reset":true,"back":true} |  |
| UI 1366-ru | 3 | «Горячие места» → место из списка: значок выбранного места виден на карте и ничем не закрыт | **PASS** | [{"title":"4 Участок: улица Садовая Не убран снег · 4 чел.","badge":true,"inView":true,"at":[856,417],"covered":null},{"title":"13 Остановка «Хан Шатыр» Долго ждать, нет расписан","badge":true,"inView":true,"at":[858,388 | 1366-ru-3-hot.jpg |
| UI 1366-ru | 4 | «Картина дня»: открылась, 4 крупных числа, «В работе», «Просрочено» | **PASS** | {"day":true,"placeholder_soon":false,"kpis":4,"kpiText":true,"overdue":true,"overdue_key":"akim.kpi.overdue"} | 1366-ru-4-day.jpg |
| UI 1366-ru | 5 | вход сотрудника: «Для сотрудников» → имя и пароль → кабинет открыт | **PASS** | {"opened":true,"ok":true,"tech":[]} | 1366-ru-5-login.jpg |
| UI 1366-ru | 5 | кабинет сотрудника: нет технических слов (адреса API, роли сервера) | **PASS** | {"tech":[]} |  |
| UI 1366-ru | 5 | каталог «Что построить?»: сквер, площадка, спортплощадка, остановка, освещение | **PASS** | {"catalog":true,"unfolded":true,"kinds":["square","playground","sports","stop","lighting"],"projects_layer":true} | 1366-ru-5-catalog.jpg |
| UI 1366-ru | 5 | «Сквер» → нажать на карту → ↺ ↻ → «Поставить»: «Проект поставлен», на карте табличка проекта 2027 | **PASS** | {"hint":true,"rotate":[true,true],"placedClick":true,"placedMsg":true,"label_px_from_place":26} | 1366-ru-5-placed.jpg |
| UI 1366-ru | 5 | после «Поставить» проект виден: место на карте не закрыто сообщением или каталогом | **PASS** | {"place":[683,346],"at_place":null,"at_label":null} | 1366-ru-5-placed.jpg |
| UI 1366-ru | 5 | кнопка «3D» наклоняет карту | **PASS** | {"b3d":true,"pitch0":0,"pitch1":51.99999999999999} | 1366-ru-5-3d.jpg |
| UI 1366-ru | 5 | житель: табличка проекта → карточка → «За» → «Голос учтён» / «Ваш голос: за» | **PASS** | {"label":true,"voted":true,"saved":true} | 1366-ru-5-vote.jpg |
| UI 1366-ru | 5 | акимат: карточка проекта → «Удалить» → «Проект удалён» | **PASS** | {"label":true,"delClick":true,"deleted":true} |  |
| UI 1366-ru | 5 | слои → «Только жалобы и работы»: каталог «Что построить?» скрыт | **PASS** |  |  |
| UI 1366-ru | 6 | карточка места открыта: значок выбранного места виден на карте и ничем не закрыт (шторка, шапка, кнопки) | **PASS** | {"badge":true,"inView":true,"at":[683,346],"covered":null} |  |
| UI 1366-ru | 6 | акимат: карточка остановки → «Взять в работу» (если место ещё не в работе) → «Отметить исправленным» → «Исправлено», зелёным на карте (с волны 2 — «служба сообщила», ждёт проверки жителей) | **PASS** | {"under":"r07-badge maplibregl-marker maplibregl-m","take":false,"fix":true,"fixForm":true,"fixFormSent":true,"fixedShown":false,"green":false,"reportedCard":true,"note":"место уже «В работе» — кнопки «Взять в работу» не | 1366-ru-6-fixed.jpg |
| UI 1366-ru | 6 | клавиатура: Esc закрывает карточку остановки | **PASS** | {"stillOpen":false} |  |
| UI 1366-ru | 6 | житель: «Мои обращения» → у обращения статус «Исправлено» (с волны 2 — «Служба сообщила об устранении») | **PASS** | {"mineOpen":true,"mineFixed":false,"mineReported":true} | 1366-ru-6-mine.jpg |
| UI 1366-ru | 7 | житель проверяет ремонт: «Да, исправлено» → «Проверено жителями» | **PASS** | {"verified":true} | 1366-ru-7-verified.jpg |
| UI 1366-ru | * | консоль без ошибок (кроме шума среды: подложка, WebGL) | **PASS** | [] |  |
| UI 1366-ru | E | нет связи · тепловая карта: понятное сообщение и «Повторить»; после связи «Повторить» возвращает данные | **PASS** | {"opened":true,"message":true,"retry":true,"recovered":true} | 1366-ru-E-heat.jpg |
| UI 1366-ru | E | нет связи · «Мои обращения»: понятное сообщение и «Повторить»; после связи «Повторить» возвращает данные | **PASS** | {"opened":true,"message":true,"retry":true,"recovered":true} | 1366-ru-E-mine.jpg |
| UI 1366-ru | E | нет связи · «Картина дня»: понятное сообщение и «Повторить»; после связи «Повторить» возвращает данные | **PASS** | {"opened":true,"message":true,"retry":true,"recovered":true} | 1366-ru-E-summary.jpg |
| UI 375-ru | 0 | шапка: ҚАЗ/РУС на виду, язык страницы переключился | **PASS** | {"lang":"ru"} | 375-ru-0-start.jpg |
| UI 375-ru | 0 | нет горизонтальной прокрутки | **PASS** | {"scrollW":375,"w":375} |  |
| UI 375-ru | 0 | надписи не закрыты другими панелями (частично) | **PASS** | {"n":0,"ex":[]} |  |
| UI 375-ru | 0 | короткие надписи не обрезаны многоточием (название в шапке, кнопки) | **PASS** | {"n":0,"ex":[]} |  |
| UI 375-ru | 0 | контраст текста ≥ 4.5:1 (крупный ≥ 3:1), UX_BRIEF правило 2 | **PASS** | {"n":0,"ex":[]} |  |
| UI 375-ru | 0 | нет ключей перевода и технических слов | **PASS** | {"raw":[],"tech":[]} |  |
| UI 375-ru | 0 | шрифт: нет текста мельче 13 px (основной ≥ 15 px, CLEAN_PASS §4) | **PASS** | {"tiny":0,"ex":[],"under15":16,"ex15":["13px «Сарыарка ·»","13px «Алматы ·»","13px «Байконур ·»","13px «мало»","13px «много»","13px «·»"]} |  |
| UI 375-ru | 0 | зоны нажатия ≥ 40 px (цель — 48 px) | **FAIL** | {"under40N":1,"under40":[{"h":34,"w":40,"t":"Хроника города"}],"under48":"6/16"} |  |
| UI 375-ru | 0 | выбор ҚАЗ/РУС сохраняется после перезагрузки страницы | **PASS** |  |  |
| UI 375-ru | 1 | главная кнопка «Сообщить о проблеме» есть и открывает шаг «Где проблема?» | **PASS** | {"resident_view":true} | 375-ru-1-start.jpg |
| UI 375-ru | 1 | нажатие по значку на остановке выбирает место (значок не перехватывает нажатие) | **NOT_RUN** | "значка над остановкой в этот момент нет — нажатие прямо по карте" |  |
| UI 375-ru | 1 | после нажатия на карту в форме предложена остановка «Центр материнства и детства» | **PASS** | {"point":{"x":187.49999992462736,"y":365.4000000659792,"onCanvas":true,"under":"maplibregl-canvas","near":{"x":201.49999992462736,"y":365.4000000659792,"r":14}},"names":["Центр материнства и детства"]} | 375-ru-1-target.jpg |
| UI 375-ru | 2 | модель предложила категорию «Освещение» («Похоже на:») | **PASS** | {"textbox":true,"suggested":true,"catShown":true} | 375-ru-2-category.jpg |
| UI 375-ru | 2 | после отправки: «Я тоже» (если уже сообщали) → «Ваш голос учтён», иначе «Обращение отправлено» | **PASS** | {"sent":true,"next":true,"metoo":false,"done":true} | 375-ru-2-sent.jpg |
| UI 375-ru | 3 | тепловая карта у остановки: цвет нарисован, рядом число людей, легенда с числами видна (с FINAL-3 — строка «мало ▬ много», числа под «?») | **PASS** | {"map":true,"layers":14,"rendered":21,"badges":1,"legend":true} | 375-ru-3-heat.jpg |
| UI 375-ru | 3 | фильтры: «Освещение» + «30 дней» → «Сбросить» → снова «Все категории» | **PASS** | {"opened":true,"chip":true,"reset":true,"back":true} |  |
| UI 375-ru | 3 | «Горячие места» → место из списка: значок выбранного места виден на карте и ничем не закрыт | **PASS** | [{"title":"4 Участок: улица Садовая Не убран снег · 4 чел.","badge":true,"inView":true,"at":[160,316],"covered":null},{"title":"7 Двор ЖК «BI City Tokyo» Не убран снег · 7 чел.","badge":true,"inView":true,"at":[157,249], | 375-ru-3-hot.jpg |
| UI 375-ru | 4 | «Картина дня»: открылась, 4 крупных числа, «В работе», «Просрочено» | **PASS** | {"day":true,"placeholder_soon":false,"kpis":4,"kpiText":true,"overdue":true,"overdue_key":"akim.kpi.overdue"} | 375-ru-4-day.jpg |
| UI 375-ru | 5 | вход сотрудника: «Для сотрудников» → имя и пароль → кабинет открыт | **PASS** | {"opened":true,"ok":true,"tech":[]} | 375-ru-5-login.jpg |
| UI 375-ru | 5 | кабинет сотрудника: нет технических слов (адреса API, роли сервера) | **PASS** | {"tech":[]} |  |
| UI 375-ru | 5 | каталог «Что построить?»: сквер, площадка, спортплощадка, остановка, освещение | **PASS** | {"catalog":true,"unfolded":true,"kinds":["square","playground","sports","stop","lighting"],"projects_layer":true} | 375-ru-5-catalog.jpg |
| UI 375-ru | 5 | «Сквер» → нажать на карту → ↺ ↻ → «Поставить»: «Проект поставлен», на карте табличка проекта 2027 | **PASS** | {"hint":false,"rotate":[true,true],"placedClick":true,"placedMsg":true,"label_px_from_place":25} | 375-ru-5-placed.jpg |
| UI 375-ru | 5 | после «Поставить» проект виден: место на карте не закрыто сообщением или каталогом | **PASS** | {"place":[188,365],"at_place":null,"at_label":null} | 375-ru-5-placed.jpg |
| UI 375-ru | 5 | кнопка «3D» наклоняет карту | **PASS** | {"b3d":true,"pitch0":0,"pitch1":51.99999999999999} | 375-ru-5-3d.jpg |
| UI 375-ru | 5 | житель: табличка проекта → карточка → «За» → «Голос учтён» / «Ваш голос: за» | **PASS** | {"label":true,"voted":true,"saved":true} | 375-ru-5-vote.jpg |
| UI 375-ru | 5 | акимат: карточка проекта → «Удалить» → «Проект удалён» | **PASS** | {"label":true,"delClick":true,"deleted":true} |  |
| UI 375-ru | 5 | слои → «Только жалобы и работы»: каталог «Что построить?» скрыт | **PASS** |  |  |
| UI 375-ru | 6 | карточка места открыта: значок выбранного места виден на карте и ничем не закрыт (шторка, шапка, кнопки) | **PASS** | {"badge":true,"inView":true,"at":[188,366],"covered":null} |  |
| UI 375-ru | 6 | акимат: карточка остановки → «Взять в работу» (если место ещё не в работе) → «Отметить исправленным» → «Исправлено», зелёным на карте (с волны 2 — «служба сообщила», ждёт проверки жителей) | **PASS** | {"under":"r07-badge maplibregl-marker maplibregl-m","take":true,"fix":true,"fixForm":true,"fixFormSent":true,"fixedShown":false,"green":false,"reportedCard":true} | 375-ru-6-fixed.jpg |
| UI 375-ru | 6 | житель: «Мои обращения» → у обращения статус «Исправлено» (с волны 2 — «Служба сообщила об устранении») | **PASS** | {"mineOpen":true,"mineFixed":false,"mineReported":true} | 375-ru-6-mine.jpg |
| UI 375-ru | 7 | житель проверяет ремонт: «Да, исправлено» → «Проверено жителями» | **PASS** | {"verified":true} | 375-ru-7-verified.jpg |
| UI 375-ru | * | консоль без ошибок (кроме шума среды: подложка, WebGL) | **PASS** | [] |  |
| UI 375-ru | E | нет связи · тепловая карта: понятное сообщение и «Повторить»; после связи «Повторить» возвращает данные | **PASS** | {"opened":true,"message":true,"retry":true,"recovered":true} | 375-ru-E-heat.jpg |
| UI 375-ru | E | нет связи · «Мои обращения»: понятное сообщение и «Повторить»; после связи «Повторить» возвращает данные | **PASS** | {"opened":true,"message":true,"retry":true,"recovered":true} | 375-ru-E-mine.jpg |
| UI 375-ru | E | нет связи · «Картина дня»: понятное сообщение и «Повторить»; после связи «Повторить» возвращает данные | **PASS** | {"opened":true,"message":true,"retry":true,"recovered":true} | 375-ru-E-summary.jpg |

Время шагов, с (паузы теста + ожидание страницы):

| Слой | 0 | 1 | 2 | 3 | 4 | 5 | 6 | 7 | * | E | всего |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| API | 11.6 | 0.0 | 2.1 | 0.1 | 1.3 | 0.3 | 0.1 |  |  |  | 15.5 |
| UI 1366-ru | 10.7 | 10.9 | 10.5 | 37.3 | 3.8 | 62.7 | 18.2 | 2.7 | 0.0 | 33.9 | 190.7 |
| UI 375-ru | 8.0 | 8.4 | 10.9 | 24.7 | 4.1 | 54.1 | 18.6 | 2.6 | 0.0 | 32.9 | 164.4 |
