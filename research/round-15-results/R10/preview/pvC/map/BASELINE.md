# R10 · эталон карты · c97aa5f5

```
{"root":"/tmp/claude-0/-home-user-GOV-DIPLOME/62d68526-d416-54f0-b206-35e3353bc4a5/scratchpad/builds/pvC","sha":"c97aa5f5","when":"2026-10-15T13:55:51.858Z","base":"(свой сервер, временная база, CIVIC_DEMO=1)","repeat":3,"sizes":["1366x768","375x812"],"langs":["ru","kk"],"modes":["resident","akimat"],"chromium":"141.0.7390.37","machine":{"cpu":"Intel(R) Xeon(R) Processor @ 2.80GHz","cores":4,"mem_gb":16,"platform":"linux 6.18.44-fc-v114","node":"v22.22.0"}}
```

Загрузка, медиана из 3 окон без кэша, секунды от начала навигации (WebGL программный — сравнивать с прогоном на той же машине):

| Вариант | DOM готов | load | карта загружена | 1-й значок с числом | главная кнопка | карта успокоилась | запросов | КБ | длинные задачи, мс |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 1366x768-ru-resident | 0.44 | 0.49 | 6.63 | 2.83 | 2.83 | 6.17 | 124 | 9886 | 5585 |
| 1366x768-ru-akimat | 0.50 | 0.54 | 5.96 | 2.70 | — | 5.80 | 124 | 9929 | 5117 |
| 1366x768-kk-resident | 0.45 | 0.50 | 6.06 | 2.49 | 2.49 | 5.62 | 124 | 10051 | 4885 |
| 1366x768-kk-akimat | 0.46 | 0.52 | 6.52 | 2.68 | — | 6.06 | 125 | 10094 | 5391 |
| 375x812-ru-resident | 0.43 | 0.45 | 4.21 | 2.14 | 2.14 | 5.73 | 125 | 10347 | 3130 |
| 375x812-ru-akimat | 0.47 | 0.55 | 4.46 | 2.47 | 2.39 | 4.28 | 123 | 9886 | 3246 |
| 375x812-kk-resident | 0.45 | 0.48 | 4.04 | 2.08 | 2.08 | 5.62 | 126 | 10512 | 2962 |
| 375x812-kk-akimat | 0.44 | 0.50 | 4.50 | 2.24 | 2.24 | 4.30 | 124 | 10051 | 3306 |

Вид по умолчанию (первое окно):

| Вариант | слоёв видно / всего | значков (с числом) | 3D-табличек | кнопок вне карты | меню | масштаб | кадр |
|---|---|---|---|---|---|---|---|
| 1366x768-ru-resident | 37 / 48 | 6 (6) | 0 | 22 | 3: Акимат · Житель · Для сотрудников | z10.37 | default-1366x768-ru-resident.png |
| 1366x768-ru-akimat | 37 / 48 | 6 (6) | 0 | 26 | 3: Акимат · Житель · Для сотрудников | z10.37 | default-1366x768-ru-akimat.png |
| 1366x768-kk-resident | 37 / 48 | 6 (6) | 0 | 22 | 3: Әкімдік · Тұрғын · Қызметкерлерге | z10.37 | default-1366x768-kk-resident.png |
| 1366x768-kk-akimat | 37 / 48 | 6 (6) | 0 | 26 | 3: Әкімдік · Тұрғын · Қызметкерлерге | z10.37 | default-1366x768-kk-akimat.png |
| 375x812-ru-resident | 37 / 48 | 3 (3) | 0 | 15 | 9: Карта · Мои обращения · Мой двор · Идеи · Сделаем вместе · Вопросы и встречи · Акимат · Житель · Для сотрудников | z9 | default-375x812-ru-resident.png |
| 375x812-ru-akimat | 37 / 48 | 2 (2) | 0 | 20 | 12: Карта · Картина дня · Обращения · Ведомства · Проекты и идеи · Сделаем вместе · Вопросы и встречи · Спросить Birge · QR- | z9 | default-375x812-ru-akimat.png |
| 375x812-kk-resident | 37 / 48 | 3 (3) | 0 | 16 | 9: Карта · Менің өтініштерім · Менің аулам · Идеялар · Бірге жасайық · Сұрақтар мен кездесулер · Әкімдік · Тұрғын · Қызметк | z9 | default-375x812-kk-resident.png |
| 375x812-kk-akimat | 37 / 48 | 2 (2) | 0 | 21 | 12: Карта · Күн қорытындысы · Өтініштер · Ведомстволар · Жобалар мен идеялар · Бірге жасайық · Сұрақтар мен кездесулер · Bir | z9 | default-375x812-kk-akimat.png |

