# R10 e2e · сценарий демо · 69984f0f

```
{"glass":"keep","glass_seen":{"1366-ru":{"0-start":{"off":false,"blurred":16},"1-start":{"off":false,"blurred":16},"1-target":{"off":false,"blurred":16},"2-category":{"off":false,"blurred":16},"2-sent":{"off":false,"blurred":16},"3-heat":{"off":false,"blurred":16},"3-hot":{"off":false,"blurred":16},"4-day":{"off":false,"blurred":17},"5-login":{"off":false,"blurred":16},"5-catalog":{"off":false,"blurred":17},"5-placed":{"off":false,"blurred":17},"5-3d":{"off":false,"blurred":17},"5-vote":{"off":false,"blurred":16},"6-fixed":{"off":false,"blurred":16},"6-mine":{"off":false,"blurred":18},"7-verified":{"off":false,"blurred":18}},"1366-kk":{"0-start":{"off":false,"blurred":16},"1-start":{"off":false,"blurred":16},"1-target":{"off":false,"blurred":16},"2-category":{"off":false,"blurred":16},"2-sent":{"off":false,"blurred":16},"3-heat":{"off":false,"blurred":16},"3-hot":{"off":false,"blurred":16},"4-day":{"off":false,"blurred":17},"5-login":{"off":false,"blurred":16},"5-catalog":{"off":false,"blurred":17},"5-placed":{"off":false,"blurred":17},"5-3d":{"off":false,"blurred":17},"5-vote":{"off":false,"blurred":16},"6-fixed":{"off":false,"blurred":16},"6-mine":{"off":false,"blurred":18},"7-verified":{"off":false,"blurred":18}},"375-ru":{"0-start":{"off":false,"blurred":17},"1-start":{"off":false,"blurred":17},"1-target":{"off":false,"blurred":17},"2-category":{"off":false,"blurred":17},"2-sent":{"off":false,"blurred":17},"3-heat":{"off":false,"blurred":17},"3-hot":{"off":false,"blurred":17},"4-day":{"off":false,"blurred":18},"5-login":{"off":false,"blurred":17},"5-catalog":{"off":false,"blurred":17},"5-placed":{"off":false,"blurred":17},"5-3d":{"off":false,"blurred":17},"5-vote":{"off":false,"blurred":17},"6-fixed":{"off":false,"blurred":17},"6-mine":{"off":false,"blurred":19},"7-verified":{"off":false,"blurred":19}},"375-kk":{"0-start":{"off":false,"blurred":17},"1-start":{"off":false,"blurred":17},"1-target":{"off":false,"blurred":17},"2-category":{"off":false,"blurred":17},"2-sent":{"off":false,"blurred":17},"3-heat":{"off":false,"blurred":17},"3-hot":{"off":false,"blurred":17},"4-day":{"off":false,"blurred":18},"5-login":{"off":false,"blurred":17},"5-catalog":{"off":false,"blurred":17},"5-placed":{"off":false,"blurred":17},"5-3d":{"off":false,"blurred":17},"5-vote":{"off":false,"blurred":17},"6-fixed":{"off":false,"blurred":17},"6-mine":{"off":false,"blurred":19},"7-verified":{"off":false,"blurred":19}}},"root":"/home/user/bpv3","sha":"69984f0f","base":"(свой сервер)","seeds":["seed-demo","seed-r14-demo"],"sizes":["1366x768","375x812"],"langs":["ru","kk"],"when":"2026-10-13T12:31:41.617Z","node":"v22.22.0","total_ms":698328,"audit":{"font_min_px":13,"tap_min_px":44,"shots":64,"excluded_ms":1401}}
```

Итого: PASS 167, FAIL 6, NOT_RUN 0

