# R10 · новые пункты волн 1–2 · 12c925ad

```
{"root":"/home/user/bf2f","sha":"12c925ad","when":"2026-10-12T05:42:40.396Z","sizes":["1366x768","375x812"],"langs":["ru","kk"],"node":"v22.22.0","runtime":{"BirgeNearby":true,"BirgeIdeas":false,"BirgeProjects":false,"BirgeComplaintList":true,"BirgeAsk":false,"BirgeQuestions":false,"BirgeShell":true}}
```

Итого: PASS 38, FAIL 0, ЖДЁТ 0, NOT_RUN 5

| Пункт | Что | Владелец | Готово, когда | Состояние |
|---|---|---|---|---|
| W2-4 | «Что делают рядом» | R08 + R06 | Житель видит «Завтра 10–16 нет воды в вашем дворе» и «Зачем перекопали улицу» | **частично** |
| W2-5 | «Нужно решение акима» + W2-8 «Пульс района» | R08 (+R13) | 1–3 решения; 1–5 тревог с причиной и ссылкой на карту | **PASS** |
| M | Обязательные мелочи: серый «нет данных», список у карты, лёгкая карточка до 3D | R07, R05 | POLISH_WAVE_2 «обязательные мелочи» (номер и экран проверки — в LF-2, уведомление → W2-10, язык → W2-6) | **частично** |

