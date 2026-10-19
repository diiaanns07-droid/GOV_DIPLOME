# R10 · эталон карты · 745eeae5

```
{"root":"/tmp/claude-0/-home-user-GOV-DIPLOME/62d68526-d416-54f0-b206-35e3353bc4a5/scratchpad/builds/r01-b6-745eeae5","sha":"745eeae5","when":"2026-10-16T23:50:12.368Z","base":"(свой сервер, временная база, CIVIC_DEMO=1)","repeat":3,"sizes":["1366x768","375x812"],"langs":["ru","kk"],"modes":["resident","akimat"],"chromium":"141.0.7390.37","machine":{"cpu":"Intel(R) Xeon(R) Processor @ 2.10GHz","cores":4,"mem_gb":16,"platform":"linux 6.18.44-fc-v139","node":"v22.22.0"}}
```

Загрузка, медиана из 3 окон без кэша, секунды от начала навигации (WebGL программный — сравнивать с прогоном на той же машине):

| Вариант | DOM готов | load | карта загружена | 1-й значок с числом | главная кнопка | карта успокоилась | запросов | КБ | длинные задачи, мс |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 1366x768-ru-resident | 0.27 | 0.32 | 2.20 | 1.46 | 1.46 | 3.76 | 134 | 10593 | 1376 |
| 1366x768-ru-akimat | 0.29 | 0.31 | 2.39 | 1.51 | — | 3.96 | 133 | 10634 | 1529 |
| 1366x768-kk-resident | 0.28 | 0.30 | 2.22 | 1.46 | 1.46 | 3.81 | 135 | 10799 | 1416 |
| 1366x768-kk-akimat | 0.26 | 0.32 | 2.13 | 1.56 | — | 3.68 | 134 | 10841 | 1285 |
| 375x812-ru-resident | 0.29 | 0.32 | 1.84 | 1.36 | 1.36 | 3.39 | 133 | 10777 | 990 |
| 375x812-ru-akimat | 0.27 | 0.30 | 1.88 | 1.38 | 1.20 | 3.43 | 132 | 10592 | 987 |
| 375x812-kk-resident | 0.26 | 0.29 | 1.84 | 1.34 | 1.34 | 3.39 | 134 | 10984 | 964 |
| 375x812-kk-akimat | 0.27 | 0.30 | 1.97 | 1.53 | 1.33 | 3.51 | 133 | 10798 | 1026 |

Вид по умолчанию (первое окно):

| Вариант | слоёв видно / всего | значков (с числом) | 3D-табличек | кнопок вне карты | меню | масштаб | кадр |
|---|---|---|---|---|---|---|---|
| 1366x768-ru-resident | 40 / 51 | 6 (6) | 0 | 24 | 3: Акимат · Житель · Для сотрудников | z10.37 | default-1366x768-ru-resident.png |
| 1366x768-ru-akimat | 40 / 51 | 6 (6) | 0 | 27 | 3: Акимат · Житель · Для сотрудников | z10.37 | default-1366x768-ru-akimat.png |
| 1366x768-kk-resident | 40 / 51 | 6 (6) | 0 | 24 | 3: Әкімдік · Тұрғын · Қызметкерлерге | z10.37 | default-1366x768-kk-resident.png |
| 1366x768-kk-akimat | 40 / 51 | 6 (6) | 0 | 27 | 3: Әкімдік · Тұрғын · Қызметкерлерге | z10.37 | default-1366x768-kk-akimat.png |
| 375x812-ru-resident | 40 / 51 | 3 (3) | 0 | 17 | 10: Уведомления · Карта · Мои обращения · Мой двор · Идеи · Сделаем вместе · Вопросы и встречи · Акимат · Житель · Для сотру | z9 | default-375x812-ru-resident.png |
| 375x812-ru-akimat | 40 / 51 | 2 (2) | 0 | 22 | 14: Карта · Картина дня · Обращения · Ведомства · Проекты и идеи · Сделаем вместе · Вопросы и встречи · Разбор обращений · С | z9 | default-375x812-ru-akimat.png |
| 375x812-kk-resident | 40 / 51 | 3 (3) | 0 | 17 | 10: Хабарламалар · Карта · Менің өтініштерім · Аулам · Идеялар · Бірге жасайық · Сұрақтар мен кездесулер · Әкімдік · Тұрғын  | z9 | default-375x812-kk-resident.png |
| 375x812-kk-akimat | 40 / 51 | 2 (2) | 0 | 22 | 14: Карта · Күн қорытындысы · Өтініштер · Ведомстволар · Жобалар мен идеялар · Бірге жасайық · Сұрақтар мен кездесулер · Өті | z9 | default-375x812-kk-akimat.png |

Плавность (кадр/с · p95 мс · кадров > 50 мс) и отклик интерфейса, мс:

| Вариант | сдвиг | полёт 12→15 | отклик |
|---|---|---|---|
| 1366x768-ru-resident | 3 · 333 · 9 | 4 · 300 · 11 | complaint_form: 18, mine: 8, to_akimat: 305, lang_switch: 370 |
| 1366x768-ru-akimat | 4 · 283 · 10 | 4 · 317 · 11 | hot_select: —, day_kpi: 106, lang_switch: 335 |
| 1366x768-kk-resident | 3 · 317 · 8 | 4 · 300 · 11 | complaint_form: 19, mine: 6, to_akimat: 349, lang_switch: 150 |
| 1366x768-kk-akimat | 3 · 283 · 10 | 4 · 317 · 12 | hot_select: —, day_kpi: 92, lang_switch: 172 |
| 375x812-ru-resident | 10 · 117 · 24 | 12 · 150 · 23 | complaint_form: 21, mine: 8, to_akimat: 130, lang_switch: 223 |
| 375x812-ru-akimat | 12 · 100 · 30 | 12 · 150 · 22 | hot_select: 637, day_kpi: 154, lang_switch: 224 |
| 375x812-kk-resident | 11 · 117 · 23 | 12 · 133 · 19 | complaint_form: 19, mine: 10, to_akimat: 126, lang_switch: 101 |
| 375x812-kk-akimat | 13 · 100 · 28 | 12 · 133 · 21 | hot_select: 656, day_kpi: 155, lang_switch: 137 |