| Слой | Шаг | Проверка | Итог | Подробно | Кадр |
|---|---|---|---|---|---|
| API | 0 | шлюз v2: все маршруты ready | **PASS** | {"not_ready":[]} |  |
| API | 2 | текст DEMO_SCRIPT (смесь kk/ru) → «Освещение» с подсказкой | **PASS** | {"status":200,"category":"lighting","score":0.5,"suggest":true,"model":"civic-clf-logreg-kw-cf4464341-pe9ba054a+civic-kw12-r03"} |  |
| API | 2 | /similar сразу после запуска сервера (до первой загрузки страницы) отвечает 200 | **PASS** | {"status":200} |  |
| API | 2 | чистая база демо: /similar по тексту DEMO_SCRIPT у остановки находит похожие (иначе «Я тоже» не будет) | **PASS** | {"status":200,"n":1,"stop":"Хан Шатыр"} |  |
| API | 1 | /targets у остановки: первый кандидат — реальный объект OSM ≤ 60 м с подписью | **PASS** | {"status":200,"first":{"id":"osm-node-13394597038","label":"Остановка «Республиканский диагностический центр»","d":0},"n":1} |  |
| API | 2 | /classify (ru) → «Остановки и транспорт», ответ по §7 | **PASS** | {"status":200,"category":"transport","score":1,"needs_review":true,"model":"civic-clf-logreg-kw-cf4464341-pe9ba054a+civic-kw12-r03"} |  |
| API | 2 | /classify (kk) → «Остановки и транспорт», ответ по §7 | **PASS** | {"status":200,"category":"transport","score":1,"needs_review":true,"model":"civic-clf-logreg-kw-cf4464341-pe9ba054a+civic-kw12-r03"} |  |
| API | 2 | /classify (mixed) → «Остановки и транспорт», ответ по §7 | **PASS** | {"status":200,"category":"transport","score":1,"needs_review":true,"model":"civic-clf-logreg-kw-cf4464341-pe9ba054a+civic-kw12-r03"} |  |
| API | 1 | POST /complaints: запись §5 (id c-…, status new, target сохранён) | **PASS** | {"status":201,"id":"c-0202e1339cbdeea6","st":"new"} |  |
| API | 2 | /similar находит только что поданную жалобу на ту же остановку | **PASS** | {"status":200,"n":1,"top":{"complaint_id":"c-0202e1339cbdeea6","score":0.798,"target":{"id":"osm-node-13394597038","kind":"object","label_kk":"«Республиканский диагностический центр» аялдамасы","label_ru":"Остановка «Рес |  |
| API | 2 | «Я тоже» другим устройством: metoo +1 | **PASS** | {"status":200,"metoo":1} |  |
| API | 2 | повторное «Я тоже» с того же устройства не увеличивает счёт | **PASS** | {"status":200,"metoo":1} |  |
| API | 3 | /heat (Нура, 30 дней, z16): цель жалобы есть, level ≥ 1, count ≥ 1, форма есть | **PASS** | {"status":200,"items":32,"target":{"level":4,"count":21,"weight":15.609,"kind":"object"}} |  |
| API | 3 | смысловой зум: z10 отдаёт районы, а не отдельные остановки | **PASS** | {"status":200,"n":6,"kinds":["district"]} |  |
| API | 4 | /akim/summary: KPI, темы, районы, горячие места, просрочки, отставание, текст ru/kk | **PASS** | {"status":200,"complaints_available":true,"sources":{"complaints":"r07","objects":"r06","proposals":"r06","heat":"r07"},"hot":10} |  |
| API | 5 | вход сотрудника акимата (сессия + CSRF) | **PASS** | {"ok":true,"status":200} |  |
| API | 5 | сотрудник вошёл заранее: похожая жалоба для «Я тоже» с его сессией — то же число людей, что без входа (LOCAL_FINAL P1) | **PASS** | {"similar":200,"id":"c-demo4eca27874085ec47","public":{"status":200,"reporters":3,"metoo":2,"people":3},"staff":{"status":200,"reporters":3,"metoo":2,"people":3}} |  |
| API | 5 | GET /proposals: демо-предложения (seed-r14-demo) со статусом | **PASS** | {"status":200,"n":5,"statuses":["proposal"]} |  |
| API | 5 | POST /proposals (сквер) от сотрудника | **PASS** | {"status":201,"id":"p-7a83d5f77897","st":"proposal"} |  |
| API | 5 | голос «За» +1, повтор с того же устройства не удваивает | **PASS** | {"first":[200,1],"second":[200,1]} |  |
| API | 6 | сотрудник: «Взять в работу» → «Исправлено» | **PASS** | {"in_progress":200,"fixed":200} |  |
| API | 6 | после «исправлено» цель зелёная (fixed_until задан, вес обнулён) — с волны 2: fixed_kind reported, ждёт проверки жителей | **PASS** | {"item":{"level":"fixed","weight":0,"fixed_until":"2026-10-20T17:20:10+05:00","fixed_kind":"reported","color":"#97C459"}} |  |
| API | 6 | GET /complaints: статус fixed и история статусов | **PASS** | {"status":200,"st":"fixed","history":3} |  |
| UI 1366-ru | 0 | шапка: ҚАЗ/РУС на виду, язык страницы переключился | **PASS** | {"lang":"ru"} | 1366-ru-0-start.jpg |
| UI 1366-ru | 0 | нет горизонтальной прокрутки | **PASS** | {"scrollW":1366,"w":1366} |  |
| UI 1366-ru | 0 | надписи не закрыты другими панелями (частично) | **PASS** | {"n":0,"ex":[]} |  |
| UI 1366-ru | 0 | короткие надписи не обрезаны многоточием (название в шапке, кнопки) | **PASS** | {"n":0,"ex":[]} |  |
| UI 1366-ru | 0 | контраст текста ≥ 4.5:1 (крупный ≥ 3:1), UX_BRIEF правило 2 | **FAIL** | {"n":10,"ex":["3.40:1 «за 30 дней» rgb(126, 138, 133) на rgb(248,249,247)","3.40:1 «Освещение» rgb(126, 138, 133) на rgb(248,249,247)","3.40:1 «Деревья, газон» rgb(126, 138, 133) на rgb(248,249,247)","3.40:1 «Не убран сн |  |
| UI 1366-ru | 0 | нет ключей перевода и технических слов | **PASS** | {"raw":[],"tech":[]} |  |
| UI 1366-ru | 0 | шрифт: нет текста мельче 13 px (основной ≥ 15 px, CLEAN_PASS §4) | **PASS** | {"tiny":0,"ex":[],"under15":51,"ex15":["13px «Нура ·»","13px «Байконур ·»","13px «Есиль ·»","13px «Сарайшык ·»","13px «Сарыарка ·»","13px «Алматы ·»"]} |  |
| UI 1366-ru | 0 | зоны нажатия ≥ 40 px (цель — 48 px) | **PASS** | {"under40N":0,"under40":[],"under48":"15/30"} |  |
| UI 1366-ru | 0 | выбор ҚАЗ/РУС сохраняется после перезагрузки страницы | **PASS** |  |  |
| UI 1366-ru | 1 | клавиатура: Tab доходит до главной кнопки (≤ 40), рамка фокуса видна | **PASS** | {"tabs":1,"via":"skip-link + Enter","primary":true,"ring":true,"text":"Сообщить о проблеме"} |  |
| UI 1366-ru | 1 | главная кнопка «Сообщить о проблеме» есть и открывает шаг «Где проблема?» | **PASS** | {"resident_view":true} | 1366-ru-1-start.jpg |
| UI 1366-ru | 1 | нажатие по значку на остановке выбирает место (значок не перехватывает нажатие) | **PASS** | {"under":"r07-badge maplibregl-marker maplibregl-m"} |  |
| UI 1366-ru | 1 | после нажатия на карту в форме предложена остановка «Хан Шатыр» | **PASS** | {"point":{"x":683.0000000334676,"y":345.6000000096257,"onCanvas":false,"under":"r07-badge maplibregl-marker maplibregl-m","near":{"x":683.0000000334676,"y":375.6000000096257,"r":30}},"names":["Хан Шатыр"]} | 1366-ru-1-target.jpg |
| UI 1366-ru | 2 | модель предложила категорию «Освещение» («Похоже на:») | **PASS** | {"textbox":true,"suggested":true,"catShown":true} | 1366-ru-2-category.jpg |
| UI 1366-ru | 2 | после отправки: «Я тоже» (если уже сообщали) → «Ваш голос учтён», иначе «Обращение отправлено» | **PASS** | {"sent":true,"next":true,"metoo":true,"done":true} | 1366-ru-2-sent.jpg |
| UI 1366-ru | 3 | тепловая карта у остановки: цвет нарисован, рядом число людей, легенда с числами видна (с FINAL-3 — строка «мало ▬ много», числа под «?») | **PASS** | {"map":true,"layers":14,"rendered":52,"badges":16,"legend":true} | 1366-ru-3-heat.jpg |
| UI 1366-ru | 3 | фильтры: «Освещение» + «30 дней» → «Сбросить» → снова «Все категории» | **PASS** | {"opened":true,"chip":true,"reset":true,"back":true} |  |
| UI 1366-ru | 3 | «Горячие места» → место из списка: значок выбранного места виден на карте и ничем не закрыт | **PASS** | [{"title":"6 Остановка «Хан Шатыр» Освещение · 6 чел.","badge":true,"inView":true,"at":[448,382],"covered":null},{"title":"11 Двор у ул. Коксенгир Деревья, газон · 11 чел.","badge":true,"inView":true,"at":[448,381],"cove | 1366-ru-3-hot.jpg |
| UI 1366-ru | 4 | «Картина дня»: открылась, 4 крупных числа, «В работе», «Просрочено» | **PASS** | {"day":true,"placeholder_soon":false,"kpis":4,"kpiText":true,"overdue":true} | 1366-ru-4-day.jpg |
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
| UI 1366-ru | 6 | акимат: карточка остановки → «Взять в работу» (если место ещё не в работе) → «Отметить исправленным» → «Исправлено», зелёным на карте (с волны 2 — «служба сообщила», ждёт проверки жителей) | **PASS** | {"under":"r07-badge maplibregl-marker maplibregl-m","take":true,"fix":true,"fixForm":true,"fixFormSent":true,"fixedShown":false,"green":false,"reportedCard":true} | 1366-ru-6-fixed.jpg |
| UI 1366-ru | 6 | клавиатура: Esc закрывает карточку остановки | **PASS** | {"stillOpen":false} |  |
| UI 1366-ru | 6 | житель: «Мои обращения» → у обращения статус «Исправлено» (с волны 2 — «Служба сообщила об устранении») | **PASS** | {"mineOpen":true,"mineFixed":false,"mineReported":true} | 1366-ru-6-mine.jpg |
| UI 1366-ru | 7 | житель проверяет ремонт: «Да, исправлено» → «Проверено жителями» | **PASS** | {"verified":true} | 1366-ru-7-verified.jpg |
| UI 1366-ru | * | консоль без ошибок (кроме шума среды: подложка, WebGL) | **PASS** | [] |  |
| UI 1366-ru | E | нет связи · тепловая карта: понятное сообщение и «Повторить»; после связи «Повторить» возвращает данные | **PASS** | {"opened":true,"message":true,"retry":true,"recovered":true} | 1366-ru-E-heat.jpg |
| UI 1366-ru | E | нет связи · «Мои обращения»: понятное сообщение и «Повторить»; после связи «Повторить» возвращает данные | **PASS** | {"opened":true,"message":true,"retry":true,"recovered":true} | 1366-ru-E-mine.jpg |
| UI 1366-ru | E | нет связи · «Картина дня»: понятное сообщение и «Повторить»; после связи «Повторить» возвращает данные | **PASS** | {"opened":true,"message":true,"retry":true,"recovered":true} | 1366-ru-E-summary.jpg |
| UI 1366-kk | 0 | шапка: ҚАЗ/РУС на виду, язык страницы переключился | **PASS** | {"lang":"kk"} | 1366-kk-0-start.jpg |
| UI 1366-kk | 0 | нет горизонтальной прокрутки | **PASS** | {"scrollW":1366,"w":1366} |  |
| UI 1366-kk | 0 | надписи не закрыты другими панелями (частично) | **PASS** | {"n":0,"ex":[]} |  |
| UI 1366-kk | 0 | короткие надписи не обрезаны многоточием (название в шапке, кнопки) | **PASS** | {"n":0,"ex":[]} |  |
| UI 1366-kk | 0 | контраст текста ≥ 4.5:1 (крупный ≥ 3:1), UX_BRIEF правило 2 | **FAIL** | {"n":10,"ex":["3.40:1 «соңғы 30 күнде» rgb(126, 138, 133) на rgb(248,249,247)","3.40:1 «Балалар алаңы сынған» rgb(126, 138, 133) на rgb(248,249,247)","3.40:1 «Ағаштар, көгал» rgb(126, 138, 133) на rgb(248,249,247)","3.40 |  |
| UI 1366-kk | 0 | нет ключей перевода и технических слов | **PASS** | {"raw":[],"tech":[]} |  |
| UI 1366-kk | 0 | шрифт: нет текста мельче 13 px (основной ≥ 15 px, CLEAN_PASS §4) | **PASS** | {"tiny":0,"ex":[],"under15":50,"ex15":["13px «Нұра ·»","13px «Байқоңыр ·»","13px «Есіл ·»","13px «Сарайшық ·»","13px «Сарыарқа ·»","13px «Алматы ·»"]} |  |
| UI 1366-kk | 0 | зоны нажатия ≥ 40 px (цель — 48 px) | **PASS** | {"under40N":0,"under40":[],"under48":"15/30"} |  |
| UI 1366-kk | 0 | выбор ҚАЗ/РУС сохраняется после перезагрузки страницы | **PASS** |  |  |
| UI 1366-kk | 0 | ҚАЗ: на экране нет строк, оставшихся по-русски | **PASS** | {"n":0,"ex":[]} |  |
| UI 1366-kk | 0 | ҚАЗ: во всей странице (с прокруткой панелей) нет строк по-русски | **PASS** | {"n":0,"ex":[]} |  |
| UI 1366-kk | 1 | клавиатура: Tab доходит до главной кнопки (≤ 40), рамка фокуса видна | **PASS** | {"tabs":1,"via":"skip-link + Enter","primary":true,"ring":true,"text":"Мәселе туралы хабарлау"} |  |
| UI 1366-kk | 1 | главная кнопка «Мәселе туралы хабарлау» есть и открывает шаг «Где проблема?» | **PASS** | {"resident_view":true} | 1366-kk-1-start.jpg |
| UI 1366-kk | 1 | нажатие по значку на остановке выбирает место (значок не перехватывает нажатие) | **PASS** | {"under":"r07-badge r07-badge--new maplibregl-mark"} |  |
| UI 1366-kk | 1 | после нажатия на карту в форме предложена остановка «Центр материнства и детства» | **PASS** | {"point":{"x":682.9999999176047,"y":345.5999999910874,"onCanvas":false,"under":"r07-badge r07-badge--new maplibregl-mark","near":{"x":682.9999999176047,"y":375.5999999910874,"r":30}},"names":["Центр материнства и детства | 1366-kk-1-target.jpg |
| UI 1366-kk | 2 | модель предложила категорию «Жарықтандыру» («Ұқсас санат:») | **PASS** | {"textbox":true,"suggested":true,"catShown":true} | 1366-kk-2-category.jpg |
| UI 1366-kk | 2 | после отправки: «Я тоже» (если уже сообщали) → «Ваш голос учтён», иначе «Обращение отправлено» | **PASS** | {"sent":true,"next":true,"metoo":false,"done":true} | 1366-kk-2-sent.jpg |
| UI 1366-kk | 3 | тепловая карта у остановки: цвет нарисован, рядом число людей, легенда с числами видна (с FINAL-3 — строка «мало ▬ много», числа под «?») | **PASS** | {"map":true,"layers":14,"rendered":52,"badges":16,"legend":true} | 1366-kk-3-heat.jpg |
| UI 1366-kk | 3 | фильтры: «Освещение» + «30 дней» → «Сбросить» → снова «Все категории» | **PASS** | {"opened":true,"chip":true,"reset":true,"back":true} |  |
| UI 1366-kk | 3 | «Горячие места» → место из списка: значок выбранного места виден на карте и ничем не закрыт | **PASS** | [{"title":"4 Таргабатай көшесі маңындағы аула Балалар алаңы с","badge":true,"inView":true,"at":[448,382],"covered":null},{"title":"11 Коксенгир көшесі маңындағы аула Ағаштар, көгал ","badge":true,"inView":true,"at":[448, | 1366-kk-3-hot.jpg |
| UI 1366-kk | 4 | «Картина дня»: открылась, 4 крупных числа, «В работе», «Просрочено» | **PASS** | {"day":true,"placeholder_soon":false,"kpis":4,"kpiText":true,"overdue":true} | 1366-kk-4-day.jpg |
| UI 1366-kk | 5 | вход сотрудника: «Для сотрудников» → имя и пароль → кабинет открыт | **PASS** | {"opened":true,"ok":true,"ru_in_kk":[],"tech":[]} | 1366-kk-5-login.jpg |
| UI 1366-kk | 5 | кабинет сотрудника: нет технических слов (адреса API, роли сервера) | **PASS** | {"tech":[]} |  |
| UI 1366-kk | 5 | ҚАЗ: форма входа и кабинет сотрудника по-казахски | **PASS** | {"ru":[]} |  |
| UI 1366-kk | 5 | каталог «Что построить?»: сквер, площадка, спортплощадка, остановка, освещение | **PASS** | {"catalog":true,"unfolded":true,"kinds":["square","playground","sports","stop","lighting"],"projects_layer":true} | 1366-kk-5-catalog.jpg |
| UI 1366-kk | 5 | «Гүлзар» → нажать на карту → ↺ ↻ → «Поставить»: «Проект поставлен», на карте табличка проекта 2027 | **PASS** | {"hint":true,"rotate":[true,true],"placedClick":true,"placedMsg":true,"label_px_from_place":26} | 1366-kk-5-placed.jpg |
| UI 1366-kk | 5 | после «Поставить» проект виден: место на карте не закрыто сообщением или каталогом | **PASS** | {"place":[683,346],"at_place":null,"at_label":null} | 1366-kk-5-placed.jpg |
| UI 1366-kk | 5 | кнопка «3D» наклоняет карту | **PASS** | {"b3d":true,"pitch0":0,"pitch1":51.99999999999999} | 1366-kk-5-3d.jpg |
| UI 1366-kk | 5 | житель: табличка проекта → карточка → «За» → «Голос учтён» / «Ваш голос: за» | **PASS** | {"label":true,"voted":true,"saved":true} | 1366-kk-5-vote.jpg |
| UI 1366-kk | 5 | акимат: карточка проекта → «Удалить» → «Проект удалён» | **PASS** | {"label":true,"delClick":true,"deleted":true} |  |
| UI 1366-kk | 5 | слои → «Только жалобы и работы»: каталог «Что построить?» скрыт | **PASS** |  |  |
| UI 1366-kk | 6 | карточка места открыта: значок выбранного места виден на карте и ничем не закрыт (шторка, шапка, кнопки) | **PASS** | {"badge":true,"inView":true,"at":[683,346],"covered":null} |  |
| UI 1366-kk | 6 | акимат: карточка остановки → «Взять в работу» (если место ещё не в работе) → «Отметить исправленным» → «Түзетілді», зелёным на карте (с волны 2 — «служба сообщила», ждёт проверки жителей) | **PASS** | {"under":"r07-badge maplibregl-marker maplibregl-m","take":true,"fix":true,"fixForm":true,"fixFormSent":true,"fixedShown":true,"green":false,"reportedCard":true} | 1366-kk-6-fixed.jpg |
| UI 1366-kk | 6 | клавиатура: Esc закрывает карточку остановки | **PASS** | {"stillOpen":false} |  |
| UI 1366-kk | 6 | житель: «Менің өтініштерім» → у обращения статус «Түзетілді» (с волны 2 — «Қызмет түзетілгенін хабарлады») | **PASS** | {"mineOpen":true,"mineFixed":false,"mineReported":true} | 1366-kk-6-mine.jpg |
| UI 1366-kk | 7 | житель проверяет ремонт: «Да, исправлено» → «Проверено жителями» | **PASS** | {"verified":true} | 1366-kk-7-verified.jpg |
| UI 1366-kk | * | консоль без ошибок (кроме шума среды: подложка, WebGL) | **PASS** | [] |  |
| UI 1366-kk | E | нет связи · тепловая карта: понятное сообщение и «Повторить»; после связи «Повторить» возвращает данные | **PASS** | {"opened":true,"message":true,"retry":true,"recovered":true} | 1366-kk-E-heat.jpg |
| UI 1366-kk | E | нет связи · «Мои обращения»: понятное сообщение и «Повторить»; после связи «Повторить» возвращает данные | **PASS** | {"opened":true,"message":true,"retry":true,"recovered":true} | 1366-kk-E-mine.jpg |
| UI 1366-kk | E | нет связи · «Картина дня»: понятное сообщение и «Повторить»; после связи «Повторить» возвращает данные | **PASS** | {"opened":true,"message":true,"retry":true,"recovered":true} | 1366-kk-E-summary.jpg |
| UI 375-ru | 0 | шапка: ҚАЗ/РУС на виду, язык страницы переключился | **PASS** | {"lang":"ru"} | 375-ru-0-start.jpg |
| UI 375-ru | 0 | нет горизонтальной прокрутки | **PASS** | {"scrollW":375,"w":375} |  |
| UI 375-ru | 0 | надписи не закрыты другими панелями (частично) | **FAIL** | {"n":1,"ex":["«Сломана детская площадка» под «Сообщить о проблеме»"]} |  |
| UI 375-ru | 0 | короткие надписи не обрезаны многоточием (название в шапке, кнопки) | **PASS** | {"n":0,"ex":[]} |  |
| UI 375-ru | 0 | контраст текста ≥ 4.5:1 (крупный ≥ 3:1), UX_BRIEF правило 2 | **FAIL** | {"n":2,"ex":["3.40:1 «за 30 дней» rgb(126, 138, 133) на rgb(248,249,247)","3.40:1 «Деревья, газон» rgb(126, 138, 133) на rgb(248,249,247)"]} |  |
| UI 375-ru | 0 | нет ключей перевода и технических слов | **PASS** | {"raw":[],"tech":[]} |  |
| UI 375-ru | 0 | шрифт: нет текста мельче 13 px (основной ≥ 15 px, CLEAN_PASS §4) | **PASS** | {"tiny":0,"ex":[],"under15":23,"ex15":["13px «Нура ·»","13px «Есиль ·»","13px «Сарайшык ·»","13px «мало»","13px «много»","13px «·»"]} |  |
| UI 375-ru | 0 | зоны нажатия ≥ 40 px (цель — 48 px) | **PASS** | {"under40N":0,"under40":[],"under48":"10/19"} |  |
| UI 375-ru | 0 | выбор ҚАЗ/РУС сохраняется после перезагрузки страницы | **PASS** |  |  |
| UI 375-ru | 1 | главная кнопка «Сообщить о проблеме» есть и открывает шаг «Где проблема?» | **PASS** | {"resident_view":true} | 375-ru-1-start.jpg |
| UI 375-ru | 1 | нажатие по значку на остановке выбирает место (значок не перехватывает нажатие) | **PASS** | {"under":"r07-badge maplibregl-marker maplibregl-m"} |  |
| UI 375-ru | 1 | после нажатия на карту в форме предложена остановка «Жилой комплекс Зелёный Квартал» | **PASS** | {"point":{"x":187.5000000189736,"y":365.39999998998326,"onCanvas":false,"under":"r07-badge maplibregl-marker maplibregl-m","near":{"x":187.5000000189736,"y":395.39999998998326,"r":30}},"names":["Жилой комплекс Зелёный Кв | 375-ru-1-target.jpg |
| UI 375-ru | 2 | модель предложила категорию «Освещение» («Похоже на:») | **PASS** | {"textbox":true,"suggested":true,"catShown":true} | 375-ru-2-category.jpg |
| UI 375-ru | 2 | после отправки: «Я тоже» (если уже сообщали) → «Ваш голос учтён», иначе «Обращение отправлено» | **PASS** | {"sent":true,"next":true,"metoo":false,"done":true} | 375-ru-2-sent.jpg |
| UI 375-ru | 3 | тепловая карта у остановки: цвет нарисован, рядом число людей, легенда с числами видна (с FINAL-3 — строка «мало ▬ много», числа под «?») | **PASS** | {"map":true,"layers":14,"rendered":26,"badges":1,"legend":true} | 375-ru-3-heat.jpg |
| UI 375-ru | 3 | фильтры: «Освещение» + «30 дней» → «Сбросить» → снова «Все категории» | **PASS** | {"opened":true,"chip":true,"reset":true,"back":true} |  |
| UI 375-ru | 3 | «Горячие места» → место из списка: значок выбранного места виден на карте и ничем не закрыт | **PASS** | [{"title":"4 Двор у ул. Таргабатай Сломана детская площадка ·","badge":true,"inView":true,"at":[160,316],"covered":null},{"title":"11 Двор у ул. Коксенгир Деревья, газон · 11 чел.","badge":true,"inView":true,"at":[158,25 | 375-ru-3-hot.jpg |
| UI 375-ru | 4 | «Картина дня»: открылась, 4 крупных числа, «В работе», «Просрочено» | **PASS** | {"day":true,"placeholder_soon":false,"kpis":4,"kpiText":true,"overdue":true} | 375-ru-4-day.jpg |
| UI 375-ru | 5 | вход сотрудника: «Для сотрудников» → имя и пароль → кабинет открыт | **PASS** | {"opened":true,"ok":true,"tech":[]} | 375-ru-5-login.jpg |
| UI 375-ru | 5 | кабинет сотрудника: нет технических слов (адреса API, роли сервера) | **PASS** | {"tech":[]} |  |
| UI 375-ru | 5 | каталог «Что построить?»: сквер, площадка, спортплощадка, остановка, освещение | **PASS** | {"catalog":true,"unfolded":true,"kinds":["square","playground","sports","stop","lighting"],"projects_layer":true} | 375-ru-5-catalog.jpg |
| UI 375-ru | 5 | «Сквер» → нажать на карту → ↺ ↻ → «Поставить»: «Проект поставлен», на карте табличка проекта 2027 | **PASS** | {"hint":false,"rotate":[true,true],"placedClick":true,"placedMsg":true,"label_px_from_place":25} | 375-ru-5-placed.jpg |
| UI 375-ru | 5 | после «Поставить» проект виден: место на карте не закрыто сообщением или каталогом | **PASS** | {"place":[187,365],"at_place":null,"at_label":null} | 375-ru-5-placed.jpg |
| UI 375-ru | 5 | кнопка «3D» наклоняет карту | **PASS** | {"b3d":true,"pitch0":0,"pitch1":51.99999999999999} | 375-ru-5-3d.jpg |
| UI 375-ru | 5 | житель: табличка проекта → карточка → «За» → «Голос учтён» / «Ваш голос: за» | **PASS** | {"label":true,"voted":true,"saved":true} | 375-ru-5-vote.jpg |
| UI 375-ru | 5 | акимат: карточка проекта → «Удалить» → «Проект удалён» | **PASS** | {"label":true,"delClick":true,"deleted":true} |  |
| UI 375-ru | 5 | слои → «Только жалобы и работы»: каталог «Что построить?» скрыт | **PASS** |  |  |
| UI 375-ru | 6 | карточка места открыта: значок выбранного места виден на карте и ничем не закрыт (шторка, шапка, кнопки) | **PASS** | {"badge":true,"inView":true,"at":[188,365],"covered":null} |  |
| UI 375-ru | 6 | акимат: карточка остановки → «Взять в работу» (если место ещё не в работе) → «Отметить исправленным» → «Исправлено», зелёным на карте (с волны 2 — «служба сообщила», ждёт проверки жителей) | **PASS** | {"under":"r07-badge maplibregl-marker maplibregl-m","take":false,"fix":true,"fixForm":true,"fixFormSent":true,"fixedShown":false,"green":false,"reportedCard":true,"note":"место уже «В работе» — кнопки «Взять в работу» не | 375-ru-6-fixed.jpg |
| UI 375-ru | 6 | житель: «Мои обращения» → у обращения статус «Исправлено» (с волны 2 — «Служба сообщила об устранении») | **PASS** | {"mineOpen":true,"mineFixed":false,"mineReported":true} | 375-ru-6-mine.jpg |
| UI 375-ru | 7 | житель проверяет ремонт: «Да, исправлено» → «Проверено жителями» | **PASS** | {"verified":true} | 375-ru-7-verified.jpg |
| UI 375-ru | * | консоль без ошибок (кроме шума среды: подложка, WebGL) | **PASS** | [] |  |
| UI 375-ru | E | нет связи · тепловая карта: понятное сообщение и «Повторить»; после связи «Повторить» возвращает данные | **PASS** | {"opened":true,"message":true,"retry":true,"recovered":true} | 375-ru-E-heat.jpg |
| UI 375-ru | E | нет связи · «Мои обращения»: понятное сообщение и «Повторить»; после связи «Повторить» возвращает данные | **PASS** | {"opened":true,"message":true,"retry":true,"recovered":true} | 375-ru-E-mine.jpg |
| UI 375-ru | E | нет связи · «Картина дня»: понятное сообщение и «Повторить»; после связи «Повторить» возвращает данные | **PASS** | {"opened":true,"message":true,"retry":true,"recovered":true} | 375-ru-E-summary.jpg |
| UI 375-kk | 0 | шапка: ҚАЗ/РУС на виду, язык страницы переключился | **PASS** | {"lang":"kk"} | 375-kk-0-start.jpg |
| UI 375-kk | 0 | нет горизонтальной прокрутки | **PASS** | {"scrollW":375,"w":375} |  |
| UI 375-kk | 0 | надписи не закрыты другими панелями (частично) | **FAIL** | {"n":1,"ex":["«Балалар алаңы сынған» под «Мәселе туралы хабарлау»"]} |  |
| UI 375-kk | 0 | короткие надписи не обрезаны многоточием (название в шапке, кнопки) | **PASS** | {"n":0,"ex":[]} |  |
| UI 375-kk | 0 | контраст текста ≥ 4.5:1 (крупный ≥ 3:1), UX_BRIEF правило 2 | **FAIL** | {"n":2,"ex":["3.40:1 «соңғы 30 күнде» rgb(126, 138, 133) на rgb(248,249,247)","3.40:1 «Ағаштар, көгал» rgb(126, 138, 133) на rgb(248,249,247)"]} |  |
| UI 375-kk | 0 | нет ключей перевода и технических слов | **PASS** | {"raw":[],"tech":[]} |  |
| UI 375-kk | 0 | шрифт: нет текста мельче 13 px (основной ≥ 15 px, CLEAN_PASS §4) | **PASS** | {"tiny":0,"ex":[],"under15":23,"ex15":["13px «Нұра ·»","13px «Есіл ·»","13px «Сарайшық ·»","13px «аз»","13px «көп»","13px «·»"]} |  |
| UI 375-kk | 0 | зоны нажатия ≥ 40 px (цель — 48 px) | **PASS** | {"under40N":0,"under40":[],"under48":"10/20"} |  |
| UI 375-kk | 0 | выбор ҚАЗ/РУС сохраняется после перезагрузки страницы | **PASS** |  |  |
| UI 375-kk | 0 | ҚАЗ: на экране нет строк, оставшихся по-русски | **PASS** | {"n":0,"ex":[]} |  |
| UI 375-kk | 0 | ҚАЗ: во всей странице (с прокруткой панелей) нет строк по-русски | **PASS** | {"n":0,"ex":[]} |  |
| UI 375-kk | 1 | главная кнопка «Мәселе туралы хабарлау» есть и открывает шаг «Где проблема?» | **PASS** | {"resident_view":true} | 375-kk-1-start.jpg |
| UI 375-kk | 1 | нажатие по значку на остановке выбирает место (значок не перехватывает нажатие) | **PASS** | {"under":"r07-badge maplibregl-marker maplibregl-m"} |  |
| UI 375-kk | 1 | после нажатия на карту в форме предложена остановка «Национальный кардиологический центр» | **PASS** | {"point":{"x":187.49999995180897,"y":365.3999999642077,"onCanvas":false,"under":"r07-badge maplibregl-marker maplibregl-m","near":{"x":187.49999995180897,"y":395.3999999642077,"r":30}},"names":["Национальный кардиологиче | 375-kk-1-target.jpg |
| UI 375-kk | 2 | модель предложила категорию «Жарықтандыру» («Ұқсас санат:») | **PASS** | {"textbox":true,"suggested":true,"catShown":true} | 375-kk-2-category.jpg |
| UI 375-kk | 2 | после отправки: «Я тоже» (если уже сообщали) → «Ваш голос учтён», иначе «Обращение отправлено» | **PASS** | {"sent":true,"next":true,"metoo":false,"done":true} | 375-kk-2-sent.jpg |
| UI 375-kk | 3 | тепловая карта у остановки: цвет нарисован, рядом число людей, легенда с числами видна (с FINAL-3 — строка «мало ▬ много», числа под «?») | **PASS** | {"map":true,"layers":14,"rendered":26,"badges":1,"legend":true} | 375-kk-3-heat.jpg |
| UI 375-kk | 3 | фильтры: «Освещение» + «30 дней» → «Сбросить» → снова «Все категории» | **PASS** | {"opened":true,"chip":true,"reset":true,"back":true} |  |
| UI 375-kk | 3 | «Горячие места» → место из списка: значок выбранного места виден на карте и ничем не закрыт | **PASS** | [{"title":"4 Таргабатай көшесі маңындағы аула Балалар алаңы с","badge":true,"inView":true,"at":[158,290],"covered":null},{"title":"11 Коксенгир көшесі маңындағы аула Ағаштар, көгал ","badge":true,"inView":true,"at":[158, | 375-kk-3-hot.jpg |
| UI 375-kk | 4 | «Картина дня»: открылась, 4 крупных числа, «В работе», «Просрочено» | **PASS** | {"day":true,"placeholder_soon":false,"kpis":4,"kpiText":true,"overdue":true} | 375-kk-4-day.jpg |
| UI 375-kk | 5 | вход сотрудника: «Для сотрудников» → имя и пароль → кабинет открыт | **PASS** | {"opened":true,"ok":true,"ru_in_kk":[],"tech":[]} | 375-kk-5-login.jpg |
| UI 375-kk | 5 | кабинет сотрудника: нет технических слов (адреса API, роли сервера) | **PASS** | {"tech":[]} |  |
| UI 375-kk | 5 | ҚАЗ: форма входа и кабинет сотрудника по-казахски | **PASS** | {"ru":[]} |  |
| UI 375-kk | 5 | каталог «Что построить?»: сквер, площадка, спортплощадка, остановка, освещение | **PASS** | {"catalog":true,"unfolded":true,"kinds":["square","playground","sports","stop","lighting"],"projects_layer":true} | 375-kk-5-catalog.jpg |
| UI 375-kk | 5 | «Гүлзар» → нажать на карту → ↺ ↻ → «Поставить»: «Проект поставлен», на карте табличка проекта 2027 | **PASS** | {"hint":false,"rotate":[true,true],"placedClick":true,"placedMsg":true,"label_px_from_place":25} | 375-kk-5-placed.jpg |
| UI 375-kk | 5 | после «Поставить» проект виден: место на карте не закрыто сообщением или каталогом | **PASS** | {"place":[187,365],"at_place":null,"at_label":null} | 375-kk-5-placed.jpg |
| UI 375-kk | 5 | кнопка «3D» наклоняет карту | **PASS** | {"b3d":true,"pitch0":0,"pitch1":51.99999999999999} | 375-kk-5-3d.jpg |
| UI 375-kk | 5 | житель: табличка проекта → карточка → «За» → «Голос учтён» / «Ваш голос: за» | **PASS** | {"label":true,"voted":true,"saved":true} | 375-kk-5-vote.jpg |
| UI 375-kk | 5 | акимат: карточка проекта → «Удалить» → «Проект удалён» | **PASS** | {"label":true,"delClick":true,"deleted":true} |  |
| UI 375-kk | 5 | слои → «Только жалобы и работы»: каталог «Что построить?» скрыт | **PASS** |  |  |
| UI 375-kk | 6 | карточка места открыта: значок выбранного места виден на карте и ничем не закрыт (шторка, шапка, кнопки) | **PASS** | {"badge":true,"inView":true,"at":[187,365],"covered":null} |  |
| UI 375-kk | 6 | акимат: карточка остановки → «Взять в работу» (если место ещё не в работе) → «Отметить исправленным» → «Түзетілді», зелёным на карте (с волны 2 — «служба сообщила», ждёт проверки жителей) | **PASS** | {"under":"r07-badge maplibregl-marker maplibregl-m","take":true,"fix":true,"fixForm":true,"fixFormSent":true,"fixedShown":true,"green":false,"reportedCard":true} | 375-kk-6-fixed.jpg |
| UI 375-kk | 6 | житель: «Менің өтініштерім» → у обращения статус «Түзетілді» (с волны 2 — «Қызмет түзетілгенін хабарлады») | **PASS** | {"mineOpen":true,"mineFixed":false,"mineReported":true} | 375-kk-6-mine.jpg |
| UI 375-kk | 7 | житель проверяет ремонт: «Да, исправлено» → «Проверено жителями» | **PASS** | {"verified":true} | 375-kk-7-verified.jpg |
| UI 375-kk | * | консоль без ошибок (кроме шума среды: подложка, WebGL) | **PASS** | [] |  |
| UI 375-kk | E | нет связи · тепловая карта: понятное сообщение и «Повторить»; после связи «Повторить» возвращает данные | **PASS** | {"opened":true,"message":true,"retry":true,"recovered":true} | 375-kk-E-heat.jpg |
| UI 375-kk | E | нет связи · «Мои обращения»: понятное сообщение и «Повторить»; после связи «Повторить» возвращает данные | **PASS** | {"opened":true,"message":true,"retry":true,"recovered":true} | 375-kk-E-mine.jpg |
| UI 375-kk | E | нет связи · «Картина дня»: понятное сообщение и «Повторить»; после связи «Повторить» возвращает данные | **PASS** | {"opened":true,"message":true,"retry":true,"recovered":true} | 375-kk-E-summary.jpg |

Время шагов, с (паузы теста + ожидание страницы):

| Слой | 0 | 1 | 2 | 3 | 4 | 5 | 6 | 7 | * | E | всего |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| API | 7.0 | 0.0 | 0.1 | 0.0 | 0.2 | 0.3 | 0.0 |  |  |  | 7.6 |
| UI 1366-ru | 9.5 | 10.1 | 10.4 | 31.6 | 3.8 | 61.1 | 19.8 | 2.7 | 0.0 | 32.8 | 181.8 |
| UI 1366-kk | 12.8 | 10.2 | 10.8 | 30.0 | 3.8 | 61.6 | 19.9 | 2.7 | 0.0 | 32.6 | 184.3 |
| UI 375-ru | 7.5 | 8.4 | 10.8 | 24.4 | 4.1 | 52.6 | 16.4 | 2.6 | 0.0 | 32.4 | 159.4 |
| UI 375-kk | 10.2 | 8.2 | 10.8 | 24.1 | 4.1 | 52.7 | 18.6 | 2.6 | 0.0 | 32.4 | 163.8 |
