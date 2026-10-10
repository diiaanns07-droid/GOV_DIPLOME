# R10 e2e · сценарий демо · 4ca9aef

```
{"root":"<worktree 4ca9aef>","sha":"4ca9aef","base":"http://127.0.0.1:<порт>/","seeds":[],"sizes":["1366x768","375x812"],"langs":["ru","kk"],"when":"2026-10-10T19:22:47.368Z","node":"v22.22.0"}
```

Итого: PASS 131, FAIL 5, NOT_RUN 0

| Слой | Шаг | Проверка | Итог | Подробно | Кадр |
|---|---|---|---|---|---|
| API | 0 | шлюз v2: все маршруты ready | **PASS** | {"not_ready":[]} |  |
| API | 2 | текст DEMO_SCRIPT (смесь kk/ru) → «Освещение» с подсказкой | **PASS** | {"status":200,"category":"lighting","score":0.5,"suggest":true,"model":"civic-clf-logreg-kw-cf4464341-pe9ba054a+civic-kw12-r03"} |  |
| API | 2 | /similar сразу после запуска сервера (до первой загрузки страницы) отвечает 200 | **PASS** | {"status":200} |  |
| API | 2 | чистая база демо: /similar по тексту DEMO_SCRIPT у остановки находит похожие (иначе «Я тоже» не будет) | **PASS** | {"status":200,"n":3,"stop":"Хан Шатыр"} |  |
| API | 1 | /targets у остановки: первый кандидат — реальный объект OSM ≤ 60 м с подписью | **PASS** | {"status":200,"first":{"id":"osm-node-13394597038","label":"Остановка «Республиканский диагностический центр»","d":0},"n":1} |  |
| API | 2 | /classify (ru) → «Остановки и транспорт», ответ по §7 | **PASS** | {"status":200,"category":"transport","score":1,"needs_review":true,"model":"civic-clf-logreg-kw-cf4464341-pe9ba054a+civic-kw12-r03"} |  |
| API | 2 | /classify (kk) → «Остановки и транспорт», ответ по §7 | **PASS** | {"status":200,"category":"transport","score":1,"needs_review":true,"model":"civic-clf-logreg-kw-cf4464341-pe9ba054a+civic-kw12-r03"} |  |
| API | 2 | /classify (mixed) → «Остановки и транспорт», ответ по §7 | **PASS** | {"status":200,"category":"transport","score":1,"needs_review":true,"model":"civic-clf-logreg-kw-cf4464341-pe9ba054a+civic-kw12-r03"} |  |
| API | 1 | POST /complaints: запись §5 (id c-…, status new, target сохранён) | **PASS** | {"status":201,"id":"c-e1638462087f90e9","st":"new"} |  |
| API | 2 | /similar находит только что поданную жалобу на ту же остановку | **PASS** | {"status":200,"n":1,"top":{"complaint_id":"c-e1638462087f90e9","score":0.798,"target":{"id":"osm-node-13394597038","kind":"object","label_kk":"«Республиканский диагностический центр» аялдамасы","label_ru":"Остановка «Рес |  |
| API | 2 | «Я тоже» другим устройством: metoo +1 | **PASS** | {"status":200,"metoo":1} |  |
| API | 2 | повторное «Я тоже» с того же устройства не увеличивает счёт | **PASS** | {"status":200,"metoo":1} |  |
| API | 3 | /heat (Нура, 30 дней, z16): цель жалобы есть, level ≥ 1, count ≥ 1, форма есть | **PASS** | {"status":200,"items":31,"target":{"level":4,"count":21,"weight":15.609,"kind":"object"}} |  |
| API | 3 | смысловой зум: z10 отдаёт районы, а не отдельные остановки | **PASS** | {"status":200,"n":6,"kinds":["district"]} |  |
| API | 4 | /akim/summary: KPI, темы, районы, горячие места, просрочки, отставание, текст ru/kk | **PASS** | {"status":200,"complaints_available":true,"sources":{"complaints":"r07","objects":"r06","proposals":"r06","heat":"r07"},"hot":10} |  |
| API | 5 | вход сотрудника акимата (сессия + CSRF) | **PASS** | {"ok":true,"status":200} |  |
| API | 5 | GET /proposals: демо-предложения (seed-r14-demo) со статусом | **PASS** | {"status":200,"n":5,"statuses":["proposal"]} |  |
| API | 5 | POST /proposals (сквер) от сотрудника | **PASS** | {"status":201,"id":"p-103d6f993d81","st":"proposal"} |  |
| API | 5 | голос «За» +1, повтор с того же устройства не удваивает | **PASS** | {"first":[200,1],"second":[200,1]} |  |
| API | 6 | сотрудник: «Взять в работу» → «Исправлено» | **PASS** | {"in_progress":200,"fixed":200} |  |
| API | 6 | после «исправлено» цель зелёная (fixed_until задан, вес обнулён) | **PASS** | {"item":{"level":"fixed","weight":0,"fixed_until":"2026-10-18T00:13:53+05:00"}} |  |
| API | 6 | GET /complaints: статус fixed и история статусов | **PASS** | {"status":200,"st":"fixed","history":3} |  |
| UI 1366-ru | 0 | шапка: ҚАЗ/РУС на виду, язык страницы переключился | **PASS** | {"lang":"ru"} | 1366-ru-0-start.jpg |
| UI 1366-ru | 0 | нет горизонтальной прокрутки | **PASS** | {"scrollW":1366,"w":1366} |  |
| UI 1366-ru | 0 | нет ключей перевода и технических слов | **PASS** | {"raw":[],"tech":[]} |  |
| UI 1366-ru | 0 | шрифт: нет текста мельче 14 px (основной ≥ 16 px) | **PASS** | {"tiny":0,"ex":[],"under16":18,"ex16":["15px «Сколько человек сообщили»","14px «Свежие жалобы ярче: за 2 недел»","14px «Приблизьте карту, чтобы увидет»","14px «Город и жители вместе»","14px «3D»","14px «Больше всего жало |  |
| UI 1366-ru | 0 | зоны нажатия ≥ 40 px (цель — 48 px) | **PASS** | {"under40N":0,"under40":[],"under48":"19/26"} |  |
| UI 1366-ru | 0 | выбор ҚАЗ/РУС сохраняется после перезагрузки страницы | **PASS** |  |  |
| UI 1366-ru | 1 | клавиатура: Tab доходит до главной кнопки (≤ 40), рамка фокуса видна | **PASS** | {"tabs":1,"via":"skip-link + Enter","primary":true,"ring":true,"text":"Сообщить о проблеме"} |  |
| UI 1366-ru | 1 | главная кнопка «Сообщить о проблеме» есть и открывает шаг «Где проблема?» | **PASS** | {"resident_view":true} | 1366-ru-1-start.jpg |
| UI 1366-ru | 1 | нажатие по значку на остановке выбирает место (значок не перехватывает нажатие) | **PASS** | {"under":"r07-badge maplibregl-marker maplibregl-m"} |  |
| UI 1366-ru | 1 | после нажатия на карту в форме предложена остановка «Хан Шатыр» | **PASS** | {"point":{"x":682.9999999933773,"y":345.60000001721914,"onCanvas":false,"under":"r07-badge maplibregl-marker maplibregl-m","near":{"x":682.9999999933773,"y":375.60000001721914,"r":30}},"names":["Хан Шатыр"]} | 1366-ru-1-target.jpg |
| UI 1366-ru | 2 | модель предложила категорию «Освещение» («Похоже на:») | **PASS** | {"textbox":true,"suggested":true,"catShown":true} | 1366-ru-2-category.jpg |
| UI 1366-ru | 2 | после отправки: «Я тоже» (если уже сообщали) → «Ваш голос учтён», иначе «Обращение отправлено» | **PASS** | {"sent":true,"metoo":true,"done":true} | 1366-ru-2-sent.jpg |
| UI 1366-ru | 3 | тепловая карта у остановки: цвет нарисован, рядом число людей, легенда с числами видна | **PASS** | {"map":true,"layers":13,"rendered":54,"badges":17,"legend":true} | 1366-ru-3-heat.jpg |
| UI 1366-ru | 3 | фильтры: «Освещение» + «30 дней» → «Сбросить» → снова «Все категории» | **PASS** | {"opened":true,"chip":true,"reset":true,"back":true} |  |
| UI 1366-ru | 4 | «Картина дня»: открылась, 4 крупных числа, «В работе», «Просрочено» | **PASS** | {"day":true,"placeholder_soon":false,"kpis":4,"kpiText":true,"overdue":true} | 1366-ru-4-day.jpg |
| UI 1366-ru | 5 | вход сотрудника: «Для сотрудников» → имя и пароль → кабинет открыт | **PASS** | {"opened":true,"ok":true,"tech":[]} | 1366-ru-5-login.jpg |
| UI 1366-ru | 5 | кабинет сотрудника: нет технических слов (адреса API, роли сервера) | **PASS** | {"tech":[]} |  |
| UI 1366-ru | 5 | каталог «Что построить?»: сквер, площадка, спортплощадка, остановка, освещение | **PASS** | {"catalog":true,"unfolded":true,"kinds":["square","playground","sports","stop","lighting"]} | 1366-ru-5-catalog.jpg |
| UI 1366-ru | 5 | «Сквер» → нажать на карту → «Поставить»: «Проект поставлен», на карте табличка проекта 2027 | **PASS** | {"hint":true,"placedClick":true,"placedMsg":true,"label_px_from_place":26} | 1366-ru-5-placed.jpg |
| UI 1366-ru | 5 | житель: табличка проекта → карточка → «За» → «Голос учтён» / «Ваш голос: за» | **PASS** | {"label":true,"voted":true,"saved":true} | 1366-ru-5-vote.jpg |
| UI 1366-ru | 5 | акимат: карточка проекта → «Удалить» → «Проект удалён» | **PASS** | {"label":true,"delClick":true,"deleted":true} |  |
| UI 1366-ru | 6 | акимат: карточка остановки → «Взять в работу» → «Отметить исправленным» → «Исправлено», зелёным на карте | **PASS** | {"under":"r07-badge maplibregl-marker maplibregl-m","take":true,"fix":true,"fixedShown":true,"green":true} | 1366-ru-6-fixed.jpg |
| UI 1366-ru | 6 | клавиатура: Esc закрывает карточку остановки | **PASS** | {"stillOpen":false} |  |
| UI 1366-ru | 6 | житель: «Мои обращения» → у обращения статус «Исправлено» | **PASS** | {"mineOpen":true,"mineFixed":true} | 1366-ru-6-mine.jpg |
| UI 1366-ru | * | консоль без ошибок (кроме шума среды: подложка, WebGL) | **PASS** | [] |  |
| UI 1366-ru | E | нет связи · тепловая карта: понятное сообщение и «Повторить»; после связи «Повторить» возвращает данные | **PASS** | {"opened":true,"message":true,"retry":true,"recovered":true} | 1366-ru-E-heat.jpg |
| UI 1366-ru | E | нет связи · «Мои обращения»: понятное сообщение и «Повторить»; после связи «Повторить» возвращает данные | **PASS** | {"opened":true,"message":true,"retry":true,"recovered":true} | 1366-ru-E-mine.jpg |
| UI 1366-ru | E | нет связи · «Картина дня»: понятное сообщение и «Повторить»; после связи «Повторить» возвращает данные | **PASS** | {"opened":true,"message":true,"retry":true,"recovered":true} | 1366-ru-E-summary.jpg |
| UI 1366-kk | 0 | шапка: ҚАЗ/РУС на виду, язык страницы переключился | **PASS** | {"lang":"kk"} | 1366-kk-0-start.jpg |
| UI 1366-kk | 0 | нет горизонтальной прокрутки | **PASS** | {"scrollW":1366,"w":1366} |  |
| UI 1366-kk | 0 | нет ключей перевода и технических слов | **PASS** | {"raw":[],"tech":[]} |  |
| UI 1366-kk | 0 | шрифт: нет текста мельче 14 px (основной ≥ 16 px) | **PASS** | {"tiny":0,"ex":[],"under16":18,"ex16":["15px «Қанша адам хабарлады»","14px «Жаңа шағымдар ашығырақ: 2 апта»","14px «Көшелерді, аулаларды және аялд»","14px «Қала мен тұрғындар бірге»","14px «3D»","14px «Ең көп шағым: Нұра |  |
| UI 1366-kk | 0 | зоны нажатия ≥ 40 px (цель — 48 px) | **PASS** | {"under40N":0,"under40":[],"under48":"19/25"} |  |
| UI 1366-kk | 0 | выбор ҚАЗ/РУС сохраняется после перезагрузки страницы | **PASS** |  |  |
| UI 1366-kk | 0 | ҚАЗ: на экране нет строк, оставшихся по-русски | **PASS** | {"n":0,"ex":[]} |  |
| UI 1366-kk | 0 | ҚАЗ: во всей странице (с прокруткой панелей) нет строк по-русски | **PASS** | {"n":0,"ex":[]} |  |
| UI 1366-kk | 1 | клавиатура: Tab доходит до главной кнопки (≤ 40), рамка фокуса видна | **PASS** | {"tabs":1,"via":"skip-link + Enter","primary":true,"ring":true,"text":"Мәселе туралы хабарлау"} |  |
| UI 1366-kk | 1 | главная кнопка «Мәселе туралы хабарлау» есть и открывает шаг «Где проблема?» | **PASS** | {"resident_view":true} | 1366-kk-1-start.jpg |
| UI 1366-kk | 1 | нажатие по значку на остановке выбирает место (значок не перехватывает нажатие) | **PASS** | {"under":"r07-badge maplibregl-marker maplibregl-m"} |  |
| UI 1366-kk | 1 | после нажатия на карту в форме предложена остановка «Центр материнства и детства» | **PASS** | {"point":{"x":682.9999999933773,"y":345.60000000066225,"onCanvas":false,"under":"r07-badge maplibregl-marker maplibregl-m","near":{"x":682.9999999933773,"y":375.60000000066225,"r":30}},"names":["Центр материнства и детст | 1366-kk-1-target.jpg |
| UI 1366-kk | 2 | модель предложила категорию «Жарықтандыру» («Ұқсас санат:») | **PASS** | {"textbox":true,"suggested":true,"catShown":true} | 1366-kk-2-category.jpg |
| UI 1366-kk | 2 | после отправки: «Я тоже» (если уже сообщали) → «Ваш голос учтён», иначе «Обращение отправлено» | **PASS** | {"sent":true,"metoo":false,"done":true} | 1366-kk-2-sent.jpg |
| UI 1366-kk | 3 | тепловая карта у остановки: цвет нарисован, рядом число людей, легенда с числами видна | **PASS** | {"map":true,"layers":13,"rendered":54,"badges":17,"legend":true} | 1366-kk-3-heat.jpg |
| UI 1366-kk | 3 | фильтры: «Освещение» + «30 дней» → «Сбросить» → снова «Все категории» | **PASS** | {"opened":true,"chip":true,"reset":true,"back":true} |  |
| UI 1366-kk | 4 | «Картина дня»: открылась, 4 крупных числа, «В работе», «Просрочено» | **PASS** | {"day":true,"placeholder_soon":false,"kpis":4,"kpiText":true,"overdue":true} | 1366-kk-4-day.jpg |
| UI 1366-kk | 5 | вход сотрудника: «Для сотрудников» → имя и пароль → кабинет открыт | **PASS** | {"opened":true,"ok":true,"ru_in_kk":[],"tech":[]} | 1366-kk-5-login.jpg |
| UI 1366-kk | 5 | кабинет сотрудника: нет технических слов (адреса API, роли сервера) | **PASS** | {"tech":[]} |  |
| UI 1366-kk | 5 | ҚАЗ: форма входа и кабинет сотрудника по-казахски | **PASS** | {"ru":[]} |  |
| UI 1366-kk | 5 | каталог «Что построить?»: сквер, площадка, спортплощадка, остановка, освещение | **PASS** | {"catalog":true,"unfolded":true,"kinds":["square","playground","sports","stop","lighting"]} | 1366-kk-5-catalog.jpg |
| UI 1366-kk | 5 | «Гүлзар» → нажать на карту → «Поставить»: «Проект поставлен», на карте табличка проекта 2027 | **PASS** | {"hint":true,"placedClick":true,"placedMsg":true,"label_px_from_place":26} | 1366-kk-5-placed.jpg |
| UI 1366-kk | 5 | житель: табличка проекта → карточка → «За» → «Голос учтён» / «Ваш голос: за» | **PASS** | {"label":true,"voted":true,"saved":true} | 1366-kk-5-vote.jpg |
| UI 1366-kk | 5 | акимат: карточка проекта → «Удалить» → «Проект удалён» | **PASS** | {"label":true,"delClick":true,"deleted":true} |  |
| UI 1366-kk | 6 | акимат: карточка остановки → «Взять в работу» → «Отметить исправленным» → «Түзетілді», зелёным на карте | **FAIL** | {"under":"r07-badge maplibregl-marker maplibregl-m","take":true,"fix":true,"fixedShown":true,"green":false} | 1366-kk-6-fixed.jpg |
| UI 1366-kk | 6 | клавиатура: Esc закрывает карточку остановки | **PASS** | {"stillOpen":false} |  |
| UI 1366-kk | 6 | житель: «Менің өтініштерім» → у обращения статус «Түзетілді» | **PASS** | {"mineOpen":true,"mineFixed":true} | 1366-kk-6-mine.jpg |
| UI 1366-kk | * | консоль без ошибок (кроме шума среды: подложка, WebGL) | **PASS** | [] |  |
| UI 1366-kk | E | нет связи · тепловая карта: понятное сообщение и «Повторить»; после связи «Повторить» возвращает данные | **PASS** | {"opened":true,"message":true,"retry":true,"recovered":true} | 1366-kk-E-heat.jpg |
| UI 1366-kk | E | нет связи · «Мои обращения»: понятное сообщение и «Повторить»; после связи «Повторить» возвращает данные | **PASS** | {"opened":true,"message":true,"retry":true,"recovered":true} | 1366-kk-E-mine.jpg |
| UI 1366-kk | E | нет связи · «Картина дня»: понятное сообщение и «Повторить»; после связи «Повторить» возвращает данные | **PASS** | {"opened":true,"message":true,"retry":true,"recovered":true} | 1366-kk-E-summary.jpg |
| UI 375-ru | 0 | шапка: ҚАЗ/РУС на виду, язык страницы переключился | **PASS** | {"lang":"ru"} | 375-ru-0-start.jpg |
| UI 375-ru | 0 | нет горизонтальной прокрутки | **PASS** | {"scrollW":375,"w":375} |  |
| UI 375-ru | 0 | нет ключей перевода и технических слов | **PASS** | {"raw":[],"tech":[]} |  |
| UI 375-ru | 0 | шрифт: нет текста мельче 14 px (основной ≥ 16 px) | **PASS** | {"tiny":0,"ex":[],"under16":7,"ex16":["15px «Birge»","14px «3D»","14px «Больше всего жалоб: Нура · 48 »","14px «Примеры: жалобы придуманы, ули»","14px «24 места с жалобами»","14px «Территория»"]} |  |
| UI 375-ru | 0 | зоны нажатия ≥ 40 px (цель — 48 px) | **PASS** | {"under40N":0,"under40":[],"under48":"9/15"} |  |
| UI 375-ru | 0 | выбор ҚАЗ/РУС сохраняется после перезагрузки страницы | **PASS** |  |  |
| UI 375-ru | 1 | главная кнопка «Сообщить о проблеме» есть и открывает шаг «Где проблема?» | **PASS** | {"resident_view":true} | 375-ru-1-start.jpg |
| UI 375-ru | 1 | нажатие по значку на остановке выбирает место (значок не перехватывает нажатие) | **PASS** | {"under":"r07-badge maplibregl-marker maplibregl-m"} |  |
| UI 375-ru | 1 | после нажатия на карту в форме предложена остановка «Жилой комплекс Зелёный Квартал» | **PASS** | {"point":{"x":187.50000000626386,"y":365.40000000375835,"onCanvas":false,"under":"r07-badge maplibregl-marker maplibregl-m","near":{"x":187.50000000626386,"y":395.40000000375835,"r":30}},"names":["Жилой комплекс Зелёный  | 375-ru-1-target.jpg |
| UI 375-ru | 2 | модель предложила категорию «Освещение» («Похоже на:») | **PASS** | {"textbox":true,"suggested":true,"catShown":true} | 375-ru-2-category.jpg |
| UI 375-ru | 2 | после отправки: «Я тоже» (если уже сообщали) → «Ваш голос учтён», иначе «Обращение отправлено» | **PASS** | {"sent":true,"metoo":false,"done":true} | 375-ru-2-sent.jpg |
| UI 375-ru | 3 | тепловая карта у остановки: цвет нарисован, рядом число людей, легенда с числами видна | **PASS** | {"map":true,"layers":13,"rendered":20,"badges":2,"legend":true} | 375-ru-3-heat.jpg |
| UI 375-ru | 3 | фильтры: «Освещение» + «30 дней» → «Сбросить» → снова «Все категории» | **PASS** | {"opened":true,"chip":true,"reset":true,"back":true} |  |
| UI 375-ru | 4 | «Картина дня»: открылась, 4 крупных числа, «В работе», «Просрочено» | **PASS** | {"day":true,"placeholder_soon":false,"kpis":4,"kpiText":true,"overdue":true} | 375-ru-4-day.jpg |
| UI 375-ru | 5 | вход сотрудника: «Для сотрудников» → имя и пароль → кабинет открыт | **PASS** | {"opened":true,"ok":true,"tech":[]} | 375-ru-5-login.jpg |
| UI 375-ru | 5 | кабинет сотрудника: нет технических слов (адреса API, роли сервера) | **PASS** | {"tech":[]} |  |
| UI 375-ru | 5 | каталог «Что построить?»: сквер, площадка, спортплощадка, остановка, освещение | **PASS** | {"catalog":true,"unfolded":true,"kinds":["square","playground","sports","stop","lighting"]} | 375-ru-5-catalog.jpg |
| UI 375-ru | 5 | «Сквер» → нажать на карту → «Поставить»: «Проект поставлен», на карте табличка проекта 2027 | **PASS** | {"hint":false,"placedClick":true,"placedMsg":true,"label_px_from_place":26} | 375-ru-5-placed.jpg |
| UI 375-ru | 5 | житель: табличка проекта → карточка → «За» → «Голос учтён» / «Ваш голос: за» | **PASS** | {"label":true,"voted":true,"saved":true} | 375-ru-5-vote.jpg |
| UI 375-ru | 5 | акимат: карточка проекта → «Удалить» → «Проект удалён» | **PASS** | {"label":true,"delClick":true,"deleted":true} |  |
| UI 375-ru | 6 | акимат: карточка остановки → «Взять в работу» → «Отметить исправленным» → «Исправлено», зелёным на карте | **FAIL** | {"under":"r07-badge maplibregl-marker maplibregl-m","take":false,"fix":true,"fixedShown":false,"green":false} | 375-ru-6-fixed.jpg |
| UI 375-ru | 6 | житель: «Мои обращения» → у обращения статус «Исправлено» | **PASS** | {"mineOpen":true,"mineFixed":true} | 375-ru-6-mine.jpg |
| UI 375-ru | * | консоль без ошибок (кроме шума среды: подложка, WebGL) | **PASS** | [] |  |
| UI 375-ru | E | нет связи · тепловая карта: понятное сообщение и «Повторить»; после связи «Повторить» возвращает данные | **PASS** | {"opened":true,"message":true,"retry":true,"recovered":true} | 375-ru-E-heat.jpg |
| UI 375-ru | E | нет связи · «Мои обращения»: понятное сообщение и «Повторить»; после связи «Повторить» возвращает данные | **PASS** | {"opened":true,"message":true,"retry":true,"recovered":true} | 375-ru-E-mine.jpg |
| UI 375-ru | E | нет связи · «Картина дня»: понятное сообщение и «Повторить»; после связи «Повторить» возвращает данные | **PASS** | {"opened":true,"message":true,"retry":true,"recovered":true} | 375-ru-E-summary.jpg |
| UI 375-kk | 0 | шапка: ҚАЗ/РУС на виду, язык страницы переключился | **PASS** | {"lang":"kk"} | 375-kk-0-start.jpg |
| UI 375-kk | 0 | нет горизонтальной прокрутки | **PASS** | {"scrollW":375,"w":375} |  |
| UI 375-kk | 0 | нет ключей перевода и технических слов | **PASS** | {"raw":[],"tech":[]} |  |
| UI 375-kk | 0 | шрифт: нет текста мельче 14 px (основной ≥ 16 px) | **PASS** | {"tiny":0,"ex":[],"under16":6,"ex16":["15px «Birge»","14px «3D»","14px «Ең көп шағым: Нұра · 47 адам»","14px «Мысалдар: шағымдар ойдан құрас»","14px «Аумақ»","14px «Приблизьте карту, чтобы увидет»"]} |  |
| UI 375-kk | 0 | зоны нажатия ≥ 40 px (цель — 48 px) | **PASS** | {"under40N":0,"under40":[],"under48":"6/10"} |  |
| UI 375-kk | 0 | выбор ҚАЗ/РУС сохраняется после перезагрузки страницы | **PASS** |  |  |
| UI 375-kk | 0 | ҚАЗ: на экране нет строк, оставшихся по-русски | **FAIL** | {"n":1,"ex":["Көшелерді, аулаларды және аялдамаларды көру үшін картаны жақындатыңыз"]} |  |
| UI 375-kk | 0 | ҚАЗ: во всей странице (с прокруткой панелей) нет строк по-русски | **FAIL** | {"n":1,"ex":["Көшелерді, аулаларды және аялдамаларды көру үшін картаны жақындатыңыз"]} |  |
| UI 375-kk | 1 | главная кнопка «Мәселе туралы хабарлау» есть и открывает шаг «Где проблема?» | **PASS** | {"resident_view":true} | 375-kk-1-start.jpg |
| UI 375-kk | 1 | нажатие по значку на остановке выбирает место (значок не перехватывает нажатие) | **PASS** | {"under":"r07-badge maplibregl-marker maplibregl-m"} |  |
| UI 375-kk | 1 | после нажатия на карту в форме предложена остановка «Национальный кардиологический центр» | **PASS** | {"point":{"x":187.50000000626386,"y":365.4000000006264,"onCanvas":false,"under":"r07-badge maplibregl-marker maplibregl-m","near":{"x":187.50000000626386,"y":395.4000000006264,"r":30}},"names":["Национальный кардиологиче | 375-kk-1-target.jpg |
| UI 375-kk | 2 | модель предложила категорию «Жарықтандыру» («Ұқсас санат:») | **PASS** | {"textbox":true,"suggested":true,"catShown":true} | 375-kk-2-category.jpg |
| UI 375-kk | 2 | после отправки: «Я тоже» (если уже сообщали) → «Ваш голос учтён», иначе «Обращение отправлено» | **PASS** | {"sent":true,"metoo":false,"done":true} | 375-kk-2-sent.jpg |
| UI 375-kk | 3 | тепловая карта у остановки: цвет нарисован, рядом число людей, легенда с числами видна | **PASS** | {"map":true,"layers":13,"rendered":20,"badges":2,"legend":true} | 375-kk-3-heat.jpg |
| UI 375-kk | 3 | фильтры: «Освещение» + «30 дней» → «Сбросить» → снова «Все категории» | **PASS** | {"opened":true,"chip":true,"reset":true,"back":true} |  |
| UI 375-kk | 4 | «Картина дня»: открылась, 4 крупных числа, «В работе», «Просрочено» | **PASS** | {"day":true,"placeholder_soon":false,"kpis":4,"kpiText":true,"overdue":true} | 375-kk-4-day.jpg |
| UI 375-kk | 5 | вход сотрудника: «Для сотрудников» → имя и пароль → кабинет открыт | **PASS** | {"opened":true,"ok":true,"ru_in_kk":[],"tech":[]} | 375-kk-5-login.jpg |
| UI 375-kk | 5 | кабинет сотрудника: нет технических слов (адреса API, роли сервера) | **PASS** | {"tech":[]} |  |
| UI 375-kk | 5 | ҚАЗ: форма входа и кабинет сотрудника по-казахски | **PASS** | {"ru":[]} |  |
| UI 375-kk | 5 | каталог «Что построить?»: сквер, площадка, спортплощадка, остановка, освещение | **PASS** | {"catalog":true,"unfolded":true,"kinds":["square","playground","sports","stop","lighting"]} | 375-kk-5-catalog.jpg |
| UI 375-kk | 5 | «Гүлзар» → нажать на карту → «Поставить»: «Проект поставлен», на карте табличка проекта 2027 | **PASS** | {"hint":false,"placedClick":true,"placedMsg":true,"label_px_from_place":26} | 375-kk-5-placed.jpg |
| UI 375-kk | 5 | житель: табличка проекта → карточка → «За» → «Голос учтён» / «Ваш голос: за» | **PASS** | {"label":true,"voted":true,"saved":true} | 375-kk-5-vote.jpg |
| UI 375-kk | 5 | акимат: карточка проекта → «Удалить» → «Проект удалён» | **PASS** | {"label":true,"delClick":true,"deleted":true} |  |
| UI 375-kk | 6 | акимат: карточка остановки → «Взять в работу» → «Отметить исправленным» → «Түзетілді», зелёным на карте | **FAIL** | {"under":"r07-badge maplibregl-marker maplibregl-m","take":true,"fix":true,"fixedShown":true,"green":false} | 375-kk-6-fixed.jpg |
| UI 375-kk | 6 | житель: «Менің өтініштерім» → у обращения статус «Түзетілді» | **PASS** | {"mineOpen":true,"mineFixed":true} | 375-kk-6-mine.jpg |
| UI 375-kk | * | консоль без ошибок (кроме шума среды: подложка, WebGL) | **PASS** | [] |  |
| UI 375-kk | E | нет связи · тепловая карта: понятное сообщение и «Повторить»; после связи «Повторить» возвращает данные | **PASS** | {"opened":true,"message":true,"retry":true,"recovered":true} | 375-kk-E-heat.jpg |
| UI 375-kk | E | нет связи · «Мои обращения»: понятное сообщение и «Повторить»; после связи «Повторить» возвращает данные | **PASS** | {"opened":true,"message":true,"retry":true,"recovered":true} | 375-kk-E-mine.jpg |
| UI 375-kk | E | нет связи · «Картина дня»: понятное сообщение и «Повторить»; после связи «Повторить» возвращает данные | **PASS** | {"opened":true,"message":true,"retry":true,"recovered":true} | 375-kk-E-summary.jpg |
