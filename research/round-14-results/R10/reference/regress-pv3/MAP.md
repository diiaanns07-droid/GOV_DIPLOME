# R10 · эталон карты · 69984f0f

```
{"root":"/home/user/bpv3","sha":"69984f0f","when":"2026-10-13T12:36:45.539Z","base":"(свой сервер, временная база, CIVIC_DEMO=1)","repeat":3,"sizes":["1366x768","375x812"],"langs":["ru","kk"],"modes":["resident","akimat"],"chromium":"141.0.7390.37","machine":{"cpu":"Intel(R) Xeon(R) Processor @ 2.10GHz","cores":4,"mem_gb":16,"platform":"linux 6.18.44-fc-v114","node":"v22.22.0"}}
```

Загрузка, медиана из 3 окон без кэша, секунды от начала навигации (WebGL программный — сравнивать с прогоном на той же машине):

| Вариант | DOM готов | load | карта загружена | 1-й значок с числом | главная кнопка | карта успокоилась | запросов | КБ | длинные задачи, мс |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 1366x768-ru-resident | 0.25 | 0.28 | 3.67 | 1.82 | 1.82 | 3.42 | 101 | 8512 | 2916 |
| 1366x768-ru-akimat | 0.22 | 0.26 | 3.64 | 1.68 | 1.62 | 3.63 | 101 | 8512 | 3084 |
| 1366x768-kk-resident | 0.22 | 0.25 | 3.52 | 1.62 | 1.62 | 3.31 | 102 | 8626 | 2786 |
| 1366x768-kk-akimat | 0.21 | 0.23 | 3.49 | 1.63 | 1.63 | 3.26 | 102 | 8626 | 2731 |
| 375x812-ru-resident | 0.21 | 0.23 | 2.44 | 1.35 | 1.35 | 3.99 | 102 | 8788 | 1573 |
| 375x812-ru-akimat | 0.21 | 0.25 | 2.37 | 1.37 | 1.37 | 3.89 | 102 | 8788 | 1551 |
| 375x812-kk-resident | 0.19 | 0.24 | 2.54 | 1.54 | 1.54 | 4.19 | 103 | 8902 | 1580 |
| 375x812-kk-akimat | 0.22 | 0.25 | 2.58 | 1.49 | 1.49 | 4.15 | 103 | 8902 | 1817 |

Вид по умолчанию (первое окно):

| Вариант | слоёв видно / всего | значков (с числом) | 3D-табличек | кнопок вне карты | меню | масштаб | кадр |
|---|---|---|---|---|---|---|---|
| 1366x768-ru-resident | 37 / 48 | 6 (6) | 0 | 31 | 3: Акимат · Житель · Для сотрудников | z10.3 | default-1366x768-ru-resident.png |
| 1366x768-ru-akimat | 37 / 48 | 6 (6) | 0 | 30 | 3: Акимат · Житель · Для сотрудников | z10.3 | default-1366x768-ru-akimat.png |
| 1366x768-kk-resident | 37 / 48 | 6 (6) | 0 | 31 | 3: Әкімдік · Тұрғын · Қызметкерлерге | z10.3 | default-1366x768-kk-resident.png |
| 1366x768-kk-akimat | 37 / 48 | 6 (6) | 0 | 30 | 3: Әкімдік · Тұрғын · Қызметкерлерге | z10.3 | default-1366x768-kk-akimat.png |
| 375x812-ru-resident | 37 / 48 | 3 (3) | 0 | 19 | 8: Карта · Мои обращения · Рядом · Идеи · Вопрос акиму · Акимат · Житель · Для сотрудников | z9 | default-375x812-ru-resident.png |
| 375x812-ru-akimat | 37 / 48 | 3 (3) | 0 | 18 | 11: Карта · Картина дня · Обращения · Проекты и идеи · Вопросы жителей · Работы и отключения · QR-таблички · Службы · Акимат | z9 | default-375x812-ru-akimat.png |
| 375x812-kk-resident | 37 / 48 | 3 (3) | 0 | 20 | 8: Карта · Менің өтініштерім · Маңайда · Идеялар · Әкімге сұрақ · Әкімдік · Тұрғын · Қызметкерлерге | z9 | default-375x812-kk-resident.png |
| 375x812-kk-akimat | 37 / 48 | 3 (3) | 0 | 19 | 11: Карта · Күн қорытындысы · Өтініштер · Жобалар мен идеялар · Тұрғындар сұрақтары · Жұмыстар мен өшірулер · QR-тақтайшалар | z9 | default-375x812-kk-akimat.png |

Плавность (кадр/с · p95 мс · кадров > 50 мс) и отклик интерфейса, мс:

| Вариант | сдвиг | полёт 12→15 | отклик |
|---|---|---|---|
| 1366x768-ru-resident | 3 · 283 · 10 | 4 · 317 · 11 | complaint_form: 28, mine: 6, to_akimat: 349, lang_switch: 403 |
| 1366x768-ru-akimat | 3 · 467 · 9 | 4 · 333 · 12 | hot_select: 665, day_kpi: 180, lang_switch: 382 |
| 1366x768-kk-resident | 3 · 333 · 9 | 3 · 400 · 9 | complaint_form: 25, mine: 7, to_akimat: 429, lang_switch: 181 |
| 1366x768-kk-akimat | 3 · 500 · 10 | 3 · 367 · 11 | hot_select: 516, day_kpi: 159, lang_switch: 5 |
| 375x812-ru-resident | 12 · 100 · 28 | 12 · 133 · 23 | complaint_form: 25, mine: 56, to_akimat: 84, lang_switch: 121 |
| 375x812-ru-akimat | 12 · 117 · 25 | 12 · 150 · 21 | hot_select: 522, day_kpi: 158, lang_switch: 303 |
| 375x812-kk-resident | 12 · 117 · 28 | 9 · 183 · 24 | complaint_form: 20, mine: 5, to_akimat: 116, lang_switch: 100 |
| 375x812-kk-akimat | 11 · 117 · 26 | 10 · 183 · 22 | hot_select: 533, day_kpi: 163, lang_switch: 91 |

