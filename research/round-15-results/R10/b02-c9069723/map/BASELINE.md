# R10 · эталон карты · c9069723

```
{"root":"/tmp/claude-0/-home-user-GOV-DIPLOME/62d68526-d416-54f0-b206-35e3353bc4a5/scratchpad/builds/r01-c9069723","sha":"c9069723","when":"2026-10-15T14:37:02.532Z","base":"(свой сервер, временная база, CIVIC_DEMO=1)","repeat":3,"sizes":["1366x768","375x812"],"langs":["ru","kk"],"modes":["resident","akimat"],"chromium":"141.0.7390.37","machine":{"cpu":"Intel(R) Xeon(R) Processor @ 2.80GHz","cores":4,"mem_gb":16,"platform":"linux 6.18.44-fc-v114","node":"v22.22.0"}}
```

Загрузка, медиана из 3 окон без кэша, секунды от начала навигации (WebGL программный — сравнивать с прогоном на той же машине):

| Вариант | DOM готов | load | карта загружена | 1-й значок с числом | главная кнопка | карта успокоилась | запросов | КБ | длинные задачи, мс |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 1366x768-ru-resident | 0.44 | 0.50 | 6.56 | 2.68 | 2.68 | 6.43 | 119 | 9567 | 5439 |
| 1366x768-ru-akimat | 0.44 | 0.50 | 6.54 | 2.80 | — | 6.08 | 120 | 9881 | 5440 |
| 1366x768-kk-resident | 0.40 | 0.44 | 5.82 | 2.56 | 2.56 | 5.44 | 119 | 9731 | 4832 |
| 1366x768-kk-akimat | 0.45 | 0.52 | 6.16 | 2.63 | — | 5.70 | 120 | 9770 | 4900 |
| 375x812-ru-resident | 0.38 | 0.41 | 3.95 | 2.16 | 2.16 | 5.72 | 120 | 10028 | 2951 |
| 375x812-ru-akimat | 0.38 | 0.47 | 4.10 | 2.15 | 2.15 | 3.96 | 118 | 9567 | 3059 |
| 375x812-kk-resident | 0.47 | 0.48 | 4.21 | 2.25 | 2.26 | 5.66 | 121 | 10193 | 2993 |
| 375x812-kk-akimat | 0.48 | 0.51 | 4.33 | 2.32 | 2.32 | 4.17 | 119 | 9731 | 3207 |

Вид по умолчанию (первое окно):

| Вариант | слоёв видно / всего | значков (с числом) | 3D-табличек | кнопок вне карты | меню | масштаб | кадр |
|---|---|---|---|---|---|---|---|
| 1366x768-ru-resident | 37 / 48 | 6 (6) | 0 | 22 | 3: Акимат · Житель · Для сотрудников | z10.37 | default-1366x768-ru-resident.png |
| 1366x768-ru-akimat | 37 / 48 | 6 (6) | 0 | 26 | 3: Акимат · Житель · Для сотрудников | z10.37 | default-1366x768-ru-akimat.png |
| 1366x768-kk-resident | 37 / 48 | 6 (6) | 0 | 22 | 3: Әкімдік · Тұрғын · Қызметкерлерге | z10.37 | default-1366x768-kk-resident.png |
| 1366x768-kk-akimat | 37 / 48 | 6 (6) | 0 | 26 | 3: Әкімдік · Тұрғын · Қызметкерлерге | z10.37 | default-1366x768-kk-akimat.png |
| 375x812-ru-resident | 37 / 48 | 3 (3) | 0 | 15 | 8: Карта · Мои обращения · Рядом · Идеи · Вопросы и встречи · Акимат · Житель · Для сотрудников | z9 | default-375x812-ru-resident.png |
| 375x812-ru-akimat | 37 / 48 | 2 (2) | 0 | 20 | 12: Карта · Картина дня · Обращения · Штаб ведомств · Проекты и идеи · Вопросы и встречи · Спросить Birge · Ситуационный цен | z9 | default-375x812-ru-akimat.png |
| 375x812-kk-resident | 37 / 48 | 3 (3) | 0 | 16 | 8: Карта · Менің өтініштерім · Маңайда · Идеялар · Сұрақтар мен кездесулер · Әкімдік · Тұрғын · Қызметкерлерге | z9 | default-375x812-kk-resident.png |
| 375x812-kk-akimat | 37 / 48 | 2 (2) | 0 | 21 | 12: Карта · Күн қорытындысы · Өтініштер · Ведомстволар штабы · Жобалар мен идеялар · Сұрақтар мен кездесулер · Birge-ден сұр | z9 | default-375x812-kk-akimat.png |

