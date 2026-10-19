# R10 e2e · сценарий демо · ac0140f9

```
{"glass":"keep","glass_seen":{"1366-ru":{"0-start":{"off":false,"blurred":24},"1-start":{"off":false,"blurred":24},"1-target":{"off":false,"blurred":24},"2-category":{"off":false,"blurred":24},"2-sent":{"off":false,"blurred":24},"3-heat":{"off":false,"blurred":24},"3-hot":{"off":false,"blurred":24},"4-day":{"off":false,"blurred":25},"5-login":{"off":false,"blurred":24},"5-catalog":{"off":false,"blurred":25},"5-placed":{"off":false,"blurred":25},"5-3d":{"off":false,"blurred":25},"5-vote":{"off":false,"blurred":24},"6-fixed":{"off":false,"blurred":24},"6-mine":{"off":false,"blurred":26},"7-verified":{"off":false,"blurred":26}},"375-ru":{"0-start":{"off":false,"blurred":18},"1-start":{"off":false,"blurred":18},"1-target":{"off":false,"blurred":18},"2-category":{"off":false,"blurred":18},"2-sent":{"off":false,"blurred":18},"3-heat":{"off":false,"blurred":18},"3-hot":{"off":false,"blurred":18},"4-day":{"off":false,"blurred":19},"5-login":{"off":false,"blurred":17},"5-catalog":{"off":false,"blurred":17},"5-placed":{"off":false,"blurred":17},"5-3d":{"off":false,"blurred":17},"5-vote":{"off":false,"blurred":18},"6-fixed":{"off":false,"blurred":18},"6-mine":{"off":false,"blurred":20},"7-verified":{"off":false,"blurred":20}}},"root":"/tmp/claude-0/-home-user-GOV-DIPLOME/07a536ce-6785-529f-986d-09bb0dfa43d5/scratchpad/stand4","sha":"ac0140f9","base":"(свой сервер)","seeds":["seed-demo","seed-r14-demo"],"sizes":["1366x768","375x812"],"langs":["ru"],"when":"2026-10-13T18:10:06.456Z","node":"v22.22.0","total_ms":425320}
```

