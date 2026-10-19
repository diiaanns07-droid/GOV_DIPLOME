# R10 · эталон карты · e91acb69

```
{"root":"FINAL-4 e91acb69","sha":"e91acb69","when":"2026-10-15T12:49:43.774Z","base":"(свой сервер, временная база, CIVIC_DEMO=1)","repeat":3,"sizes":["1366x768","375x812"],"langs":["ru","kk"],"modes":["resident","akimat"],"chromium":"141.0.7390.37","machine":{"cpu":"Intel(R) Xeon(R) Processor @ 2.80GHz","cores":4,"mem_gb":16,"platform":"linux 6.18.44-fc-v114","node":"v22.22.0"}}
```

Загрузка, медиана из 3 окон без кэша, секунды от начала навигации (WebGL программный — сравнивать с прогоном на той же машине):

| Вариант | DOM готов | load | карта загружена | 1-й значок с числом | главная кнопка | карта успокоилась | запросов | КБ | длинные задачи, мс |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 1366x768-ru-resident | 0.46 | 0.48 | 5.49 | 2.36 | 2.27 | 5.11 | 106 | 8697 | 4754 |
| 1366x768-ru-akimat | 0.32 | 0.36 | 5.30 | 2.25 | — | 4.87 | 107 | 8726 | 4358 |
| 1366x768-kk-resident | 0.36 | 0.42 | 5.10 | 2.17 | 1.96 | 4.73 | 107 | 8811 | 4419 |
| 1366x768-kk-akimat | 0.38 | 0.46 | 6.01 | 2.45 | — | 5.57 | 108 | 8840 | 5048 |
| 375x812-ru-resident | 0.41 | 0.46 | 4.30 | 2.33 | 2.01 | 5.70 | 108 | 9033 | 3009 |
| 375x812-ru-akimat | 0.34 | 0.38 | 4.21 | 2.01 | 1.98 | 4.22 | 106 | 8697 | 3221 |
| 375x812-kk-resident | 0.39 | 0.40 | 3.98 | 1.98 | 1.99 | 5.56 | 109 | 9147 | 3088 |
| 375x812-kk-akimat | 0.32 | 0.36 | 3.75 | 1.98 | 1.98 | 3.80 | 107 | 8811 | 2995 |

Вид по умолчанию (первое окно):

| Вариант | слоёв видно / всего | значков (с числом) | 3D-табличек | кнопок вне карты | меню | масштаб | кадр |
|---|---|---|---|---|---|---|---|
| 1366x768-ru-resident | 37 / 48 | 6 (6) | 0 | 22 | 3: Акимат · Житель · Для сотрудников | z10.35 | default-1366x768-ru-resident.png |
| 1366x768-ru-akimat | 37 / 48 | 6 (6) | 0 | 26 | 3: Акимат · Житель · Для сотрудников | z10.35 | default-1366x768-ru-akimat.png |
| 1366x768-kk-resident | 37 / 48 | 6 (6) | 0 | 22 | 3: Әкімдік · Тұрғын · Қызметкерлерге | z10.35 | default-1366x768-kk-resident.png |
| 1366x768-kk-akimat | 37 / 48 | 6 (6) | 0 | 26 | 3: Әкімдік · Тұрғын · Қызметкерлерге | z10.35 | default-1366x768-kk-akimat.png |
| 375x812-ru-resident | 37 / 48 | 2 (2) | 0 | 14 | 8: Карта · Мои обращения · Рядом · Идеи · Вопрос акиму · Акимат · Житель · Для сотрудников | z9 | default-375x812-ru-resident.png |
| 375x812-ru-akimat | 37 / 48 | 3 (3) | 0 | 20 | 11: Карта · Картина дня · Обращения · Проекты и идеи · Вопросы жителей · Работы и отключения · QR-таблички · Службы · Акимат | z9 | default-375x812-ru-akimat.png |
| 375x812-kk-resident | 37 / 48 | 2 (2) | 0 | 15 | 8: Карта · Менің өтініштерім · Маңайда · Идеялар · Әкімге сұрақ · Әкімдік · Тұрғын · Қызметкерлерге | z9 | default-375x812-kk-resident.png |
| 375x812-kk-akimat | 37 / 48 | 3 (3) | 0 | 20 | 11: Карта · Күн қорытындысы · Өтініштер · Жобалар мен идеялар · Тұрғындар сұрақтары · Жұмыстар мен өшірулер · QR-тақтайшалар | z9 | default-375x812-kk-akimat.png |

