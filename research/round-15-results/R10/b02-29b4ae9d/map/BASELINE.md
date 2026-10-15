# R10 · эталон карты · 29b4ae9d

```
{"root":"/tmp/claude-0/-home-user-GOV-DIPLOME/62d68526-d416-54f0-b206-35e3353bc4a5/scratchpad/builds/r01-29b4","sha":"29b4ae9d","when":"2026-10-15T17:36:04.595Z","base":"(свой сервер, временная база, CIVIC_DEMO=1)","repeat":3,"sizes":["1366x768","375x812"],"langs":["ru","kk"],"modes":["resident","akimat"],"chromium":"141.0.7390.37","machine":{"cpu":"Intel(R) Xeon(R) Processor @ 2.80GHz","cores":4,"mem_gb":16,"platform":"linux 6.18.44-fc-v114","node":"v22.22.0"}}
```

Загрузка, медиана из 3 окон без кэша, секунды от начала навигации (WebGL программный — сравнивать с прогоном на той же машине):

| Вариант | DOM готов | load | карта загружена | 1-й значок с числом | главная кнопка | карта успокоилась | запросов | КБ | длинные задачи, мс |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 1366x768-ru-resident | 0.40 | 0.42 | 5.64 | 2.38 | 2.38 | 5.26 | 124 | 9879 | 4509 |
| 1366x768-ru-akimat | 0.43 | 0.48 | 5.84 | 2.71 | — | 5.65 | 125 | 9919 | 5064 |
| 1366x768-kk-resident | 0.44 | 0.49 | 5.53 | 2.48 | 2.49 | 5.13 | 125 | 10045 | 4491 |
| 1366x768-kk-akimat | 0.44 | 0.47 | 5.76 | 2.39 | — | 5.34 | 126 | 10085 | 4729 |
| 375x812-ru-resident | 0.41 | 0.48 | 4.25 | 2.30 | 2.30 | 4.09 | 125 | 10064 | 3105 |
| 375x812-ru-akimat | 0.41 | 0.45 | 4.22 | 2.17 | 2.18 | 4.09 | 124 | 9879 | 3113 |
| 375x812-kk-resident | 0.45 | 0.51 | 4.41 | 2.15 | 2.15 | 4.41 | 126 | 10231 | 3376 |
| 375x812-kk-akimat | 0.46 | 0.51 | 4.32 | 2.30 | 2.06 | 4.24 | 125 | 10045 | 3161 |

Вид по умолчанию (первое окно):

| Вариант | слоёв видно / всего | значков (с числом) | 3D-табличек | кнопок вне карты | меню | масштаб | кадр |
|---|---|---|---|---|---|---|---|
| 1366x768-ru-resident | 37 / 48 | 6 (6) | 0 | 23 | 3: Акимат · Житель · Для сотрудников | z10.37 | default-1366x768-ru-resident.png |
| 1366x768-ru-akimat | 37 / 48 | 6 (6) | 0 | 27 | 3: Акимат · Житель · Для сотрудников | z10.37 | default-1366x768-ru-akimat.png |
| 1366x768-kk-resident | 37 / 48 | 6 (6) | 0 | 23 | 3: Әкімдік · Тұрғын · Қызметкерлерге | z10.37 | default-1366x768-kk-resident.png |
| 1366x768-kk-akimat | 37 / 48 | 6 (6) | 0 | 27 | 3: Әкімдік · Тұрғын · Қызметкерлерге | z10.37 | default-1366x768-kk-akimat.png |
| 375x812-ru-resident | 37 / 48 | 3 (3) | 0 | 16 | 9: Карта · Мои обращения · Мой двор · Идеи · Сделаем вместе · Вопросы и встречи · Акимат · Житель · Для сотрудников | z9 | default-375x812-ru-resident.png |
| 375x812-ru-akimat | 37 / 48 | 2 (2) | 0 | 21 | 13: Карта · Картина дня · Обращения · Ведомства · Проекты и идеи · Сделаем вместе · Вопросы и встречи · Спросить Birge · Сит | z9 | default-375x812-ru-akimat.png |
| 375x812-kk-resident | 37 / 48 | 3 (3) | 0 | 16 | 9: Карта · Менің өтініштерім · Менің аулам · Идеялар · Бірге жасайық · Сұрақтар мен кездесулер · Әкімдік · Тұрғын · Қызметк | z9 | default-375x812-kk-resident.png |
| 375x812-kk-akimat | 37 / 48 | 2 (2) | 0 | 21 | 13: Карта · Күн қорытындысы · Өтініштер · Ведомстволар · Жобалар мен идеялар · Бірге жасайық · Сұрақтар мен кездесулер · Bir | z9 | default-375x812-kk-akimat.png |