Карточка места «Хан Шатыр» (правила 3–4 POLISH_WAVE_2):

| Вариант | заголовок | видно, px | содержимое, px | кнопок | главных | главная без прокрутки | «Подробнее» | кадр |
|---|---|---:|---:|---:|---:|---|---:|---|
| 1366x768-ru-resident | Остановка «Хан Шатыр» | 336 | 336 | 4 | 1 (Я тоже) | true | 0 | card-1366x768-ru-resident.jpg |
| 1366x768-ru-akimat | Остановка «Хан Шатыр» | 462 | 462 | 8 | 1 (Взять в работу) | true | 0 | card-1366x768-ru-akimat.jpg |
| 1366x768-kk-resident | «Хан Шатыр» аялдамасы | 336 | 336 | 4 | 1 (Мен де) | true | 0 | card-1366x768-kk-resident.jpg |
| 1366x768-kk-akimat | «Хан Шатыр» аялдамасы | 462 | 462 | 8 | 1 (Жұмысқа алу) | true | 0 | card-1366x768-kk-akimat.jpg |
| 375x812-ru-resident | Остановка «Хан Шатыр» | 417 | 358 | 4 | 1 (Я тоже) | true | 0 | card-375x812-ru-resident.jpg |
| 375x812-ru-akimat | Остановка «Хан Шатыр» | 417 | 485 | 8 | 1 (Взять в работу) | true | 0 | card-375x812-ru-akimat.jpg |
| 375x812-kk-resident | «Хан Шатыр» аялдамасы | 417 | 358 | 4 | 1 (Мен де) | true | 0 | card-375x812-kk-resident.jpg |
| 375x812-kk-akimat | «Хан Шатыр» аялдамасы | 417 | 485 | 8 | 1 (Жұмысқа алу) | true | 0 | card-375x812-kk-akimat.jpg |

API (6 запросов: первый и медиана остальных):

| Запрос | первый, мс | медиана, мс | КБ | статус |
|---|---:|---:|---:|---|
| GET /api/civic/v2/modules | 11 | 3 | 8 | 200 |
| GET /api/civic/v2/heat z12 | 5 | 5 | 55 | 200 |
| GET /api/civic/v2/heat z16 | 11 | 3 | 32 | 200 |
| GET /api/civic/v2/akim/summary | 3 | 3 | 23 | 200 |
| POST /api/civic/v2/classify | 5 | 2 | 0 | 200 |
| POST /api/civic/v2/similar | 3 | 2 | 0 | 200 |
| GET /api/civic/v2/targets | 2 | 2 | 0 | 200 |
| GET /api/civic/v2/proposals | 3 | 3 | 3 | 200 |

Видимые слои стиля по умолчанию (первый вариант каждого вида):

- 1366x768-ru-resident: offline-bg (0), offline-nura-minor (0), offline-nura-street-case (0), offline-nura-street (0), offline-city-major-case (1254), offline-city-major (1254), civic-explore-lines (18), civic-explore-selected (0), civic-r03-approx-fill (6), civic-r03-approx-line (6), civic-r03-area-fill (0), civic-r03-area-line (0), civic-r03-area-line-approx (0), civic-r03-line-casing (1), civic-r03-line (1), civic-r03-line-approx (0), civic-r03-line-core (0), civic-r03-synthetic-outline (1), civic-r03-selected-line (0), civic-r03-point-halo (3), r07-district-fill (18), r07-district-line (18), r07-area-glow (0), r07-area-fill (0), r07-area-line (0), r07-area-approx (0), r07-sel-outline (0), r07-sel-line (0), r07-seg-casing (0), r07-seg (0), r07-seg-dashed (0), r07-obj-halo-lo (0), r07-obj-halo (0), r07-obj-dot (0), civic-r03-point-synthetic (3), civic-r03-point (3), civic-r03-selected-point (0)
- 1366x768-ru-akimat: offline-bg (0), offline-nura-minor (0), offline-nura-street-case (0), offline-nura-street (0), offline-city-major-case (1254), offline-city-major (1254), civic-explore-lines (18), civic-explore-selected (0), civic-r03-approx-fill (6), civic-r03-approx-line (6), civic-r03-area-fill (0), civic-r03-area-line (0), civic-r03-area-line-approx (0), civic-r03-line-casing (1), civic-r03-line (1), civic-r03-line-approx (0), civic-r03-line-core (0), civic-r03-synthetic-outline (1), civic-r03-selected-line (0), civic-r03-point-halo (3), r07-district-fill (18), r07-district-line (18), r07-area-glow (0), r07-area-fill (0), r07-area-line (0), r07-area-approx (0), r07-sel-outline (0), r07-sel-line (0), r07-seg-casing (0), r07-seg (0), r07-seg-dashed (0), r07-obj-halo-lo (0), r07-obj-halo (0), r07-obj-dot (0), civic-r03-point-synthetic (3), civic-r03-point (3), civic-r03-selected-point (0)
