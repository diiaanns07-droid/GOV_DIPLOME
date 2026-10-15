# R10 · эталон карты · c97aa5f5

```
{"root":"/tmp/claude-0/-home-user-GOV-DIPLOME/62d68526-d416-54f0-b206-35e3353bc4a5/scratchpad/builds/b0-c97aa5f5","sha":"c97aa5f5","when":"2026-10-15T13:25:41.051Z","base":"(свой сервер, временная база, CIVIC_DEMO=1)","repeat":3,"sizes":["1366x768","375x812"],"langs":["ru","kk"],"modes":["resident","akimat"],"chromium":"141.0.7390.37","machine":{"cpu":"Intel(R) Xeon(R) Processor @ 2.80GHz","cores":4,"mem_gb":16,"platform":"linux 6.18.44-fc-v114","node":"v22.22.0"}}
```

Загрузка, медиана из 3 окон без кэша, секунды от начала навигации (WebGL программный — сравнивать с прогоном на той же машине):

| Вариант | DOM готов | load | карта загружена | 1-й значок с числом | главная кнопка | карта успокоилась | запросов | КБ | длинные задачи, мс |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 1366x768-ru-resident | 0.41 | 0.47 | 5.94 | 2.52 | 2.51 | 5.52 | 118 | 9544 | 4973 |
| 1366x768-ru-akimat | 0.42 | 0.52 | 6.51 | 2.72 | — | 5.99 | 120 | 9575 | 5529 |
| 1366x768-kk-resident | 0.45 | 0.48 | 6.46 | 2.86 | 2.86 | 6.90 | 119 | 9709 | 6171 |
| 1366x768-kk-akimat | 0.45 | 0.53 | 6.34 | 2.64 | — | 5.86 | 120 | 9739 | 5271 |
| 375x812-ru-resident | 0.41 | 0.49 | 4.55 | 2.26 | 2.24 | 5.79 | 120 | 10005 | 3384 |
| 375x812-ru-akimat | 0.40 | 0.42 | 3.76 | 2.09 | 2.09 | 3.61 | 118 | 9544 | 2674 |
| 375x812-kk-resident | 0.38 | 0.40 | 3.74 | 1.96 | 1.96 | 4.81 | 120 | 9895 | 3213 |
| 375x812-kk-akimat | 0.42 | 0.45 | 4.31 | 2.23 | 2.23 | 4.20 | 119 | 9709 | 3190 |

Вид по умолчанию (первое окно):

| Вариант | слоёв видно / всего | значков (с числом) | 3D-табличек | кнопок вне карты | меню | масштаб | кадр |
|---|---|---|---|---|---|---|---|
| 1366x768-ru-resident | 37 / 48 | 6 (6) | 0 | 22 | 3: Акимат · Житель · Для сотрудников | z10.37 | default-1366x768-ru-resident.png |
| 1366x768-ru-akimat | 37 / 48 | 6 (6) | 0 | 26 | 3: Акимат · Житель · Для сотрудников | z10.37 | default-1366x768-ru-akimat.png |
| 1366x768-kk-resident | 37 / 48 | 6 (6) | 0 | 22 | 3: Әкімдік · Тұрғын · Қызметкерлерге | z10.37 | default-1366x768-kk-resident.png |
| 1366x768-kk-akimat | 37 / 48 | 6 (6) | 0 | 26 | 3: Әкімдік · Тұрғын · Қызметкерлерге | z10.37 | default-1366x768-kk-akimat.png |
| 375x812-ru-resident | 37 / 48 | 3 (3) | 0 | 15 | 8: Карта · Мои обращения · Рядом · Идеи · Вопросы и встречи · Акимат · Житель · Для сотрудников | z9 | default-375x812-ru-resident.png |
| 375x812-ru-akimat | 37 / 48 | 2 (2) | 0 | 20 | 11: Карта · Картина дня · Обращения · Штаб ведомств · Проекты и идеи · Вопросы и встречи · Спросить Birge · QR-таблички · Ак | z9 | default-375x812-ru-akimat.png |
| 375x812-kk-resident | 37 / 48 | 3 (3) | 0 | 16 | 8: Карта · Менің өтініштерім · Маңайда · Идеялар · Сұрақтар мен кездесулер · Әкімдік · Тұрғын · Қызметкерлерге | z9 | default-375x812-kk-resident.png |
| 375x812-kk-akimat | 37 / 48 | 2 (2) | 0 | 21 | 11: Карта · Күн қорытындысы · Өтініштер · Ведомстволар штабы · Жобалар мен идеялар · Сұрақтар мен кездесулер · Birge-ден сұр | z9 | default-375x812-kk-akimat.png |

