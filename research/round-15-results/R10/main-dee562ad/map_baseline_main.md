# R10 · эталон карты · 2bd09480

```
{"root":"/home/user/GOV_DIPLOME","sha":"2bd09480","when":"2026-10-19T10:29:14.878Z","base":"(свой сервер, временная база, CIVIC_DEMO=1)","repeat":3,"sizes":["1366x768","375x812"],"langs":["ru","kk"],"modes":["resident","akimat"],"chromium":"141.0.7390.37","machine":{"cpu":"Intel(R) Xeon(R) Processor @ 2.10GHz","cores":4,"mem_gb":16,"platform":"linux 6.18.44-fc-v139","node":"v22.22.0"}}
```

Загрузка, медиана из 3 окон без кэша, секунды от начала навигации (WebGL программный — сравнивать с прогоном на той же машине):

| Вариант | DOM готов | load | карта загружена | 1-й значок с числом | главная кнопка | карта успокоилась | запросов | КБ | длинные задачи, мс |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 1366x768-ru-resident | 0.29 | 0.33 | 2.78 | 1.70 | 1.70 | 4.34 | 134 | 10621 | 1814 |
| 1366x768-ru-akimat | 0.34 | 0.38 | 2.69 | 1.77 | — | 4.23 | 133 | 10663 | 1720 |
| 1366x768-kk-resident | 0.29 | 0.35 | 2.54 | 1.71 | 1.71 | 4.15 | 135 | 10828 | 1659 |
| 1366x768-kk-akimat | 0.31 | 0.36 | 2.56 | 1.71 | — | 4.11 | 134 | 10870 | 1668 |
| 375x812-ru-resident | 0.32 | 0.34 | 1.87 | 1.41 | 1.41 | 3.42 | 133 | 10805 | 903 |
| 375x812-ru-akimat | 0.33 | 0.36 | 2.13 | 1.55 | 1.55 | 3.70 | 132 | 10620 | 1150 |
| 375x812-kk-resident | 0.35 | 0.36 | 2.00 | 1.48 | 1.46 | 3.55 | 134 | 11012 | 1034 |
| 375x812-kk-akimat | 0.30 | 0.33 | 2.02 | 1.53 | 1.44 | 3.58 | 133 | 10827 | 1068 |

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
| 1366x768-ru-resident | 3 · 367 · 8 | 3 · 317 · 9 | complaint_form: 20, mine: 8, to_akimat: 648, lang_switch: 390 |
| 1366x768-ru-akimat | 3 · 433 · 8 | 3 · 367 · 10 | hot_select: —, day_kpi: 80, lang_switch: 355 |
| 1366x768-kk-resident | 3 · 417 · 8 | 3 · 417 · 10 | complaint_form: 24, mine: 6, to_akimat: 573, lang_switch: 173 |
| 1366x768-kk-akimat | 4 · 300 · 10 | 3 · 350 · 9 | hot_select: —, day_kpi: 73, lang_switch: 195 |
| 375x812-ru-resident | 8 · 183 · 20 | 9 · 183 · 22 | complaint_form: 33, mine: 6, to_akimat: 208, lang_switch: 287 |
| 375x812-ru-akimat | 11 · 117 · 24 | 9 · 167 · 23 | hot_select: 573, day_kpi: 155, lang_switch: 260 |
| 375x812-kk-resident | 8 · 150 · 20 | 8 · 167 · 21 | complaint_form: 21, mine: 7, to_akimat: 222, lang_switch: 138 |
| 375x812-kk-akimat | 11 · 117 · 24 | 10 · 167 · 26 | hot_select: 587, day_kpi: 154, lang_switch: 117 |

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
| GET /api/civic/v2/modules | 18 | 3 | 14 | 200 |
| GET /api/civic/v2/heat z12 | 11 | 10 | 171 | 200 |
| GET /api/civic/v2/heat z16 | 44 | 3 | 19 | 200 |
| GET /api/civic/v2/akim/summary | 43 | 32 | 35 | 200 |
| POST /api/civic/v2/classify | 7 | 2 | 0 | 200 |
| POST /api/civic/v2/similar | 3 | 3 | 0 | 200 |
| GET /api/civic/v2/targets | 4 | 2 | 0 | 200 |
| GET /api/civic/v2/proposals | 5 | 4 | 5 | 200 |

Видимые слои стиля по умолчанию (первый вариант каждого вида):

- 1366x768-ru-resident: offline-bg (0), offline-nura-minor (0), offline-nura-street-case (0), offline-nura-street (0), offline-city-major-case (1244), offline-city-major (1244), civic-explore-lines (18), civic-explore-selected (0), civic-r03-approx-fill (0), civic-r03-approx-line (0), civic-r03-area-fill (0), civic-r03-area-line (0), civic-r03-area-line-approx (0), civic-r03-line-casing (0), civic-r03-line (0), civic-r03-line-approx (0), civic-r03-line-core (0), civic-r03-synthetic-outline (0), civic-r03-selected-line (0), civic-r03-point-halo (0), r07-district-fill (18), r07-district-line (18), r07-area-glow (0), r07-area-fill (0), r07-area-line (0), r07-area-approx (0), r07-sel-outline (0), r07-sel-line (0), r07-seg-casing (0), r07-seg (0), r07-seg-dashed (0), r07-obj-halo-lo (0), r07-obj-halo (0), r07-obj-dot (0), r07-place-line (0), r07-place-approx (0), r07-place-ring (0), civic-r03-point-synthetic (0), civic-r03-point (0), civic-r03-selected-point (0)
- 1366x768-ru-akimat: offline-bg (0), offline-nura-minor (0), offline-nura-street-case (0), offline-nura-street (0), offline-city-major-case (1236), offline-city-major (1236), civic-explore-lines (16), civic-explore-selected (0), civic-r03-approx-fill (0), civic-r03-approx-line (0), civic-r03-area-fill (0), civic-r03-area-line (0), civic-r03-area-line-approx (0), civic-r03-line-casing (0), civic-r03-line (0), civic-r03-line-approx (0), civic-r03-line-core (0), civic-r03-synthetic-outline (0), civic-r03-selected-line (0), civic-r03-point-halo (0), r07-district-fill (16), r07-district-line (16), r07-area-glow (0), r07-area-fill (0), r07-area-line (0), r07-area-approx (0), r07-sel-outline (0), r07-sel-line (0), r07-seg-casing (0), r07-seg (0), r07-seg-dashed (0), r07-obj-halo-lo (0), r07-obj-halo (0), r07-obj-dot (0), r07-place-line (0), r07-place-approx (0), r07-place-ring (0), civic-r03-point-synthetic (0), civic-r03-point (0), civic-r03-selected-point (0)
