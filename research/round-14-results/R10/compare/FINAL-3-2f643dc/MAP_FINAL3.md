# R10 · эталон карты · 2f643dc7

```
{"root":"/home/user/bf3c","sha":"2f643dc7","when":"2026-10-12T09:52:20.603Z","base":"(свой сервер, временная база, CIVIC_DEMO=1)","repeat":3,"sizes":["1366x768","375x812"],"langs":["ru","kk"],"modes":["resident","akimat"],"chromium":"141.0.7390.37","machine":{"cpu":"Intel(R) Xeon(R) Processor @ 2.10GHz","cores":4,"mem_gb":16,"platform":"linux 6.18.44-fc-v114","node":"v22.22.0"}}
```

Загрузка, медиана из 3 окон без кэша, секунды от начала навигации (WebGL программный — сравнивать с прогоном на той же машине):

| Вариант | DOM готов | load | карта загружена | 1-й значок с числом | главная кнопка | карта успокоилась | запросов | КБ | длинные задачи, мс |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 1366x768-ru-resident | 0.23 | 0.25 | 3.38 | 2.69 | 1.37 | 3.56 | 99 | 8187 | 2807 |
| 1366x768-ru-akimat | 0.20 | 0.22 | 3.37 | 2.69 | 2.69 | 3.61 | 99 | 8187 | 2797 |
| 1366x768-kk-resident | 0.23 | 0.23 | 3.50 | 2.48 | 1.61 | 3.70 | 100 | 8283 | 2963 |
| 1366x768-kk-akimat | 0.18 | 0.21 | 3.49 | 2.59 | 2.59 | 3.68 | 100 | 8283 | 2954 |
| 375x812-ru-resident | 0.21 | 0.22 | 2.47 | 1.87 | 1.23 | 3.10 | 99 | 8187 | 1399 |
| 375x812-ru-akimat | 0.20 | 0.22 | 2.52 | 1.75 | — | 3.12 | 99 | 8187 | 1603 |
| 375x812-kk-resident | 0.19 | 0.21 | 2.54 | 2.21 | 1.20 | 3.03 | 100 | 8283 | 1706 |
| 375x812-kk-akimat | 0.17 | 0.18 | 2.47 | 2.19 | — | 3.01 | 100 | 8283 | 1530 |

Вид по умолчанию (первое окно):

| Вариант | слоёв видно / всего | значков (с числом) | 3D-табличек | кнопок вне карты | меню | масштаб | кадр |
|---|---|---|---|---|---|---|---|
| 1366x768-ru-resident | 37 / 48 | 6 (6) | 0 | 25 | 3: Акимат · Житель · Для сотрудников | z10.34 | default-1366x768-ru-resident.png |
| 1366x768-ru-akimat | 37 / 48 | 6 (6) | 0 | 24 | 3: Акимат · Житель · Для сотрудников | z10.34 | default-1366x768-ru-akimat.png |
| 1366x768-kk-resident | 37 / 48 | 6 (6) | 0 | 24 | 3: Әкімдік · Тұрғын · Қызметкерлерге | z10.34 | default-1366x768-kk-resident.png |
| 1366x768-kk-akimat | 37 / 48 | 6 (6) | 0 | 23 | 3: Әкімдік · Тұрғын · Қызметкерлерге | z10.34 | default-1366x768-kk-akimat.png |
| 375x812-ru-resident | 37 / 48 | 3 (3) | 0 | 17 | 8: Карта · Мои обращения · Рядом · Идеи · Вопрос акиму · Акимат · Житель · Для сотрудников | z9 | default-375x812-ru-resident.png |
| 375x812-ru-akimat | 37 / 48 | 3 (3) | 0 | 16 | 11: Карта · Картина дня · Обращения · Проекты и идеи · Вопросы жителей · Работы и отключения · QR-таблички · Службы · Акимат | z9 | default-375x812-ru-akimat.png |
| 375x812-kk-resident | 37 / 48 | 3 (3) | 0 | 13 | 8: Карта · Менің өтініштерім · Маңайда · Идеялар · Әкімге сұрақ · Әкімдік · Тұрғын · Қызметкерлерге | z9 | default-375x812-kk-resident.png |
| 375x812-kk-akimat | 37 / 48 | 3 (3) | 0 | 13 | 11: Карта · Күн қорытындысы · Өтініштер · Жобалар мен идеялар · Тұрғындар сұрақтары · Жұмыстар мен өшірулер · QR-тақтайшалар | z9 | default-375x812-kk-akimat.png |

Плавность (кадр/с · p95 мс · кадров > 50 мс) и отклик интерфейса, мс:

| Вариант | сдвиг | полёт 12→15 | отклик |
|---|---|---|---|
| 1366x768-ru-resident | 4 · 267 · 11 | 3 · 450 · 8 | complaint_form: 21, mine: 5, to_akimat: 359, lang_switch: 473 |
| 1366x768-ru-akimat | 4 · 283 · 11 | 4 · 350 · 11 | hot_select: 635, day_kpi: 3, lang_switch: 468 |
| 1366x768-kk-resident | 4 · 267 · 11 | 4 · 300 · 12 | complaint_form: 17, mine: 55, to_akimat: 322, lang_switch: 180 |
| 1366x768-kk-akimat | 4 · 283 · 10 | 4 · 350 · 11 | hot_select: 750, day_kpi: 4, lang_switch: 188 |
| 375x812-ru-resident | 17 · 100 · 28 | 11 · 150 · 21 | complaint_form: 26, mine: 55, to_akimat: 110, lang_switch: 316 |
| 375x812-ru-akimat | 12 · 100 · 27 | 11 · 150 · 26 | hot_select: 543, day_kpi: 6, lang_switch: 373 |
| 375x812-kk-resident | 14 · 100 · 27 | 12 · 117 · 24 | complaint_form: 20, mine: 54, to_akimat: 90, lang_switch: 79 |
| 375x812-kk-akimat | 14 · 83 · 31 | 14 · 133 · 17 | hot_select: 701, day_kpi: 6, lang_switch: 91 |