Плавность (кадр/с · p95 мс · кадров > 50 мс) и отклик интерфейса, мс:

| Вариант | сдвиг | полёт 12→15 | отклик |
|---|---|---|---|
| 1366x768-ru-resident | 1 · 1167 · 5 | 2 · 583 · 5 | complaint_form: 51, mine: 10, to_akimat: 730, lang_switch: 971 |
| 1366x768-ru-akimat | 1 · 1217 · 4 | 2 · 667 · 6 | hot_select: —, day_kpi: 57, lang_switch: 1234 |
| 1366x768-kk-resident | 1 · 833 · 4 | 1 · 733 · 6 | complaint_form: 33, mine: 10, to_akimat: 675, lang_switch: 335 |
| 1366x768-kk-akimat | 1 · 950 · 4 | 2 · 583 · 6 | hot_select: —, day_kpi: 50, lang_switch: 346 |
| 375x812-ru-resident | 6 · 200 · 15 | 5 · 250 · 14 | complaint_form: 32, mine: 18, to_akimat: 186, lang_switch: 776 |
| 375x812-ru-akimat | 6 · 233 · 15 | 6 · 267 · 16 | hot_select: 676, day_kpi: 173, lang_switch: 877 |
| 375x812-kk-resident | 7 · 183 · 16 | 6 · 250 · 16 | complaint_form: 30, mine: 14, to_akimat: 170, lang_switch: 193 |
| 375x812-kk-akimat | 6 · 183 · 16 | 6 · 300 · 16 | hot_select: 602, day_kpi: 160, lang_switch: 220 |

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
| GET /api/civic/v2/modules | 18 | 6 | 14 | 200 |
| GET /api/civic/v2/heat z12 | 23 | 17 | 171 | 200 |
| GET /api/civic/v2/heat z16 | 51 | 5 | 19 | 200 |
| GET /api/civic/v2/akim/summary | 5 | 6 | 25 | 200 |
| POST /api/civic/v2/classify | 11 | 3 | 0 | 200 |
| POST /api/civic/v2/similar | 5 | 4 | 0 | 200 |
| GET /api/civic/v2/targets | 4 | 3 | 0 | 200 |
| GET /api/civic/v2/proposals | 7 | 6 | 3 | 200 |

Видимые слои стиля по умолчанию (первый вариант каждого вида):

- 1366x768-ru-resident: offline-bg (0), offline-nura-minor (0), offline-nura-street-case (0), offline-nura-street (0), offline-city-major-case (1244), offline-city-major (1244), civic-explore-lines (18), civic-explore-selected (0), civic-r03-approx-fill (6), civic-r03-approx-line (6), civic-r03-area-fill (0), civic-r03-area-line (0), civic-r03-area-line-approx (0), civic-r03-line-casing (1), civic-r03-line (1), civic-r03-line-approx (0), civic-r03-line-core (0), civic-r03-synthetic-outline (1), civic-r03-selected-line (0), civic-r03-point-halo (3), r07-district-fill (18), r07-district-line (18), r07-area-glow (0), r07-area-fill (0), r07-area-line (0), r07-area-approx (0), r07-sel-outline (0), r07-sel-line (0), r07-seg-casing (0), r07-seg (0), r07-seg-dashed (0), r07-obj-halo-lo (0), r07-obj-halo (0), r07-obj-dot (0), civic-r03-point-synthetic (3), civic-r03-point (3), civic-r03-selected-point (0)
- 1366x768-ru-akimat: offline-bg (0), offline-nura-minor (0), offline-nura-street-case (0), offline-nura-street (0), offline-city-major-case (1236), offline-city-major (1236), civic-explore-lines (16), civic-explore-selected (0), civic-r03-approx-fill (6), civic-r03-approx-line (6), civic-r03-area-fill (0), civic-r03-area-line (0), civic-r03-area-line-approx (0), civic-r03-line-casing (1), civic-r03-line (1), civic-r03-line-approx (0), civic-r03-line-core (0), civic-r03-synthetic-outline (1), civic-r03-selected-line (0), civic-r03-point-halo (3), r07-district-fill (16), r07-district-line (16), r07-area-glow (0), r07-area-fill (0), r07-area-line (0), r07-area-approx (0), r07-sel-outline (0), r07-sel-line (0), r07-seg-casing (0), r07-seg (0), r07-seg-dashed (0), r07-obj-halo-lo (0), r07-obj-halo (0), r07-obj-dot (0), civic-r03-point-synthetic (3), civic-r03-point (3), civic-r03-selected-point (0)