Плавность (кадр/с · p95 мс · кадров > 50 мс) и отклик интерфейса, мс:

| Вариант | сдвиг | полёт 12→15 | отклик |
|---|---|---|---|
| 1366x768-ru-resident | 2 · 783 · 5 | 2 · 583 · 6 | complaint_form: 29, mine: 11, to_akimat: 632, lang_switch: 709 |
| 1366x768-ru-akimat | 2 · 550 · 6 | 2 · 567 · 6 | hot_select: —, day_kpi: 27, lang_switch: 1047 |
| 1366x768-kk-resident | 2 · 650 · 6 | 2 · 550 · 6 | complaint_form: 29, mine: 15, to_akimat: 873, lang_switch: 326 |
| 1366x768-kk-akimat | 1 · 667 · 4 | 2 · 550 · 6 | hot_select: —, day_kpi: 82, lang_switch: 348 |
| 375x812-ru-resident | 6 · 200 · 16 | 5 · 317 · 14 | complaint_form: 30, mine: 9, to_akimat: 226, lang_switch: 364 |
| 375x812-ru-akimat | 7 · 200 · 15 | 5 · 367 · 15 | hot_select: 627, day_kpi: 163, lang_switch: 416 |
| 375x812-kk-resident | 7 · 183 · 17 | 6 · 283 · 17 | complaint_form: 42, mine: 10, to_akimat: 246, lang_switch: 232 |
| 375x812-kk-akimat | 6 · 233 · 15 | 5 · 317 · 14 | hot_select: 582, day_kpi: 154, lang_switch: 175 |

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
| GET /api/civic/v2/modules | 17 | 3 | 8 | 200 |
| GET /api/civic/v2/heat z12 | 6 | 6 | 55 | 200 |
| GET /api/civic/v2/heat z16 | 17 | 5 | 32 | 200 |
| GET /api/civic/v2/akim/summary | 7 | 4 | 23 | 200 |
| POST /api/civic/v2/classify | 7 | 2 | 0 | 200 |
| POST /api/civic/v2/similar | 3 | 3 | 0 | 200 |
| GET /api/civic/v2/targets | 2 | 2 | 0 | 200 |
| GET /api/civic/v2/proposals | 4 | 4 | 3 | 200 |

Видимые слои стиля по умолчанию (первый вариант каждого вида):

- 1366x768-ru-resident: offline-bg (0), offline-nura-minor (0), offline-nura-street-case (0), offline-nura-street (0), offline-city-major-case (1247), offline-city-major (1247), civic-explore-lines (18), civic-explore-selected (0), civic-r03-approx-fill (6), civic-r03-approx-line (6), civic-r03-area-fill (0), civic-r03-area-line (0), civic-r03-area-line-approx (0), civic-r03-line-casing (1), civic-r03-line (1), civic-r03-line-approx (0), civic-r03-line-core (0), civic-r03-synthetic-outline (1), civic-r03-selected-line (0), civic-r03-point-halo (3), r07-district-fill (18), r07-district-line (18), r07-area-glow (0), r07-area-fill (0), r07-area-line (0), r07-area-approx (0), r07-sel-outline (0), r07-sel-line (0), r07-seg-casing (0), r07-seg (0), r07-seg-dashed (0), r07-obj-halo-lo (0), r07-obj-halo (0), r07-obj-dot (0), civic-r03-point-synthetic (3), civic-r03-point (3), civic-r03-selected-point (0)
- 1366x768-ru-akimat: offline-bg (0), offline-nura-minor (0), offline-nura-street-case (0), offline-nura-street (0), offline-city-major-case (1246), offline-city-major (1246), civic-explore-lines (17), civic-explore-selected (0), civic-r03-approx-fill (6), civic-r03-approx-line (6), civic-r03-area-fill (0), civic-r03-area-line (0), civic-r03-area-line-approx (0), civic-r03-line-casing (1), civic-r03-line (1), civic-r03-line-approx (0), civic-r03-line-core (0), civic-r03-synthetic-outline (1), civic-r03-selected-line (0), civic-r03-point-halo (3), r07-district-fill (17), r07-district-line (17), r07-area-glow (0), r07-area-fill (0), r07-area-line (0), r07-area-approx (0), r07-sel-outline (0), r07-sel-line (0), r07-seg-casing (0), r07-seg (0), r07-seg-dashed (0), r07-obj-halo-lo (0), r07-obj-halo (0), r07-obj-dot (0), civic-r03-point-synthetic (3), civic-r03-point (3), civic-r03-selected-point (0)