| Пункт | Где | Проверка | Итог | Подробно | Кадр |
|---|---|---|---|---|---|
| W2-4 | сборка | «Что делают рядом»: есть в сборке — проверяю | **INFO** | {"static":{"emergency":["web/civic/feedback/categories_v2.js: emergency_phone","web/civic/feedback/complaint-strings.js: complaint.emergency","web/civic/feedback/complaint.js: emergency_phone","ui/civic_feedback/v2/categ |  |
| W2-4 | 1366-ru | меню «Рядом» → свой экран «Что делают рядом» (#nearby), 4 вкладки, карта закрыта, одна главная кнопка | **PASS** | {"opened":true,"hash":"#nearby","title":true,"tabs":[true,true,true,true],"screen":{"map_on_top":false},"primary":["Следить за районом"]} | 1366-ru-W2-4-nearby.jpg |
| W2-4 | 1366-ru | отключения: у каждого «Где», когда, «Источник», «обновлено …»; у перекрытия — «Как обойти»; баннеров ≤ 2 | **PASS** | {"banners":1,"outages":[{"zone":true,"time":true,"source":true,"updated":true,"closure":false,"detour":true,"text":"Вода Пример Не будет холодной воды Когда: завтра 10:00–16:00 Где: ул. Кабанбай батыра, 48–"}]} | 1366-ru-W2-4-outages.jpg |
| W2-4 | 1366-ru | задержки видны («срок перенесён»); «Зачем?» — 4 строки: проблема → почему так → результат → неудобства и срок | **PASS** | {"delay":true,"why":[true,true,true,true]} | 1366-ru-W2-4-why.jpg |
| W2-4 | 1366-ru | подписка: «Следить…» → «Вы подписаны / следите» | **PASS** | {"sub":true,"subd":true} |  |
| W2-4 | 1366-ru | «Карта» в меню возвращает к карте | **PASS** | {"opened":true,"toMap":true,"back":true} |  |
| W2-4 | 1366-kk | меню «Маңайда» → свой экран «Маңайда не істеліп жатыр» (#nearby), 4 вкладки, карта закрыта, одна главная кнопка | **PASS** | {"opened":true,"hash":"#nearby","title":true,"tabs":[true,true,true,true],"screen":{"map_on_top":false},"primary":["Ауданды бақылау"]} | 1366-kk-W2-4-nearby.jpg |
| W2-4 | 1366-kk | отключения: у каждого «Где», когда, «Источник», «обновлено …»; у перекрытия — «Как обойти»; баннеров ≤ 2 | **PASS** | {"banners":1,"outages":[{"zone":true,"time":true,"source":true,"updated":true,"closure":false,"detour":true,"text":"Су Үлгі Суық су болмайды Қашан: ертең 10:00–16:00 Қай жерде: Қабанбай батыр көшесі, 48–56 "}]} | 1366-kk-W2-4-outages.jpg |
| W2-4 | 1366-kk | задержки видны («мерзімі ауыстырылды»); «Не үшін?» — 4 строки: проблема → почему так → результат → неудобства и срок | **PASS** | {"delay":true,"why":[true,true,true,true]} | 1366-kk-W2-4-why.jpg |
| W2-4 | 1366-kk | подписка: «Следить…» → «Вы подписаны / следите» | **PASS** | {"sub":true,"subd":true} |  |
| W2-4 | 1366-kk | «Карта» в меню возвращает к карте | **PASS** | {"opened":true,"toMap":true,"back":true} |  |
| W2-4 | 375-ru | меню «Рядом» → свой экран «Что делают рядом» (#nearby), 4 вкладки, карта закрыта, одна главная кнопка | **PASS** | {"opened":true,"hash":"#nearby","title":true,"tabs":[true,true,true,true],"screen":{"map_on_top":false},"primary":["Следить за районом"]} | 375-ru-W2-4-nearby.jpg |
| W2-4 | 375-ru | отключения: у каждого «Где», когда, «Источник», «обновлено …»; у перекрытия — «Как обойти»; баннеров ≤ 2 | **PASS** | {"banners":1,"outages":[{"zone":true,"time":true,"source":true,"updated":true,"closure":false,"detour":true,"text":"Вода Пример Не будет холодной воды Когда: завтра 10:00–16:00 Где: ул. Кабанбай батыра, 48–"}]} | 375-ru-W2-4-outages.jpg |
| W2-4 | 375-ru | задержки видны («срок перенесён»); «Зачем?» — 4 строки: проблема → почему так → результат → неудобства и срок | **PASS** | {"delay":true,"why":[true,true,true,true]} | 375-ru-W2-4-why.jpg |
| W2-4 | 375-ru | подписка: «Следить…» → «Вы подписаны / следите» | **PASS** | {"sub":true,"subd":true} |  |
| W2-4 | 375-ru | «Карта» в меню возвращает к карте | **PASS** | {"opened":true,"toMap":true,"back":true} |  |
| W2-4 | 375-kk | меню «Маңайда» → свой экран «Маңайда не істеліп жатыр» (#nearby), 4 вкладки, карта закрыта, одна главная кнопка | **PASS** | {"opened":true,"hash":"#nearby","title":true,"tabs":[true,true,true,true],"screen":{"map_on_top":false},"primary":["Ауданды бақылау"]} | 375-kk-W2-4-nearby.jpg |
| W2-4 | 375-kk | отключения: у каждого «Где», когда, «Источник», «обновлено …»; у перекрытия — «Как обойти»; баннеров ≤ 2 | **PASS** | {"banners":1,"outages":[{"zone":true,"time":true,"source":true,"updated":true,"closure":false,"detour":true,"text":"Су Үлгі Суық су болмайды Қашан: ертең 10:00–16:00 Қай жерде: Қабанбай батыр көшесі, 48–56 "}]} | 375-kk-W2-4-outages.jpg |
| W2-4 | 375-kk | задержки видны («мерзімі ауыстырылды»); «Не үшін?» — 4 строки: проблема → почему так → результат → неудобства и срок | **PASS** | {"delay":true,"why":[true,true,true,true]} | 375-kk-W2-4-why.jpg |
| W2-4 | 375-kk | подписка: «Следить…» → «Вы подписаны / следите» | **PASS** | {"sub":true,"subd":true} |  |
| W2-4 | 375-kk | «Карта» в меню возвращает к карте | **PASS** | {"opened":true,"toMap":true,"back":true} |  |
| W2-4 | R09 | события подписки «Рядом» — в «Мои обращения → Что изменилось» | **NOT_RUN** | "дописать при поставке R09 (mine.changes) — R08 отдаёт /nearby/updates" |  |
| W2-5 | сборка | «Нужно решение акима» + W2-8 «Пульс района»: есть в сборке — проверяю | **INFO** | {"static":{"emergency":["web/civic/feedback/categories_v2.js: emergency_phone","web/civic/feedback/complaint-strings.js: complaint.emergency","web/civic/feedback/complaint.js: emergency_phone","ui/civic_feedback/v2/categ |  |
| W2-5 | API | «Нужно решение акима»: 1–3 решения, у каждого — проблема, что блокирует, 2 варианта, нужное решение (ru и kk) | **PASS** | {"available":true,"n":3,"complete":3,"source":"example","demo":true} |  |
| W2-8 | API | «Пульс района»: 1–5 тревог с причиной (рост к обычному уровню) и местом на карте | **PASS** | {"available":true,"n":5,"kinds":["spike_city","spike_city","spike_new","spike","spike"],"method":{"min_reports":5,"spike_ratio":2,"base_weeks":4,"min_metoo_week":8}} |  |
| W2-5 | 1366-ru | «Картина дня»: блок «Нужно решение акима» виден; демо помечено «пример» | **PASS** | {"day":true,"block":true,"demoMark":true} | 1366-ru-W2-5-decisions.jpg |
| W2-8 | 1366-ru | «Картина дня»: «Пульс района» — 1–5 тревог, у тревоги ссылка «на карте» открывает карту | **PASS** | {"rows":5,"link":true,"toMap":true} | 1366-ru-W2-8-pulse.jpg |
| W2-5 | 1366-kk | «Картина дня»: блок «Әкімнің шешімі керек» виден; демо помечено «пример» | **PASS** | {"day":true,"block":true,"demoMark":true} | 1366-kk-W2-5-decisions.jpg |
| W2-8 | 1366-kk | «Картина дня»: «Аудан пульсі» — 1–5 тревог, у тревоги ссылка «на карте» открывает карту | **PASS** | {"rows":5,"link":true,"toMap":true} | 1366-kk-W2-8-pulse.jpg |
| W2-5 | 375-ru | «Картина дня»: блок «Нужно решение акима» виден; демо помечено «пример» | **PASS** | {"day":true,"block":true,"demoMark":true} | 375-ru-W2-5-decisions.jpg |
| W2-8 | 375-ru | «Картина дня»: «Пульс района» — 1–5 тревог, у тревоги ссылка «на карте» открывает карту | **PASS** | {"rows":5,"link":true,"toMap":true} | 375-ru-W2-8-pulse.jpg |
| W2-5 | 375-kk | «Картина дня»: блок «Әкімнің шешімі керек» виден; демо помечено «пример» | **PASS** | {"day":true,"block":true,"demoMark":true} | 375-kk-W2-5-decisions.jpg |
| W2-8 | 375-kk | «Картина дня»: «Аудан пульсі» — 1–5 тревог, у тревоги ссылка «на карте» открывает карту | **PASS** | {"rows":5,"link":true,"toMap":true} | 375-kk-W2-8-pulse.jpg |
| M | сборка | Обязательные мелочи: серый «нет данных», список у карты, лёгкая карточка до 3D: есть в сборке — проверяю | **INFO** | {"static":{"emergency":["web/civic/feedback/categories_v2.js: emergency_phone","web/civic/feedback/complaint-strings.js: complaint.emergency","web/civic/feedback/complaint.js: emergency_phone","ui/civic_feedback/v2/categ |  |
| M-1 | 1366-ru | тепловая карта: серый «Нет свежих данных» у районов без жалоб | **NOT_RUN** | {"why":"в данных демо нет района без жалоб за 7 дней — серому нечего показать","districts":6,"states":["active"]} |  |
| M-4 | 1366-ru | рядом с картой — список мест («Горячие места»); нажатие по строке открывает карточку | **PASS** | {"items":10,"card":true} | 1366-ru-M-4-list.jpg |
| M-5 | 1366-ru | лёгкая карточка раньше 3D (правило 5): на главной без слоя «Проекты» и 3D библиотека 3D не загружается | **PASS** | {"three":[]} |  |
| M-1 | 1366-kk | тепловая карта: серый «Нет свежих данных» у районов без жалоб | **NOT_RUN** | {"why":"в данных демо нет района без жалоб за 7 дней — серому нечего показать","districts":6,"states":["active"]} |  |
| M-4 | 1366-kk | рядом с картой — список мест («Горячие места»); нажатие по строке открывает карточку | **PASS** | {"items":10,"card":true} | 1366-kk-M-4-list.jpg |
| M-5 | 1366-kk | лёгкая карточка раньше 3D (правило 5): на главной без слоя «Проекты» и 3D библиотека 3D не загружается | **PASS** | {"three":[]} |  |
| M-1 | 375-ru | тепловая карта: серый «Нет свежих данных» у районов без жалоб | **NOT_RUN** | {"why":"в данных демо нет района без жалоб за 7 дней — серому нечего показать","districts":6,"states":["active"]} |  |
| M-4 | 375-ru | рядом с картой — список мест («Горячие места»); нажатие по строке открывает карточку | **PASS** | {"items":10,"card":true} | 375-ru-M-4-list.jpg |
| M-5 | 375-ru | лёгкая карточка раньше 3D (правило 5): на главной без слоя «Проекты» и 3D библиотека 3D не загружается | **PASS** | {"three":[]} |  |
| M-1 | 375-kk | тепловая карта: серый «Нет свежих данных» у районов без жалоб | **NOT_RUN** | {"why":"в данных демо нет района без жалоб за 7 дней — серому нечего показать","districts":6,"states":["active"]} |  |
| M-4 | 375-kk | рядом с картой — список мест («Горячие места»); нажатие по строке открывает карточку | **PASS** | {"items":10,"card":true} | 375-kk-M-4-list.jpg |
| M-5 | 375-kk | лёгкая карточка раньше 3D (правило 5): на главной без слоя «Проекты» и 3D библиотека 3D не загружается | **PASS** | {"three":[]} |  |