Плавность (кадр/с · p95 мс · кадров > 50 мс) и отклик интерфейса, мс:

| Вариант | сдвиг | полёт 12→15 | отклик |
|---|---|---|---|
| 1366x768-ru-resident | 1 · 1017 · 4 | 1 · 633 · 5 | complaint_form: 55, mine: 13, to_akimat: 707, lang_switch: 773 |
| 1366x768-ru-akimat | 1 · 783 · 5 | 2 · 717 · 5 | hot_select: —, day_kpi: 54, lang_switch: 665 |
| 1366x768-kk-resident | 2 · 767 · 5 | 2 · 583 · 6 | complaint_form: 51, mine: 13, to_akimat: 595, lang_switch: 350 |
| 1366x768-kk-akimat | 2 · 783 · 6 | 2 · 683 · 6 | hot_select: —, day_kpi: 90, lang_switch: 332 |
| 375x812-ru-resident | 4 · 300 · 10 | 5 · 283 · 14 | complaint_form: 33, mine: 14, to_akimat: 190, lang_switch: 481 |
| 375x812-ru-akimat | 5 · 200 · 14 | 5 · 317 · 14 | hot_select: 854, day_kpi: 156, lang_switch: 448 |
| 375x812-kk-resident | 5 · 250 · 13 | 5 · 283 · 15 | complaint_form: 37, mine: 9, to_akimat: 237, lang_switch: 242 |
| 375x812-kk-akimat | 6 · 200 · 14 | 5 · 283 · 14 | hot_select: 586, day_kpi: 158, lang_switch: 173 |

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
| GET /api/civic/v2/modules | 26 | 6 | 14 | 200 |
| GET /api/civic/v2/heat z12 | 21 | 21 | 171 | 200 |
| GET /api/civic/v2/heat z16 | 80 | 9 | 19 | 200 |
| GET /api/civic/v2/akim/summary | 7 | 9 | 35 | 200 |
| POST /api/civic/v2/classify | 9 | 5 | 0 | 200 |
| POST /api/civic/v2/similar | 10 | 7 | 0 | 200 |
| GET /api/civic/v2/targets | 5 | 5 | 0 | 200 |
| GET /api/civic/v2/proposals | 10 | 8 | 3 | 200 |

Видимые слои стиля по умолчанию (первый вариант каждого вида):

- 1366x768-ru-resident: offline-bg (0), offline-nura-minor (0), offline-nura-street-case (0), offline-nura-street (0), offline-city-major-case (1244), offline-city-major (1244), civic-explore-lines (18), civic-explore-selected (0), civic-r03-approx-fill (6), civic-r03-approx-line (6), civic-r03-area-fill (0), civic-r03-area-line (0), civic-r03-area-line-approx (0), civic-r03-line-casing (1), civic-r03-line (1), civic-r03-line-approx (0), civic-r03-line-core (0), civic-r03-synthetic-outline (1), civic-r03-selected-line (0), civic-r03-point-halo (3), r07-district-fill (18), r07-district-line (18), r07-area-glow (0), r07-area-fill (0), r07-area-line (0), r07-area-approx (0), r07-sel-outline (0), r07-sel-line (0), r07-seg-casing (0), r07-seg (0), r07-seg-dashed (0), r07-obj-halo-lo (0), r07-obj-halo (0), r07-obj-dot (0), civic-r03-point-synthetic (3), civic-r03-point (3), civic-r03-selected-point (0)
- 1366x768-ru-akimat: offline-bg (0), offline-nura-minor (0), offline-nura-street-case (0), offline-nura-street (0), offline-city-major-case (1236), offline-city-major (1236), civic-explore-lines (16), civic-explore-selected (0), civic-r03-approx-fill (6), civic-r03-approx-line (6), civic-r03-area-fill (0), civic-r03-area-line (0), civic-r03-area-line-approx (0), civic-r03-line-casing (1), civic-r03-line (1), civic-r03-line-approx (0), civic-r03-line-core (0), civic-r03-synthetic-outline (1), civic-r03-selected-line (0), civic-r03-point-halo (3), r07-district-fill (16), r07-district-line (16), r07-area-glow (0), r07-area-fill (0), r07-area-line (0), r07-area-approx (0), r07-sel-outline (0), r07-sel-line (0), r07-seg-casing (0), r07-seg (0), r07-seg-dashed (0), r07-obj-halo-lo (0), r07-obj-halo (0), r07-obj-dot (0), civic-r03-point-synthetic (3), civic-r03-point (3), civic-r03-selected-point (0)