Плавность (кадр/с · p95 мс · кадров > 50 мс) и отклик интерфейса, мс:

| Вариант | сдвиг | полёт 12→15 | отклик |
|---|---|---|---|
| 1366x768-ru-resident | 1 · 967 · 5 | 2 · 733 · 6 | complaint_form: 38, mine: 11, to_akimat: 774, lang_switch: 1421 |
| 1366x768-ru-akimat | 1 · 1067 · 5 | 1 · 683 · 4 | hot_select: —, day_kpi: 71, lang_switch: 1148 |
| 1366x768-kk-resident | 2 · 883 · 6 | 2 · 667 · 7 | complaint_form: 41, mine: 17, to_akimat: 610, lang_switch: 277 |
| 1366x768-kk-akimat | 1 · 933 · 4 | 2 · 750 · 6 | hot_select: —, day_kpi: 116, lang_switch: 489 |
| 375x812-ru-resident | 5 · 267 · 13 | 5 · 317 · 15 | complaint_form: 37, mine: 18, to_akimat: 217, lang_switch: 1078 |
| 375x812-ru-akimat | 6 · 233 · 16 | 5 · 267 · 14 | hot_select: 547, day_kpi: 158, lang_switch: 1099 |
| 375x812-kk-resident | 7 · 200 · 16 | 5 · 333 · 13 | complaint_form: 42, mine: 14, to_akimat: 219, lang_switch: 215 |
| 375x812-kk-akimat | 7 · 183 · 16 | 6 · 283 · 15 | hot_select: 686, day_kpi: 159, lang_switch: 211 |

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
| GET /api/civic/v2/modules | 24 | 5 | 14 | 200 |
| GET /api/civic/v2/heat z12 | 89 | 23 | 171 | 200 |
| GET /api/civic/v2/heat z16 | 53 | 5 | 19 | 200 |
| GET /api/civic/v2/akim/summary | 562 | 16 | 31 | 200 |
| POST /api/civic/v2/classify | 10 | 4 | 0 | 200 |
| POST /api/civic/v2/similar | 6 | 5 | 0 | 200 |
| GET /api/civic/v2/targets | 5 | 3 | 0 | 200 |
| GET /api/civic/v2/proposals | 6 | 5 | 3 | 200 |

Видимые слои стиля по умолчанию (первый вариант каждого вида):

- 1366x768-ru-resident: offline-bg (0), offline-nura-minor (0), offline-nura-street-case (0), offline-nura-street (0), offline-city-major-case (1244), offline-city-major (1244), civic-explore-lines (18), civic-explore-selected (0), civic-r03-approx-fill (6), civic-r03-approx-line (6), civic-r03-area-fill (0), civic-r03-area-line (0), civic-r03-area-line-approx (0), civic-r03-line-casing (1), civic-r03-line (1), civic-r03-line-approx (0), civic-r03-line-core (0), civic-r03-synthetic-outline (1), civic-r03-selected-line (0), civic-r03-point-halo (3), r07-district-fill (18), r07-district-line (18), r07-area-glow (0), r07-area-fill (0), r07-area-line (0), r07-area-approx (0), r07-sel-outline (0), r07-sel-line (0), r07-seg-casing (0), r07-seg (0), r07-seg-dashed (0), r07-obj-halo-lo (0), r07-obj-halo (0), r07-obj-dot (0), civic-r03-point-synthetic (3), civic-r03-point (3), civic-r03-selected-point (0)
- 1366x768-ru-akimat: offline-bg (0), offline-nura-minor (0), offline-nura-street-case (0), offline-nura-street (0), offline-city-major-case (1236), offline-city-major (1236), civic-explore-lines (16), civic-explore-selected (0), civic-r03-approx-fill (6), civic-r03-approx-line (6), civic-r03-area-fill (0), civic-r03-area-line (0), civic-r03-area-line-approx (0), civic-r03-line-casing (1), civic-r03-line (1), civic-r03-line-approx (0), civic-r03-line-core (0), civic-r03-synthetic-outline (1), civic-r03-selected-line (0), civic-r03-point-halo (3), r07-district-fill (16), r07-district-line (16), r07-area-glow (0), r07-area-fill (0), r07-area-line (0), r07-area-approx (0), r07-sel-outline (0), r07-sel-line (0), r07-seg-casing (0), r07-seg (0), r07-seg-dashed (0), r07-obj-halo-lo (0), r07-obj-halo (0), r07-obj-dot (0), civic-r03-point-synthetic (3), civic-r03-point (3), civic-r03-selected-point (0)
