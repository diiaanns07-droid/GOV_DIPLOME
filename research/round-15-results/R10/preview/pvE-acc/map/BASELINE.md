# R10 · эталон карты · c9069723

```
{"root":"/tmp/claude-0/-home-user-GOV-DIPLOME/62d68526-d416-54f0-b206-35e3353bc4a5/scratchpad/builds/pvE","sha":"c9069723","when":"2026-10-15T16:56:58.648Z","base":"(свой сервер, временная база, CIVIC_DEMO=1)","repeat":3,"sizes":["1366x768","375x812"],"langs":["ru","kk"],"modes":["resident","akimat"],"chromium":"141.0.7390.37","machine":{"cpu":"Intel(R) Xeon(R) Processor @ 2.80GHz","cores":4,"mem_gb":16,"platform":"linux 6.18.44-fc-v114","node":"v22.22.0"}}
```

Загрузка, медиана из 3 окон без кэша, секунды от начала навигации (WebGL программный — сравнивать с прогоном на той же машине):

| Вариант | DOM готов | load | карта загружена | 1-й значок с числом | главная кнопка | карта успокоилась | запросов | КБ | длинные задачи, мс |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 1366x768-ru-resident | 0.39 | 0.44 | 5.57 | 2.40 | 2.40 | 5.36 | 123 | 9935 | 4897 |
| 1366x768-ru-akimat | 0.41 | 0.47 | 5.85 | 2.59 | — | 5.42 | 124 | 9975 | 4883 |
| 1366x768-kk-resident | 0.53 | 0.57 | 6.05 | 2.69 | 2.69 | 5.61 | 124 | 10104 | 4934 |
| 1366x768-kk-akimat | 0.38 | 0.43 | 5.27 | 2.31 | — | 5.22 | 125 | 10144 | 4538 |
| 375x812-ru-resident | 0.45 | 0.48 | 4.00 | 2.04 | 2.04 | 5.24 | 125 | 10396 | 3016 |
| 375x812-ru-akimat | 0.38 | 0.45 | 3.62 | 2.09 | 2.09 | 4.08 | 123 | 9935 | 2569 |
| 375x812-kk-resident | 0.37 | 0.45 | 3.59 | 2.02 | 2.02 | 5.35 | 126 | 10565 | 2626 |
| 375x812-kk-akimat | 0.41 | 0.43 | 4.11 | 2.13 | 2.13 | 3.97 | 124 | 10104 | 2955 |

Вид по умолчанию (первое окно):

| Вариант | слоёв видно / всего | значков (с числом) | 3D-табличек | кнопок вне карты | меню | масштаб | кадр |
|---|---|---|---|---|---|---|---|
| 1366x768-ru-resident | 37 / 48 | 6 (6) | 0 | 22 | 3: Акимат · Житель · Для сотрудников | z10.37 | default-1366x768-ru-resident.png |
| 1366x768-ru-akimat | 37 / 48 | 6 (6) | 0 | 26 | 3: Акимат · Житель · Для сотрудников | z10.37 | default-1366x768-ru-akimat.png |
| 1366x768-kk-resident | 37 / 48 | 6 (6) | 0 | 22 | 3: Әкімдік · Тұрғын · Қызметкерлерге | z10.37 | default-1366x768-kk-resident.png |
| 1366x768-kk-akimat | 37 / 48 | 6 (6) | 0 | 26 | 3: Әкімдік · Тұрғын · Қызметкерлерге | z10.37 | default-1366x768-kk-akimat.png |
| 375x812-ru-resident | 37 / 48 | 3 (3) | 0 | 15 | 9: Карта · Мои обращения · Мой двор · Идеи · Сделаем вместе · Вопросы и встречи · Акимат · Житель · Для сотрудников | z9 | default-375x812-ru-resident.png |
| 375x812-ru-akimat | 37 / 48 | 2 (2) | 0 | 20 | 13: Карта · Картина дня · Обращения · Ведомства · Проекты и идеи · Сделаем вместе · Вопросы и встречи · Спросить Birge · Сит | z9 | default-375x812-ru-akimat.png |
| 375x812-kk-resident | 37 / 48 | 3 (3) | 0 | 16 | 9: Карта · Менің өтініштерім · Менің аулам · Идеялар · Бірге жасайық · Сұрақтар мен кездесулер · Әкімдік · Тұрғын · Қызметк | z9 | default-375x812-kk-resident.png |
| 375x812-kk-akimat | 37 / 48 | 2 (2) | 0 | 21 | 13: Карта · Күн қорытындысы · Өтініштер · Ведомстволар · Жобалар мен идеялар · Бірге жасайық · Сұрақтар мен кездесулер · Bir | z9 | default-375x812-kk-akimat.png |