Итого: PASS 93, FAIL 2, NOT_RUN 0

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
| API | 1 | POST /complaints: запись §5 (id c-…, status new, target сохранён) | **PASS** | {"status":201,"id":"c-b8d45ce2cab2df54","st":"new"} |  |
| API | 2 | /similar находит только что поданную жалобу на ту же остановку | **PASS** | {"status":200,"n":1,"top":{"complaint_id":"c-b8d45ce2cab2df54","score":0.798,"target":{"id":"osm-node-13394597038","kind":"object","label_kk":"«Республиканский диагностический центр» аялдамасы","label_ru":"Остановка «Рес |  |
| API | 2 | «Я тоже» другим устройством: metoo +1 | **PASS** | {"status":200,"metoo":1} |  |
| API | 2 | повторное «Я тоже» с того же устройства не увеличивает счёт | **PASS** | {"status":200,"metoo":1} |  |
| API | 3 | /heat (Нура, 30 дней, z16): цель жалобы есть, level ≥ 1, count ≥ 1, форма есть | **PASS** | {"status":200,"items":32,"target":{"level":4,"count":21,"weight":15.609,"kind":"object"}} |  |
| API | 3 | смысловой зум: z10 отдаёт районы, а не отдельные остановки | **PASS** | {"status":200,"n":6,"kinds":["district"]} |  |
| API | 4 | /akim/summary: KPI, темы, районы, горячие места, просрочки, отставание, текст ru/kk | **PASS** | {"status":200,"complaints_available":true,"sources":{"complaints":"r07","objects":"r06","proposals":"r06","heat":"r07"},"hot":10} |  |
| API | 5 | вход сотрудника акимата (сессия + CSRF) | **PASS** | {"ok":true,"status":200} |  |
| API | 5 | сотрудник вошёл заранее: похожая жалоба для «Я тоже» с его сессией — то же число людей, что без входа (LOCAL_FINAL P1) | **PASS** | {"similar":200,"id":"c-demo4eca27874085ec47","public":{"status":200,"reporters":3,"metoo":2,"people":3},"staff":{"status":200,"reporters":3,"metoo":2,"people":3}} |  |
| API | 5 | GET /proposals: демо-предложения (seed-r14-demo) со статусом | **PASS** | {"status":200,"n":5,"statuses":["proposal"]} |  |
| API | 5 | POST /proposals (сквер) от сотрудника | **PASS** | {"status":201,"id":"p-145d65445d07","st":"proposal"} |  |
| API | 5 | голос «За» +1, повтор с того же устройства не удваивает | **PASS** | {"first":[200,1],"second":[200,1]} |  |
| API | 6 | сотрудник: «Взять в работу» → «Исправлено» | **PASS** | {"in_progress":200,"fixed":200} |  |
| API | 6 | после «исправлено» цель зелёная (fixed_until задан, вес обнулён) — с волны 2: fixed_kind reported, ждёт проверки жителей | **PASS** | {"item":{"level":"fixed","weight":0,"fixed_until":"2026-10-20T23:03:12+05:00","fixed_kind":"reported","color":"#97C459"}} |  |
| API | 6 | GET /complaints: статус fixed и история статусов | **PASS** | {"status":200,"st":"fixed","history":3} |  |
| UI 1366-ru | 0 | шапка: ҚАЗ/РУС на виду, язык страницы переключился | **PASS** | {"lang":"ru"} | 1366-ru-0-start.jpg |
| UI 1366-ru | 0 | нет горизонтальной прокрутки | **PASS** | {"scrollW":1366,"w":1366} |  |
| UI 1366-ru | 0 | надписи не закрыты другими панелями (частично) | **PASS** | {"n":0,"ex":[]} |  |
| UI 1366-ru | 0 | короткие надписи не обрезаны многоточием (название в шапке, кнопки) | **PASS** | {"n":0,"ex":[]} |  |
| UI 1366-ru | 0 | контраст текста ≥ 4.5:1 (крупный ≥ 3:1), UX_BRIEF правило 2 | **PASS** | {"n":0,"ex":[]} |  |
| UI 1366-ru | 0 | нет ключей перевода и технических слов | **PASS** | {"raw":[],"tech":[]} |  |
| UI 1366-ru | 0 | шрифт: нет текста мельче 13 px (основной ≥ 15 px, CLEAN_PASS §4) | **PASS** | {"tiny":0,"ex":[],"under15":35,"ex15":["13px «Нура ·»","13px «Байконур ·»","13px «Есиль ·»","13px «Сарайшык ·»","13px «Сарыарка ·»","13px «Алматы ·»"]} |  |
| UI 1366-ru | 0 | зоны нажатия ≥ 40 px (цель — 48 px) | **PASS** | {"under40N":0,"under40":[],"under48":"18/26"} |  |
| UI 1366-ru | 0 | выбор ҚАЗ/РУС сохраняется после перезагрузки страницы | **PASS** |  |  |
| UI 1366-ru | 1 | клавиатура: Tab доходит до главной кнопки (≤ 40), рамка фокуса видна | **PASS** | {"tabs":1,"via":"skip-link + Enter","primary":true,"ring":true,"text":"Сообщить о проблеме"} |  |
| UI 1366-ru | 1 | главная кнопка «Сообщить о проблеме» есть и открывает шаг «Где проблема?» | **PASS** | {"resident_view":true} | 1366-ru-1-start.jpg |
| UI 1366-ru | 1 | нажатие по значку на остановке выбирает место (значок не перехватывает нажатие) | **PASS** | {"under":"r07-badge r07-badge--new maplibregl-mark"} |  |
| UI 1366-ru | 1 | после нажатия на карту в форме предложена остановка «Хан Шатыр» | **PASS** | {"point":{"x":682.9999999088413,"y":345.59999999976225,"onCanvas":false,"under":"r07-badge r07-badge--new maplibregl-mark","near":{"x":682.9999999088413,"y":375.59999999976225,"r":30}},"names":["Хан Шатыр"]} | 1366-ru-1-target.jpg |
| UI 1366-ru | 2 | модель предложила категорию «Освещение» («Похоже на:») | **PASS** | {"textbox":true,"suggested":true,"catShown":true} | 1366-ru-2-category.jpg |
| UI 1366-ru | 2 | после отправки: «Я тоже» (если уже сообщали) → «Ваш голос учтён», иначе «Обращение отправлено» | **PASS** | {"sent":true,"next":true,"metoo":true,"done":true} | 1366-ru-2-sent.jpg |
| UI 1366-ru | 3 | тепловая карта у остановки: цвет нарисован, рядом число людей, легенда с числами видна (с FINAL-3 — строка «мало ▬ много», числа под «?») | **PASS** | {"map":true,"layers":14,"rendered":52,"badges":11,"legend":true} | 1366-ru-3-heat.jpg |
| UI 1366-ru | 3 | фильтры: «Освещение» + «30 дней» → «Сбросить» → снова «Все категории» | **PASS** | {"opened":true,"chip":true,"reset":true,"back":true} |  |
| UI 1366-ru | 3 | «Горячие места» → место из списка: значок выбранного места виден на карте и ничем не закрыт | **PASS** | [{"title":"6 Остановка «Хан Шатыр» Освещение · 6 чел.","badge":true,"inView":true,"at":[856,417],"covered":null},{"title":"11 Двор у ул. Коксенгир Деревья, газон · 11 чел.","badge":true,"inView":true,"at":[858,388],"cove | 1366-ru-3-hot.jpg |
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
| UI 375-ru | 0 | шапка: ҚАЗ/РУС на виду, язык страницы переключился | **PASS** | {"lang":"ru"} | 375-ru-0-start.jpg |
| UI 375-ru | 0 | нет горизонтальной прокрутки | **PASS** | {"scrollW":375,"w":375} |  |
| UI 375-ru | 0 | надписи не закрыты другими панелями (частично) | **PASS** | {"n":0,"ex":[]} |  |
| UI 375-ru | 0 | короткие надписи не обрезаны многоточием (название в шапке, кнопки) | **PASS** | {"n":0,"ex":[]} |  |
| UI 375-ru | 0 | контраст текста ≥ 4.5:1 (крупный ≥ 3:1), UX_BRIEF правило 2 | **FAIL** | {"n":3,"ex":["3.40:1 «Долго ждать, нет расписани» rgb(126, 138, 133) на rgb(248,249,247)","3.40:1 «Опасный или неудобный пере» rgb(126, 138, 133) на rgb(248,249,247)","3.40:1 «Гололёд, не посыпано» rgb(126, 138, 133) на  |  |
| UI 375-ru | 0 | нет ключей перевода и технических слов | **PASS** | {"raw":[],"tech":[]} |  |
| UI 375-ru | 0 | шрифт: нет текста мельче 13 px (основной ≥ 15 px, CLEAN_PASS §4) | **FAIL** | {"tiny":3,"ex":["12px «Долго ждать, нет расписания · »","12px «Опасный или неудобный перекрёс»","12px «Гололёд, не посыпано»"],"under15":11,"ex15":["13px «Байконур ·»","13px «Алматы ·»","13px «мало»","13px «много»","13px |  |
| UI 375-ru | 0 | зоны нажатия ≥ 40 px (цель — 48 px) | **PASS** | {"under40N":0,"under40":[],"under48":"5/11"} |  |
| UI 375-ru | 0 | выбор ҚАЗ/РУС сохраняется после перезагрузки страницы | **PASS** |  |  |
| UI 375-ru | 1 | главная кнопка «Сообщить о проблеме» есть и открывает шаг «Где проблема?» | **PASS** | {"resident_view":true} | 375-ru-1-start.jpg |
| UI 375-ru | 1 | нажатие по значку на остановке выбирает место (значок не перехватывает нажатие) | **PASS** | {"under":"r07-badge maplibregl-marker maplibregl-m"} |  |
| UI 375-ru | 1 | после нажатия на карту в форме предложена остановка «Центр материнства и детства» | **PASS** | {"point":{"x":187.50000006262275,"y":365.399999996301,"onCanvas":false,"under":"r07-badge maplibregl-marker maplibregl-m","near":{"x":187.50000006262275,"y":335.399999996301,"r":30}},"names":["Центр материнства и детства | 375-ru-1-target.jpg |
| UI 375-ru | 2 | модель предложила категорию «Освещение» («Похоже на:») | **PASS** | {"textbox":true,"suggested":true,"catShown":true} | 375-ru-2-category.jpg |
| UI 375-ru | 2 | после отправки: «Я тоже» (если уже сообщали) → «Ваш голос учтён», иначе «Обращение отправлено» | **PASS** | {"sent":true,"next":true,"metoo":false,"done":true} | 375-ru-2-sent.jpg |
| UI 375-ru | 3 | тепловая карта у остановки: цвет нарисован, рядом число людей, легенда с числами видна (с FINAL-3 — строка «мало ▬ много», числа под «?») | **PASS** | {"map":true,"layers":14,"rendered":26,"badges":2,"legend":true} | 375-ru-3-heat.jpg |
| UI 375-ru | 3 | фильтры: «Освещение» + «30 дней» → «Сбросить» → снова «Все категории» | **PASS** | {"opened":true,"chip":true,"reset":true,"back":true} |  |
| UI 375-ru | 3 | «Горячие места» → место из списка: значок выбранного места виден на карте и ничем не закрыт | **PASS** | [{"title":"4 Двор у ул. Таргабатай Сломана детская площадка ·","badge":true,"inView":true,"at":[160,318],"covered":null},{"title":"11 Двор у ул. Коксенгир Деревья, газон · 11 чел.","badge":true,"inView":true,"at":[158,25 | 375-ru-3-hot.jpg |
| UI 375-ru | 4 | «Картина дня»: открылась, 4 крупных числа, «В работе», «Просрочено» | **PASS** | {"day":true,"placeholder_soon":false,"kpis":4,"kpiText":true,"overdue":true} | 375-ru-4-day.jpg |
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
| API | 10.2 | 0.0 | 0.1 | 0.1 | 0.2 | 0.4 | 0.0 |  |  |  | 11.0 |
| UI 1366-ru | 13.5 | 14.7 | 11.7 | 47.0 | 4.3 | 76.6 | 22.5 | 2.8 | 0.0 | 42.2 | 235.2 |
| UI 375-ru | 10.1 | 9.1 | 11.2 | 28.5 | 4.4 | 58.9 | 19.4 | 2.7 | 0.0 | 34.8 | 179.0 |
