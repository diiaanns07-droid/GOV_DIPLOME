# R10 · эталон карты · f94f0fc1

```
{"root":"/home/user/bf3f","sha":"f94f0fc1","when":"2026-10-12T10:57:30.800Z","base":"(свой сервер, временная база, CIVIC_DEMO=1)","repeat":3,"sizes":["1366x768","375x812"],"langs":["ru","kk"],"modes":["resident","akimat"],"chromium":"141.0.7390.37","machine":{"cpu":"Intel(R) Xeon(R) Processor @ 2.10GHz","cores":4,"mem_gb":16,"platform":"linux 6.18.44-fc-v114","node":"v22.22.0"}}
```

Загрузка, медиана из 3 окон без кэша, секунды от начала навигации (WebGL программный — сравнивать с прогоном на той же машине):

| Вариант | DOM готов | load | карта загружена | 1-й значок с числом | главная кнопка | карта успокоилась | запросов | КБ | длинные задачи, мс |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 1366x768-ru-resident | 0.21 | 0.27 | 3.24 | 1.68 | 1.42 | 2.97 | 98 | 7929 | 2509 |
| 1366x768-ru-akimat | 0.21 | 0.23 | 2.89 | 1.66 | 1.66 | 2.89 | 98 | 7929 | 2353 |
| 1366x768-kk-resident | 0.19 | 0.35 | 3.27 | 1.62 | 1.42 | 3.27 | 99 | 8032 | 2534 |
| 1366x768-kk-akimat | 0.18 | 0.20 | 3.24 | 1.70 | 1.70 | 3.23 | 99 | 8032 | 2580 |
| 375x812-ru-resident | 0.18 | 0.20 | 2.14 | 1.35 | 1.17 | 3.75 | 99 | 8204 | 1385 |
| 375x812-ru-akimat | 0.19 | 0.22 | 2.46 | 1.44 | — | 4.07 | 99 | 8204 | 1734 |
| 375x812-kk-resident | 0.19 | 0.21 | 2.32 | 1.39 | 1.22 | 3.85 | 100 | 8307 | 1496 |
| 375x812-kk-akimat | 0.21 | 0.24 | 2.36 | 1.48 | — | 3.90 | 100 | 8307 | 1577 |

Вид по умолчанию (первое окно):

| Вариант | слоёв видно / всего | значков (с числом) | 3D-табличек | кнопок вне карты | меню | масштаб | кадр |
|---|---|---|---|---|---|---|---|
| 1366x768-ru-resident | 37 / 48 | 6 (6) | 0 | 25 | 3: Акимат · Житель · Для сотрудников | z10.33 | default-1366x768-ru-resident.png |
| 1366x768-ru-akimat | 37 / 48 | 6 (6) | 0 | 24 | 3: Акимат · Житель · Для сотрудников | z10.33 | default-1366x768-ru-akimat.png |
| 1366x768-kk-resident | 37 / 48 | 6 (6) | 0 | 24 | 3: Әкімдік · Тұрғын · Қызметкерлерге | z10.33 | default-1366x768-kk-resident.png |
| 1366x768-kk-akimat | 37 / 48 | 6 (6) | 0 | 23 | 3: Әкімдік · Тұрғын · Қызметкерлерге | z10.33 | default-1366x768-kk-akimat.png |
| 375x812-ru-resident | 37 / 48 | 3 (3) | 0 | 17 | 8: Карта · Мои обращения · Рядом · Идеи · Вопрос акиму · Акимат · Житель · Для сотрудников | z9 | default-375x812-ru-resident.png |
| 375x812-ru-akimat | 37 / 48 | 3 (3) | 0 | 16 | 11: Карта · Картина дня · Обращения · Проекты и идеи · Вопросы жителей · Работы и отключения · QR-таблички · Службы · Акимат | z9 | default-375x812-ru-akimat.png |
| 375x812-kk-resident | 37 / 48 | 3 (3) | 0 | 13 | 8: Карта · Менің өтініштерім · Маңайда · Идеялар · Әкімге сұрақ · Әкімдік · Тұрғын · Қызметкерлерге | z9 | default-375x812-kk-resident.png |
| 375x812-kk-akimat | 37 / 48 | 3 (3) | 0 | 13 | 11: Карта · Күн қорытындысы · Өтініштер · Жобалар мен идеялар · Тұрғындар сұрақтары · Жұмыстар мен өшірулер · QR-тақтайшалар | z9 | default-375x812-kk-akimat.png |

Плавность (кадр/с · p95 мс · кадров > 50 мс) и отклик интерфейса, мс:

| Вариант | сдвиг | полёт 12→15 | отклик |
|---|---|---|---|
| 1366x768-ru-resident | 4 · 250 · 12 | 4 · 350 · 11 | complaint_form: 21, mine: 56, to_akimat: 270, lang_switch: 306 |
| 1366x768-ru-akimat | 4 · 267 · 11 | 4 · 317 · 11 | hot_select: 817, day_kpi: 3, lang_switch: 408 |
| 1366x768-kk-resident | 5 · 250 · 12 | 4 · 333 · 12 | complaint_form: 22, mine: 55, to_akimat: 255, lang_switch: 127 |
| 1366x768-kk-akimat | 4 · 300 · 10 | 4 · 267 · 12 | hot_select: 632, day_kpi: 5, lang_switch: 169 |
| 375x812-ru-resident | 13 · 100 · 30 | 12 · 150 · 22 | complaint_form: 22, mine: 55, to_akimat: 80, lang_switch: 282 |
| 375x812-ru-akimat | 14 · 117 · 25 | 12 · 117 · 26 | hot_select: 689, day_kpi: 3, lang_switch: 264 |
| 375x812-kk-resident | 17 · 100 · 29 | 12 · 133 · 20 | complaint_form: 20, mine: 55, to_akimat: 119, lang_switch: 84 |
| 375x812-kk-akimat | 14 · 100 · 31 | 13 · 117 · 21 | hot_select: 655, day_kpi: 3, lang_switch: 134 |