Плавность (кадр/с · p95 мс · кадров > 50 мс) и отклик интерфейса, мс:

| Вариант | сдвиг | полёт 12→15 | отклик |
|---|---|---|---|
| 1366x768-ru-resident | 1 · 950 · 4 | 1 · 617 · 6 | complaint_form: 49, mine: 13, to_akimat: 632, lang_switch: 573 |
| 1366x768-ru-akimat | 2 · 683 · 5 | 1 · 600 · 5 | hot_select: —, day_kpi: 152, lang_switch: 550 |
| 1366x768-kk-resident | 1 · 950 · 6 | 2 · 533 · 7 | complaint_form: 34, mine: 11, to_akimat: 620, lang_switch: 418 |
| 1366x768-kk-akimat | 2 · 767 · 6 | 2 · 567 · 6 | hot_select: —, day_kpi: 135, lang_switch: 328 |
| 375x812-ru-resident | 7 · 200 · 15 | 7 · 267 · 18 | complaint_form: 27, mine: 14, to_akimat: 163, lang_switch: 384 |
| 375x812-ru-akimat | 7 · 167 · 18 | 7 · 233 · 17 | hot_select: 595, day_kpi: 155, lang_switch: 351 |
| 375x812-kk-resident | 5 · 267 · 13 | 6 · 250 · 16 | complaint_form: 33, mine: 12, to_akimat: 208, lang_switch: 163 |
| 375x812-kk-akimat | 7 · 183 · 15 | 6 · 250 · 17 | hot_select: 758, day_kpi: 156, lang_switch: 171 |

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
| GET /api/civic/v2/modules | 17 | 4 | 14 | 200 |
| GET /api/civic/v2/heat z12 | 18 | 18 | 171 | 200 |
| GET /api/civic/v2/heat z16 | 61 | 3 | 19 | 200 |
| GET /api/civic/v2/akim/summary | 20 | 18 | 32 | 200 |
| POST /api/civic/v2/classify | 11 | 3 | 0 | 200 |
| POST /api/civic/v2/similar | 7 | 4 | 0 | 200 |
| GET /api/civic/v2/targets | 3 | 2 | 0 | 200 |
| GET /api/civic/v2/proposals | 4 | 6 | 3 | 200 |

Видимые слои стиля по умолчанию (первый вариант каждого вида):

- 1366x768-ru-resident: offline-bg (0), offline-nura-minor (0), offline-nura-street-case (0), offline-nura-street (0), offline-city-major-case (1244), offline-city-major (1244), civic-explore-lines (18), civic-explore-selected (0), civic-r03-approx-fill (6), civic-r03-approx-line (6), civic-r03-area-fill (0), civic-r03-area-line (0), civic-r03-area-line-approx (0), civic-r03-line-casing (1), civic-r03-line (1), civic-r03-line-approx (0), civic-r03-line-core (0), civic-r03-synthetic-outline (1), civic-r03-selected-line (0), civic-r03-point-halo (3), r07-district-fill (18), r07-district-line (18), r07-area-glow (0), r07-area-fill (0), r07-area-line (0), r07-area-approx (0), r07-sel-outline (0), r07-sel-line (0), r07-seg-casing (0), r07-seg (0), r07-seg-dashed (0), r07-obj-halo-lo (0), r07-obj-halo (0), r07-obj-dot (0), civic-r03-point-synthetic (3), civic-r03-point (3), civic-r03-selected-point (0)
- 1366x768-ru-akimat: offline-bg (0), offline-nura-minor (0), offline-nura-street-case (0), offline-nura-street (0), offline-city-major-case (1236), offline-city-major (1236), civic-explore-lines (16), civic-explore-selected (0), civic-r03-approx-fill (6), civic-r03-approx-line (6), civic-r03-area-fill (0), civic-r03-area-line (0), civic-r03-area-line-approx (0), civic-r03-line-casing (1), civic-r03-line (1), civic-r03-line-approx (0), civic-r03-line-core (0), civic-r03-synthetic-outline (1), civic-r03-selected-line (0), civic-r03-point-halo (3), r07-district-fill (16), r07-district-line (16), r07-area-glow (0), r07-area-fill (0), r07-area-line (0), r07-area-approx (0), r07-sel-outline (0), r07-sel-line (0), r07-seg-casing (0), r07-seg (0), r07-seg-dashed (0), r07-obj-halo-lo (0), r07-obj-halo (0), r07-obj-dot (0), civic-r03-point-synthetic (3), civic-r03-point (3), civic-r03-selected-point (0)