Плавность (кадр/с · p95 мс · кадров > 50 мс) и отклик интерфейса, мс:

| Вариант | сдвиг | полёт 12→15 | отклик |
|---|---|---|---|
| 1366x768-ru-resident | 2 · 850 · 6 | 2 · 617 · 7 | complaint_form: 39, mine: 36, to_akimat: 711, lang_switch: 578 |
| 1366x768-ru-akimat | 2 · 833 · 5 | 1 · 700 · 6 | hot_select: —, day_kpi: 97, lang_switch: 825 |
| 1366x768-kk-resident | 1 · 817 · 3 | 1 · 683 · 6 | complaint_form: 30, mine: 9, to_akimat: 722, lang_switch: 313 |
| 1366x768-kk-akimat | 2 · 733 · 5 | 2 · 617 · 7 | hot_select: —, day_kpi: 144, lang_switch: 268 |
| 375x812-ru-resident | 5 · 250 · 12 | 6 · 267 · 15 | complaint_form: 45, mine: 14, to_akimat: 187, lang_switch: 415 |
| 375x812-ru-akimat | 6 · 183 · 16 | 6 · 250 · 16 | hot_select: 671, day_kpi: 156, lang_switch: 412 |
| 375x812-kk-resident | 5 · 217 · 12 | 5 · 300 · 14 | complaint_form: 35, mine: 11, to_akimat: 177, lang_switch: 178 |
| 375x812-kk-akimat | 6 · 183 · 17 | 6 · 300 · 16 | hot_select: 595, day_kpi: 156, lang_switch: 121 |

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
| GET /api/civic/v2/modules | 20 | 6 | 14 | 200 |
| GET /api/civic/v2/heat z12 | 90 | 20 | 171 | 200 |
| GET /api/civic/v2/heat z16 | 75 | 6 | 19 | 200 |
| GET /api/civic/v2/akim/summary | 1107 | 29 | 32 | 200 |
| POST /api/civic/v2/classify | 12 | 4 | 0 | 200 |
| POST /api/civic/v2/similar | 6 | 6 | 0 | 200 |
| GET /api/civic/v2/targets | 4 | 4 | 0 | 200 |
| GET /api/civic/v2/proposals | 6 | 8 | 3 | 200 |

Видимые слои стиля по умолчанию (первый вариант каждого вида):

- 1366x768-ru-resident: offline-bg (0), offline-nura-minor (0), offline-nura-street-case (0), offline-nura-street (0), offline-city-major-case (1244), offline-city-major (1244), civic-explore-lines (18), civic-explore-selected (0), civic-r03-approx-fill (6), civic-r03-approx-line (6), civic-r03-area-fill (0), civic-r03-area-line (0), civic-r03-area-line-approx (0), civic-r03-line-casing (1), civic-r03-line (1), civic-r03-line-approx (0), civic-r03-line-core (0), civic-r03-synthetic-outline (1), civic-r03-selected-line (0), civic-r03-point-halo (3), r07-district-fill (18), r07-district-line (18), r07-area-glow (0), r07-area-fill (0), r07-area-line (0), r07-area-approx (0), r07-sel-outline (0), r07-sel-line (0), r07-seg-casing (0), r07-seg (0), r07-seg-dashed (0), r07-obj-halo-lo (0), r07-obj-halo (0), r07-obj-dot (0), civic-r03-point-synthetic (3), civic-r03-point (3), civic-r03-selected-point (0)
- 1366x768-ru-akimat: offline-bg (0), offline-nura-minor (0), offline-nura-street-case (0), offline-nura-street (0), offline-city-major-case (1236), offline-city-major (1236), civic-explore-lines (16), civic-explore-selected (0), civic-r03-approx-fill (6), civic-r03-approx-line (6), civic-r03-area-fill (0), civic-r03-area-line (0), civic-r03-area-line-approx (0), civic-r03-line-casing (1), civic-r03-line (1), civic-r03-line-approx (0), civic-r03-line-core (0), civic-r03-synthetic-outline (1), civic-r03-selected-line (0), civic-r03-point-halo (3), r07-district-fill (16), r07-district-line (16), r07-area-glow (0), r07-area-fill (0), r07-area-line (0), r07-area-approx (0), r07-sel-outline (0), r07-sel-line (0), r07-seg-casing (0), r07-seg (0), r07-seg-dashed (0), r07-obj-halo-lo (0), r07-obj-halo (0), r07-obj-dot (0), civic-r03-point-synthetic (3), civic-r03-point (3), civic-r03-selected-point (0)