Карточка места «Хан Шатыр» (правила 3–4 POLISH_WAVE_2):

| Вариант | заголовок | видно, px | содержимое, px | кнопок | главных | главная без прокрутки | «Подробнее» | кадр |
|---|---|---:|---:|---:|---:|---|---:|---|
| 1366x768-ru-resident | Остановка «Хан Шатыр» | 517 | 517 | 3 | 1 (Я тоже) | true | 0 | card-1366x768-ru-resident.jpg |
| 1366x768-ru-akimat | Остановка «Хан Шатыр» | 654 | 732 | 5 | 1 (Взять в работу) | true | 0 | card-1366x768-ru-akimat.jpg |
| 1366x768-kk-resident | «Хан Шатыр» аялдамасы | 517 | 517 | 3 | 1 (Мен де) | true | 0 | card-1366x768-kk-resident.jpg |
| 1366x768-kk-akimat | «Хан Шатыр» аялдамасы | 654 | 732 | 5 | 1 (Жұмысқа алу) | true | 0 | card-1366x768-kk-akimat.jpg |
| 375x812-ru-resident | Остановка «Хан Шатыр» | 417 | 517 | 3 | 1 (Я тоже) | true | 0 | card-375x812-ru-resident.jpg |
| 375x812-ru-akimat | Остановка «Хан Шатыр» | 417 | 810 | 5 | 1 (Взять в работу) | true | 0 | card-375x812-ru-akimat.jpg |
| 375x812-kk-resident | «Хан Шатыр» аялдамасы | 417 | 517 | 3 | 1 (Мен де) | true | 0 | card-375x812-kk-resident.jpg |
| 375x812-kk-akimat | «Хан Шатыр» аялдамасы | 417 | 754 | 5 | 1 (Жұмысқа алу) | true | 0 | card-375x812-kk-akimat.jpg |

API (6 запросов: первый и медиана остальных):

| Запрос | первый, мс | медиана, мс | КБ | статус |
|---|---:|---:|---:|---|
| GET /api/civic/v2/modules | 12 | 2 | 8 | 200 |
| GET /api/civic/v2/heat z12 | 4 | 4 | 54 | 200 |
| GET /api/civic/v2/heat z16 | 12 | 3 | 32 | 200 |
| GET /api/civic/v2/akim/summary | 2 | 2 | 23 | 200 |
| POST /api/civic/v2/classify | 6 | 2 | 0 | 200 |
| POST /api/civic/v2/similar | 2 | 2 | 0 | 200 |
| GET /api/civic/v2/targets | 2 | 2 | 0 | 200 |
| GET /api/civic/v2/proposals | 3 | 3 | 3 | 200 |

Видимые слои стиля по умолчанию (первый вариант каждого вида):

- 1366x768-ru-resident: offline-bg (0), offline-nura-minor (0), offline-nura-street-case (0), offline-nura-street (0), offline-city-major-case (1248), offline-city-major (1248), civic-explore-lines (18), civic-explore-selected (0), civic-r03-approx-fill (6), civic-r03-approx-line (6), civic-r03-area-fill (0), civic-r03-area-line (0), civic-r03-area-line-approx (0), civic-r03-line-casing (1), civic-r03-line (1), civic-r03-line-approx (0), civic-r03-line-core (0), civic-r03-synthetic-outline (1), civic-r03-selected-line (0), civic-r03-point-halo (3), r07-district-fill (18), r07-district-line (18), r07-area-glow (0), r07-area-fill (0), r07-area-line (0), r07-area-approx (0), r07-sel-outline (0), r07-sel-line (0), r07-seg-casing (0), r07-seg (0), r07-seg-dashed (0), r07-obj-halo-lo (0), r07-obj-halo (0), r07-obj-dot (0), civic-r03-point-synthetic (3), civic-r03-point (3), civic-r03-selected-point (0)
- 1366x768-ru-akimat: offline-bg (0), offline-nura-minor (0), offline-nura-street-case (0), offline-nura-street (0), offline-city-major-case (1248), offline-city-major (1248), civic-explore-lines (18), civic-explore-selected (0), civic-r03-approx-fill (6), civic-r03-approx-line (6), civic-r03-area-fill (0), civic-r03-area-line (0), civic-r03-area-line-approx (0), civic-r03-line-casing (1), civic-r03-line (1), civic-r03-line-approx (0), civic-r03-line-core (0), civic-r03-synthetic-outline (1), civic-r03-selected-line (0), civic-r03-point-halo (3), r07-district-fill (18), r07-district-line (18), r07-area-glow (0), r07-area-fill (0), r07-area-line (0), r07-area-approx (0), r07-sel-outline (0), r07-sel-line (0), r07-seg-casing (0), r07-seg (0), r07-seg-dashed (0), r07-obj-halo-lo (0), r07-obj-halo (0), r07-obj-dot (0), civic-r03-point-synthetic (3), civic-r03-point (3), civic-r03-selected-point (0)
