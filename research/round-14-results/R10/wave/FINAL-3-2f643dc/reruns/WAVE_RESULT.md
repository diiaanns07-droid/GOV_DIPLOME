# R10 · новые пункты волн 1–2 · 2f643dc7

```
{"root":"/home/user/bf3c","sha":"2f643dc7","when":"2026-10-12T10:39:41.877Z","sizes":["1366x768","375x812"],"langs":["ru","kk"],"node":"v22.22.0","runtime":{"BirgeNearby":true,"BirgeIdeas":true,"BirgeProjects":false,"BirgeComplaintList":true,"BirgeAsk":true,"BirgeQuestions":false,"BirgeShell":true}}
```

Итого: PASS 17, FAIL 0, ЖДЁТ 0, NOT_RUN 1

| Пункт | Что | Владелец | Готово, когда | Состояние |
|---|---|---|---|---|
| W2-7 | Идеи → голосование → проект в 3D | R06 + R05 | Путь «идея → голоса → проект в 3D» или «отказ с причиной и доработка» | **частично** |
| W2-9 | «Вопрос акиму» | R13 | вопросы, голоса и «Ответ акима» | **PASS** |

| Пункт | Где | Проверка | Итог | Подробно | Кадр |
|---|---|---|---|---|---|
| W2-7 | сборка | Идеи → голосование → проект в 3D: есть в сборке — проверяю | **INFO** | {"static":{"emergency":["web/civic/feedback/categories_v2.js: emergency_phone","web/civic/feedback/complaint-strings.js: complaint.emergency","web/civic/feedback/complaint.js: emergency_phone","ui/civic_feedback/v2/categ |  |
| W2-7 | 1366-ru | меню «Идеи» → «Идеи жителей»: «Это опрос для выбора концепции, решение принимает акимат.» видно сразу, одна главная «Предложить идею», 3 вкладки | **PASS** | {"opened":true,"honest":true,"primary":["Предложить идею"],"tabs":[true,true,true]} | 1366-ru-W2-7-ideas.jpg |
| W2-7 | 1366-ru | «Поддержать» → «Вы поддержали», голосов +1; после перезагрузки не удваивается | **PASS** | {"support":true,"done":true,"before":47,"after":48,"again":48} |  |
| W2-7 | 1366-ru | отказ: «Причина отказа: {text}» и «Можно доработать: {text}»; проект: «По идее жителей · {n} голосов»; 3D само не открывается | **PASS** | {"reason":true,"improve":true,"byRes":true,"auto3d":0} | 1366-ru-W2-7-paths.jpg |
| W2-7 | 1366-kk | меню «Идеялар» → «Тұрғындар идеялары»: «Бұл тұжырымдаманы таңдауға арналған сауалнама, шешімді әкімдік қабылдайды.» видно сразу, одна главная «Идея ұсыну», 3 вкладки | **PASS** | {"opened":true,"honest":true,"primary":["Идея ұсыну"],"tabs":[true,true,true]} | 1366-kk-W2-7-ideas.jpg |
| W2-7 | 1366-kk | «Қолдау» → «Сіз қолдадыңыз», голосов +1; после перезагрузки не удваивается | **PASS** | {"support":true,"done":true,"before":48,"after":49,"again":49} |  |
| W2-7 | 1366-kk | отказ: «Бас тарту себебі: {text}» и «Жетілдіруге болады: {text}»; проект: «Тұрғындар идеясы бойынша · {n} дауыс»; 3D само не открывается | **PASS** | {"reason":true,"improve":true,"byRes":true,"auto3d":0} | 1366-kk-W2-7-paths.jpg |
| W2-7 | 375-ru | меню «Идеи» → «Идеи жителей»: «Это опрос для выбора концепции, решение принимает акимат.» видно сразу, одна главная «Предложить идею», 3 вкладки | **PASS** | {"opened":true,"honest":true,"primary":["Предложить идею"],"tabs":[true,true,true]} | 375-ru-W2-7-ideas.jpg |
| W2-7 | 375-ru | «Поддержать» → «Вы поддержали», голосов +1; после перезагрузки не удваивается | **PASS** | {"support":true,"done":true,"before":49,"after":50,"again":50} |  |
| W2-7 | 375-ru | отказ: «Причина отказа: {text}» и «Можно доработать: {text}»; проект: «По идее жителей · {n} голосов»; 3D само не открывается | **PASS** | {"reason":true,"improve":true,"byRes":true,"auto3d":0} | 375-ru-W2-7-paths.jpg |
| W2-7 | 375-kk | меню «Идеялар» → «Тұрғындар идеялары»: «Бұл тұжырымдаманы таңдауға арналған сауалнама, шешімді әкімдік қабылдайды.» видно сразу, одна главная «Идея ұсыну», 3 вкладки | **PASS** | {"opened":true,"honest":true,"primary":["Идея ұсыну"],"tabs":[true,true,true]} | 375-kk-W2-7-ideas.jpg |
| W2-7 | 375-kk | «Қолдау» → «Сіз қолдадыңыз», голосов +1; после перезагрузки не удваивается | **PASS** | {"support":true,"done":true,"before":50,"after":51,"again":51} |  |
| W2-7 | 375-kk | отказ: «Бас тарту себебі: {text}» и «Жетілдіруге болады: {text}»; проект: «Тұрғындар идеясы бойынша · {n} дауыс»; 3D само не открывается | **PASS** | {"reason":true,"improve":true,"byRes":true,"auto3d":0} | 375-kk-W2-7-paths.jpg |
| W2-7 | 1366-ru | акимат «Проекты и идеи»: проверка реализуемости (участок, сети, доступность, содержание), «Сделать проектом», «Отклонить с причиной» | **PASS** | {"logged":true,"opened":true,"checkOpen":true,"checks":[true,true,true,true],"make":true,"reject":true} | 1366-ru-W2-7-akimat.jpg |
| W2-7 | путь | новая идея за 3 шага (место → название и описание → объект 3D) и превращение в проект в 3D | **NOT_RUN** | "дописать при поставке R06/R05 (вход сотрудника, API идей)" |  |
| W2-9 | сборка | «Вопрос акиму»: есть в сборке — проверяю | **INFO** | {"static":{"emergency":["web/civic/feedback/categories_v2.js: emergency_phone","web/civic/feedback/complaint-strings.js: complaint.emergency","web/civic/feedback/complaint.js: emergency_phone","ui/civic_feedback/v2/categ |  |
| W2-9 | 1366-ru | «Вопрос акиму»: вопросы жителей с голосами, во вкладке «С ответом» — «Ответ акима» хотя бы у 2, демо помечено | **PASS** | {"votes":7,"tab":true,"answers":2,"demo":true} | 1366-ru-W2-9-ask.jpg |
| W2-9 | 1366-kk | «Вопрос акиму»: вопросы жителей с голосами, во вкладке «С ответом» — «Ответ акима» хотя бы у 2, демо помечено | **PASS** | {"votes":7,"tab":true,"answers":2,"demo":true} | 1366-kk-W2-9-ask.jpg |
| W2-9 | 375-ru | «Вопрос акиму»: вопросы жителей с голосами, во вкладке «С ответом» — «Ответ акима» хотя бы у 2, демо помечено | **PASS** | {"votes":7,"tab":true,"answers":2,"demo":true} | 375-ru-W2-9-ask.jpg |
| W2-9 | 375-kk | «Вопрос акиму»: вопросы жителей с голосами, во вкладке «С ответом» — «Ответ акима» хотя бы у 2, демо помечено | **PASS** | {"votes":7,"tab":true,"answers":2,"demo":true} | 375-kk-W2-9-ask.jpg |
