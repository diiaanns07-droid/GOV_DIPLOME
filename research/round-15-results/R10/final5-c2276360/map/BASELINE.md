# R10 · эталон карты · c2276360

```
{"root":"/tmp/claude-0/-home-user-GOV-DIPLOME/62d68526-d416-54f0-b206-35e3353bc4a5/scratchpad/builds/r01-final5","sha":"c2276360","when":"2026-10-16T08:57:56.309Z","base":"(свой сервер, временная база, CIVIC_DEMO=1)","repeat":3,"sizes":["1366x768","375x812"],"langs":["ru","kk"],"modes":["resident","akimat"],"chromium":"141.0.7390.37","machine":{"cpu":"Intel(R) Xeon(R) Processor @ 2.10GHz","cores":4,"mem_gb":16,"platform":"linux 6.18.44-fc-v139","node":"v22.22.0"}}
```

Загрузка, медиана из 3 окон без кэша, секунды от начала навигации (WebGL программный — сравнивать с прогоном на той же машине):

| Вариант | DOM готов | load | карта загружена | 1-й значок с числом | главная кнопка | карта успокоилась | запросов | КБ | длинные задачи, мс |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 1366x768-ru-resident | 0.32 | 0.37 | 3.58 | 1.73 | 1.73 | 3.41 | 131 | 10199 | 2664 |
| 1366x768-ru-akimat | 0.31 | 0.33 | 3.21 | 1.62 | — | 3.41 | 130 | 10240 | 2730 |
| 1366x768-kk-resident | 0.29 | 0.34 | 3.45 | 1.65 | 1.65 | 3.24 | 132 | 10400 | 2550 |
| 1366x768-kk-akimat | 0.30 | 0.34 | 3.62 | 1.76 | — | 3.41 | 131 | 10441 | 2768 |
| 375x812-ru-resident | 0.30 | 0.33 | 2.54 | 1.38 | 1.36 | 4.09 | 131 | 10659 | 1693 |
| 375x812-ru-akimat | 0.31 | 0.34 | 2.58 | 1.43 | 1.43 | 4.15 | 130 | 10473 | 1663 |
| 375x812-kk-resident | 0.31 | 0.36 | 2.53 | 1.43 | 1.43 | 4.25 | 132 | 10860 | 1840 |
| 375x812-kk-akimat | 0.30 | 0.33 | 2.68 | 1.58 | 1.48 | 4.10 | 131 | 10674 | 1695 |

Вид по умолчанию (первое окно):

| Вариант | слоёв видно / всего | значков (с числом) | 3D-табличек | кнопок вне карты | меню | масштаб | кадр |
|---|---|---|---|---|---|---|---|
| 1366x768-ru-resident | 37 / 48 | 6 (6) | 0 | 24 | 3: Акимат · Житель · Для сотрудников | z10.37 | default-1366x768-ru-resident.png |
| 1366x768-ru-akimat | 37 / 48 | 6 (6) | 0 | 27 | 3: Акимат · Житель · Для сотрудников | z10.37 | default-1366x768-ru-akimat.png |
| 1366x768-kk-resident | 37 / 48 | 6 (6) | 0 | 24 | 3: Әкімдік · Тұрғын · Қызметкерлерге | z10.37 | default-1366x768-kk-resident.png |
| 1366x768-kk-akimat | 37 / 48 | 6 (6) | 0 | 27 | 3: Әкімдік · Тұрғын · Қызметкерлерге | z10.37 | default-1366x768-kk-akimat.png |
| 375x812-ru-resident | 37 / 48 | 3 (3) | 0 | 17 | 10: Уведомления · Карта · Мои обращения · Мой двор · Идеи · Сделаем вместе · Вопросы и встречи · Акимат · Житель · Для сотру | z9 | default-375x812-ru-resident.png |
| 375x812-ru-akimat | 37 / 48 | 2 (2) | 0 | 22 | 13: Карта · Картина дня · Обращения · Ведомства · Проекты и идеи · Сделаем вместе · Вопросы и встречи · Спросить Birge · Сит | z9 | default-375x812-ru-akimat.png |
| 375x812-kk-resident | 37 / 48 | 3 (3) | 0 | 17 | 10: Хабарламалар · Карта · Менің өтініштерім · Аулам · Идеялар · Бірге жасайық · Сұрақтар мен кездесулер · Әкімдік · Тұрғын  | z9 | default-375x812-kk-resident.png |
| 375x812-kk-akimat | 37 / 48 | 2 (2) | 0 | 22 | 13: Карта · Күн қорытындысы · Өтініштер · Ведомстволар · Жобалар мен идеялар · Бірге жасайық · Сұрақтар мен кездесулер · Bir | z9 | default-375x812-kk-akimat.png |