Карточка места «Хан Шатыр» (правила 3–4 POLISH_WAVE_2):

| Вариант | заголовок | видно, px | содержимое, px | кнопок | главных | главная без прокрутки | «Подробнее» | кадр |
|---|---|---:|---:|---:|---:|---|---:|---|
| 1366x768-ru-resident | Остановка «Хан Шатыр» | 385 | 385 | 4 | 1 (Я тоже) | true | 0 | card-1366x768-ru-resident.jpg |
| 1366x768-ru-akimat | Остановка «Хан Шатыр» | 600 | 532 | 7 | 1 (Отметить исправленным) | true | 0 | card-1366x768-ru-akimat.jpg |
| 1366x768-kk-resident | «Хан Шатыр» аялдамасы | 385 | 385 | 4 | 1 (Мен де) | true | 0 | card-1366x768-kk-resident.jpg |
| 1366x768-kk-akimat | «Хан Шатыр» аялдамасы | 600 | 532 | 7 | 1 (Түзетілді деп белгілеу) | true | 0 | card-1366x768-kk-akimat.jpg |
| 375x812-ru-resident | Остановка «Хан Шатыр» | 417 | 416 | 4 | 1 (Я тоже) | true | 0 | card-375x812-ru-resident.jpg |
| 375x812-ru-akimat | Остановка «Хан Шатыр» | 417 | 563 | 7 | 1 (Отметить исправленным) | true | 0 | card-375x812-ru-akimat.jpg |
| 375x812-kk-resident | «Хан Шатыр» аялдамасы | 417 | 407 | 4 | 1 (Мен де) | true | 0 | card-375x812-kk-resident.jpg |
| 375x812-kk-akimat | «Хан Шатыр» аялдамасы | 417 | 554 | 7 | 1 (Түзетілді деп белгілеу) | true | 0 | card-375x812-kk-akimat.jpg |

API (6 запросов: первый и медиана остальных):

| Запрос | первый, мс | медиана, мс | КБ | статус |
|---|---:|---:|---:|---|
| GET /api/civic/v2/modules | 13 | 3 | 14 | 200 |
| GET /api/civic/v2/heat z12 | 9 | 10 | 171 | 200 |
| GET /api/civic/v2/heat z16 | 35 | 3 | 19 | 200 |
| GET /api/civic/v2/akim/summary | 35 | 34 | 34 | 200 |
| POST /api/civic/v2/classify | 6 | 2 | 0 | 200 |
| POST /api/civic/v2/similar | 3 | 3 | 0 | 200 |
| GET /api/civic/v2/targets | 2 | 2 | 0 | 200 |
| GET /api/civic/v2/proposals | 3 | 3 | 5 | 200 |

Видимые слои стиля по умолчанию (первый вариант каждого вида):

- 1366x768-ru-resident: offline-bg (0), offline-nura-minor (0), offline-nura-street-case (0), offline-nura-street (0), offline-city-major-case (1244), offline-city-major (1244), civic-explore-lines (18), civic-explore-selected (0), civic-r03-approx-fill (0), civic-r03-approx-line (0), civic-r03-area-fill (0), civic-r03-area-line (0), civic-r03-area-line-approx (0), civic-r03-line-casing (0), civic-r03-line (0), civic-r03-line-approx (0), civic-r03-line-core (0), civic-r03-synthetic-outline (0), civic-r03-selected-line (0), civic-r03-point-halo (0), r07-district-fill (18), r07-district-line (18), r07-area-glow (0), r07-area-fill (0), r07-area-line (0), r07-area-approx (0), r07-sel-outline (0), r07-sel-line (0), r07-seg-casing (0), r07-seg (0), r07-seg-dashed (0), r07-obj-halo-lo (0), r07-obj-halo (0), r07-obj-dot (0), r07-place-line (0), r07-place-approx (0), r07-place-ring (0), civic-r03-point-synthetic (0), civic-r03-point (0), civic-r03-selected-point (0)
- 1366x768-ru-akimat: offline-bg (0), offline-nura-minor (0), offline-nura-street-case (0), offline-nura-street (0), offline-city-major-case (1236), offline-city-major (1236), civic-explore-lines (16), civic-explore-selected (0), civic-r03-approx-fill (0), civic-r03-approx-line (0), civic-r03-area-fill (0), civic-r03-area-line (0), civic-r03-area-line-approx (0), civic-r03-line-casing (0), civic-r03-line (0), civic-r03-line-approx (0), civic-r03-line-core (0), civic-r03-synthetic-outline (0), civic-r03-selected-line (0), civic-r03-point-halo (0), r07-district-fill (16), r07-district-line (16), r07-area-glow (0), r07-area-fill (0), r07-area-line (0), r07-area-approx (0), r07-sel-outline (0), r07-sel-line (0), r07-seg-casing (0), r07-seg (0), r07-seg-dashed (0), r07-obj-halo-lo (0), r07-obj-halo (0), r07-obj-dot (0), r07-place-line (0), r07-place-approx (0), r07-place-ring (0), civic-r03-point-synthetic (0), civic-r03-point (0), civic-r03-selected-point (0)