Карточка места «Хан Шатыр» (правила 3–4 POLISH_WAVE_2):

| Вариант | заголовок | видно, px | содержимое, px | кнопок | главных | главная без прокрутки | «Подробнее» | кадр |
|---|---|---:|---:|---:|---:|---|---:|---|
| 1366x768-ru-resident | Остановка «Хан Шатыр» | 517 | 517 | 3 | 1 (Я тоже) | true | 0 | card-1366x768-ru-resident.jpg |
| 1366x768-ru-akimat | Остановка «Хан Шатыр» | 652 | 732 | 5 | 1 (Взять в работу) | true | 0 | card-1366x768-ru-akimat.jpg |
| 1366x768-kk-resident | «Хан Шатыр» аялдамасы | 517 | 517 | 3 | 1 (Мен де) | true | 0 | card-1366x768-kk-resident.jpg |
| 1366x768-kk-akimat | «Хан Шатыр» аялдамасы | 652 | 732 | 5 | 1 (Жұмысқа алу) | true | 0 | card-1366x768-kk-akimat.jpg |
| 375x812-ru-resident | Остановка «Хан Шатыр» | 415 | 517 | 3 | 1 (Я тоже) | true | 0 | card-375x812-ru-resident.jpg |
| 375x812-ru-akimat | Остановка «Хан Шатыр» | 415 | 810 | 5 | 1 (Взять в работу) | true | 0 | card-375x812-ru-akimat.jpg |
| 375x812-kk-resident | «Хан Шатыр» аялдамасы | 415 | 517 | 3 | 1 (Мен де) | true | 0 | card-375x812-kk-resident.jpg |
| 375x812-kk-akimat | «Хан Шатыр» аялдамасы | 415 | 754 | 5 | 1 (Жұмысқа алу) | true | 0 | card-375x812-kk-akimat.jpg |

API (6 запросов: первый и медиана остальных):

| Запрос | первый, мс | медиана, мс | КБ | статус |
|---|---:|---:|---:|---|
| GET /api/civic/v2/modules | 16 | 3 | 8 | 200 |
| GET /api/civic/v2/heat z12 | 4 | 4 | 54 | 200 |
| GET /api/civic/v2/heat z16 | 11 | 3 | 32 | 200 |
| GET /api/civic/v2/akim/summary | 3 | 2 | 23 | 200 |
| POST /api/civic/v2/classify | 6 | 2 | 0 | 200 |
| POST /api/civic/v2/similar | 3 | 2 | 0 | 200 |
| GET /api/civic/v2/targets | 2 | 2 | 0 | 200 |
| GET /api/civic/v2/proposals | 3 | 3 | 3 | 200 |

Видимые слои стиля по умолчанию (первый вариант каждого вида):

- 1366x768-ru-resident: offline-bg (0), offline-nura-minor (0), offline-nura-street-case (0), offline-nura-street (0), offline-city-major-case (1248), offline-city-major (1248), civic-explore-lines (18), civic-explore-selected (0), civic-r03-approx-fill (6), civic-r03-approx-line (6), civic-r03-area-fill (0), civic-r03-area-line (0), civic-r03-area-line-approx (0), civic-r03-line-casing (1), civic-r03-line (1), civic-r03-line-approx (0), civic-r03-line-core (0), civic-r03-synthetic-outline (1), civic-r03-selected-line (0), civic-r03-point-halo (3), r07-district-fill (18), r07-district-line (18), r07-area-glow (0), r07-area-fill (0), r07-area-line (0), r07-area-approx (0), r07-sel-outline (0), r07-sel-line (0), r07-seg-casing (0), r07-seg (0), r07-seg-dashed (0), r07-obj-halo-lo (0), r07-obj-halo (0), r07-obj-dot (0), civic-r03-point-synthetic (3), civic-r03-point (3), civic-r03-selected-point (0)
- 1366x768-ru-akimat: offline-bg (0), offline-nura-minor (0), offline-nura-street-case (0), offline-nura-street (0), offline-city-major-case (1248), offline-city-major (1248), civic-explore-lines (18), civic-explore-selected (0), civic-r03-approx-fill (6), civic-r03-approx-line (6), civic-r03-area-fill (0), civic-r03-area-line (0), civic-r03-area-line-approx (0), civic-r03-line-casing (1), civic-r03-line (1), civic-r03-line-approx (0), civic-r03-line-core (0), civic-r03-synthetic-outline (1), civic-r03-selected-line (0), civic-r03-point-halo (3), r07-district-fill (18), r07-district-line (18), r07-area-glow (0), r07-area-fill (0), r07-area-line (0), r07-area-approx (0), r07-sel-outline (0), r07-sel-line (0), r07-seg-casing (0), r07-seg (0), r07-seg-dashed (0), r07-obj-halo-lo (0), r07-obj-halo (0), r07-obj-dot (0), civic-r03-point-synthetic (3), civic-r03-point (3), civic-r03-selected-point (0)