Плавность (кадр/с · p95 мс · кадров > 50 мс) и отклик интерфейса, мс:

| Вариант | сдвиг | полёт 12→15 | отклик |
|---|---|---|---|
| 1366x768-ru-resident | 3 · 333 · 10 | 4 · 300 · 12 | complaint_form: 23, mine: 5, to_akimat: 383, lang_switch: 324 |
| 1366x768-ru-akimat | 4 · 267 · 11 | 4 · 283 · 12 | hot_select: —, day_kpi: 67, lang_switch: 398 |
| 1366x768-kk-resident | 3 · 367 · 9 | 4 · 333 · 12 | complaint_form: 26, mine: 5, to_akimat: 325, lang_switch: 133 |
| 1366x768-kk-akimat | 4 · 283 · 10 | 3 · 367 · 10 | hot_select: —, day_kpi: 83, lang_switch: 173 |
| 375x812-ru-resident | 10 · 117 · 23 | 11 · 150 · 22 | complaint_form: 21, mine: 8, to_akimat: 95, lang_switch: 259 |
| 375x812-ru-akimat | 15 · 83 · 29 | 12 · 133 · 22 | hot_select: 600, day_kpi: 154, lang_switch: 213 |
| 375x812-kk-resident | 10 · 117 · 25 | 11 · 150 · 22 | complaint_form: 24, mine: 10, to_akimat: 88, lang_switch: 91 |
| 375x812-kk-akimat | 10 · 133 · 22 | 10 · 167 · 23 | hot_select: 592, day_kpi: 155, lang_switch: 99 |

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
| GET /api/civic/v2/modules | 16 | 3 | 14 | 200 |
| GET /api/civic/v2/heat z12 | 11 | 10 | 171 | 200 |
| GET /api/civic/v2/heat z16 | 36 | 3 | 19 | 200 |
| GET /api/civic/v2/akim/summary | 32 | 31 | 34 | 200 |
| POST /api/civic/v2/classify | 8 | 3 | 0 | 200 |
| POST /api/civic/v2/similar | 4 | 3 | 0 | 200 |
| GET /api/civic/v2/targets | 3 | 2 | 0 | 200 |
| GET /api/civic/v2/proposals | 4 | 4 | 5 | 200 |

Видимые слои стиля по умолчанию (первый вариант каждого вида):

- 1366x768-ru-resident: offline-bg (0), offline-nura-minor (0), offline-nura-street-case (0), offline-nura-street (0), offline-city-major-case (1244), offline-city-major (1244), civic-explore-lines (18), civic-explore-selected (0), civic-r03-approx-fill (6), civic-r03-approx-line (6), civic-r03-area-fill (0), civic-r03-area-line (0), civic-r03-area-line-approx (0), civic-r03-line-casing (1), civic-r03-line (1), civic-r03-line-approx (0), civic-r03-line-core (0), civic-r03-synthetic-outline (1), civic-r03-selected-line (0), civic-r03-point-halo (3), r07-district-fill (18), r07-district-line (18), r07-area-glow (0), r07-area-fill (0), r07-area-line (0), r07-area-approx (0), r07-sel-outline (0), r07-sel-line (0), r07-seg-casing (0), r07-seg (0), r07-seg-dashed (0), r07-obj-halo-lo (0), r07-obj-halo (0), r07-obj-dot (0), civic-r03-point-synthetic (3), civic-r03-point (3), civic-r03-selected-point (0)
- 1366x768-ru-akimat: offline-bg (0), offline-nura-minor (0), offline-nura-street-case (0), offline-nura-street (0), offline-city-major-case (1236), offline-city-major (1236), civic-explore-lines (16), civic-explore-selected (0), civic-r03-approx-fill (6), civic-r03-approx-line (6), civic-r03-area-fill (0), civic-r03-area-line (0), civic-r03-area-line-approx (0), civic-r03-line-casing (1), civic-r03-line (1), civic-r03-line-approx (0), civic-r03-line-core (0), civic-r03-synthetic-outline (1), civic-r03-selected-line (0), civic-r03-point-halo (3), r07-district-fill (16), r07-district-line (16), r07-area-glow (0), r07-area-fill (0), r07-area-line (0), r07-area-approx (0), r07-sel-outline (0), r07-sel-line (0), r07-seg-casing (0), r07-seg (0), r07-seg-dashed (0), r07-obj-halo-lo (0), r07-obj-halo (0), r07-obj-dot (0), civic-r03-point-synthetic (3), civic-r03-point (3), civic-r03-selected-point (0)
