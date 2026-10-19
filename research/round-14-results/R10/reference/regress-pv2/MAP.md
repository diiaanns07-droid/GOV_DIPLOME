# R10 · эталон карты · 69984f0f

```
{"root":"/home/user/bpv2","sha":"69984f0f","when":"2026-10-13T11:42:36.142Z","base":"(свой сервер, временная база, CIVIC_DEMO=1)","repeat":3,"sizes":["1366x768","375x812"],"langs":["ru","kk"],"modes":["resident","akimat"],"chromium":"141.0.7390.37","machine":{"cpu":"Intel(R) Xeon(R) Processor @ 2.10GHz","cores":4,"mem_gb":16,"platform":"linux 6.18.44-fc-v114","node":"v22.22.0"}}
```

Загрузка, медиана из 3 окон без кэша, секунды от начала навигации (WebGL программный — сравнивать с прогоном на той же машине):

| Вариант | DOM готов | load | карта загружена | 1-й значок с числом | главная кнопка | карта успокоилась | запросов | КБ | длинные задачи, мс |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 1366x768-ru-resident | 0.22 | 0.25 | 3.40 | 1.56 | 1.56 | 3.37 | 101 | 8441 | 2869 |
| 1366x768-ru-akimat | 0.26 | 0.29 | 3.62 | 1.85 | 1.85 | 3.45 | 101 | 8441 | 2978 |
| 1366x768-kk-resident | 0.20 | 0.23 | 3.53 | 1.61 | 1.61 | 3.33 | 102 | 8547 | 2685 |
| 1366x768-kk-akimat | 0.22 | 0.28 | 3.65 | 1.64 | 1.64 | 3.43 | 102 | 8547 | 2849 |
| 375x812-ru-resident | 0.22 | 0.25 | 2.54 | 1.38 | 1.38 | 4.09 | 102 | 8717 | 1719 |
| 375x812-ru-akimat | 0.23 | 0.25 | 2.61 | 1.44 | 1.45 | 4.04 | 102 | 8717 | 1760 |
| 375x812-kk-resident | 0.24 | 0.27 | 2.80 | 1.50 | 1.50 | 4.44 | 103 | 8823 | 1876 |
| 375x812-kk-akimat | 0.23 | 0.25 | 2.49 | 1.41 | 1.41 | 4.06 | 103 | 8823 | 1701 |

Вид по умолчанию (первое окно):

| Вариант | слоёв видно / всего | значков (с числом) | 3D-табличек | кнопок вне карты | меню | масштаб | кадр |
|---|---|---|---|---|---|---|---|
| 1366x768-ru-resident | 37 / 48 | 6 (6) | 0 | 32 | 3: Акимат · Житель · Для сотрудников | z10.3 | default-1366x768-ru-resident.png |
| 1366x768-ru-akimat | 37 / 48 | 6 (6) | 0 | 31 | 3: Акимат · Житель · Для сотрудников | z10.3 | default-1366x768-ru-akimat.png |
| 1366x768-kk-resident | 37 / 48 | 6 (6) | 0 | 32 | 3: Әкімдік · Тұрғын · Қызметкерлерге | z10.3 | default-1366x768-kk-resident.png |
| 1366x768-kk-akimat | 37 / 48 | 6 (6) | 0 | 31 | 3: Әкімдік · Тұрғын · Қызметкерлерге | z10.3 | default-1366x768-kk-akimat.png |
| 375x812-ru-resident | 37 / 48 | 3 (3) | 0 | 20 | 8: Карта · Мои обращения · Рядом · Идеи · Вопрос акиму · Акимат · Житель · Для сотрудников | z9 | default-375x812-ru-resident.png |
| 375x812-ru-akimat | 37 / 48 | 3 (3) | 0 | 19 | 11: Карта · Картина дня · Обращения · Проекты и идеи · Вопросы жителей · Работы и отключения · QR-таблички · Службы · Акимат | z9 | default-375x812-ru-akimat.png |
| 375x812-kk-resident | 37 / 48 | 3 (3) | 0 | 21 | 8: Карта · Менің өтініштерім · Маңайда · Идеялар · Әкімге сұрақ · Әкімдік · Тұрғын · Қызметкерлерге | z9 | default-375x812-kk-resident.png |
| 375x812-kk-akimat | 37 / 48 | 3 (3) | 0 | 20 | 11: Карта · Күн қорытындысы · Өтініштер · Жобалар мен идеялар · Тұрғындар сұрақтары · Жұмыстар мен өшірулер · QR-тақтайшалар | z9 | default-375x812-kk-akimat.png |

Плавность (кадр/с · p95 мс · кадров > 50 мс) и отклик интерфейса, мс:

| Вариант | сдвиг | полёт 12→15 | отклик |
|---|---|---|---|
| 1366x768-ru-resident | 3 · 333 · 9 | 3 · 333 · 11 | complaint_form: 22, mine: 8, to_akimat: 334, lang_switch: 358 |
| 1366x768-ru-akimat | 3 · 533 · 9 | 3 · 350 · 10 | hot_select: 695, day_kpi: 158, lang_switch: 490 |
| 1366x768-kk-resident | 3 · 333 · 10 | 4 · 317 · 11 | complaint_form: 20, mine: 6, to_akimat: 287, lang_switch: 151 |
| 1366x768-kk-akimat | 4 · 250 · 11 | 3 · 400 · 10 | hot_select: 639, day_kpi: 167, lang_switch: 160 |
| 375x812-ru-resident | 10 · 150 · 24 | 10 · 150 · 22 | complaint_form: 30, mine: 7, to_akimat: 115, lang_switch: 253 |
| 375x812-ru-akimat | 12 · 117 · 28 | 12 · 150 · 20 | hot_select: 581, day_kpi: 158, lang_switch: 284 |
| 375x812-kk-resident | 10 · 133 · 25 | 11 · 167 · 21 | complaint_form: 20, mine: 6, to_akimat: 137, lang_switch: 108 |
| 375x812-kk-akimat | 14 · 100 · 25 | 12 · 133 · 19 | hot_select: 656, day_kpi: 175, lang_switch: 102 |

Карточка места «Хан Шатыр» (правила 3–4 POLISH_WAVE_2):

| Вариант | заголовок | видно, px | содержимое, px | кнопок | главных | главная без прокрутки | «Подробнее» | кадр |
|---|---|---:|---:|---:|---:|---|---:|---|
| 1366x768-ru-resident | Остановка «Хан Шатыр» | 336 | 336 | 4 | 1 (Я тоже) | true | 0 | card-1366x768-ru-resident.jpg |
| 1366x768-ru-akimat | Остановка «Хан Шатыр» | 514 | 514 | 8 | 1 (Взять в работу) | true | 0 | card-1366x768-ru-akimat.jpg |
| 1366x768-kk-resident | «Хан Шатыр» аялдамасы | 336 | 336 | 4 | 1 (Мен де) | true | 0 | card-1366x768-kk-resident.jpg |
| 1366x768-kk-akimat | «Хан Шатыр» аялдамасы | 514 | 514 | 8 | 1 (Жұмысқа алу) | true | 0 | card-1366x768-kk-akimat.jpg |
| 375x812-ru-resident | Остановка «Хан Шатыр» | 417 | 336 | 4 | 1 (Я тоже) | true | 0 | card-375x812-ru-resident.jpg |
| 375x812-ru-akimat | Остановка «Хан Шатыр» | 417 | 514 | 8 | 1 (Взять в работу) | true | 0 | card-375x812-ru-akimat.jpg |
| 375x812-kk-resident | «Хан Шатыр» аялдамасы | 417 | 358 | 4 | 1 (Мен де) | true | 0 | card-375x812-kk-resident.jpg |
| 375x812-kk-akimat | «Хан Шатыр» аялдамасы | 417 | 536 | 8 | 1 (Жұмысқа алу) | true | 0 | card-375x812-kk-akimat.jpg |

API (6 запросов: первый и медиана остальных):

| Запрос | первый, мс | медиана, мс | КБ | статус |
|---|---:|---:|---:|---|
| GET /api/civic/v2/modules | 12 | 2 | 8 | 200 |
| GET /api/civic/v2/heat z12 | 5 | 4 | 55 | 200 |
| GET /api/civic/v2/heat z16 | 10 | 3 | 32 | 200 |
| GET /api/civic/v2/akim/summary | 3 | 3 | 23 | 200 |
| POST /api/civic/v2/classify | 7 | 2 | 0 | 200 |
| POST /api/civic/v2/similar | 4 | 2 | 0 | 200 |
| GET /api/civic/v2/targets | 2 | 2 | 0 | 200 |
| GET /api/civic/v2/proposals | 3 | 3 | 3 | 200 |

Видимые слои стиля по умолчанию (первый вариант каждого вида):

- 1366x768-ru-resident: offline-bg (0), offline-nura-minor (0), offline-nura-street-case (0), offline-nura-street (0), offline-city-major-case (1254), offline-city-major (1254), civic-explore-lines (18), civic-explore-selected (0), civic-r03-approx-fill (6), civic-r03-approx-line (6), civic-r03-area-fill (0), civic-r03-area-line (0), civic-r03-area-line-approx (0), civic-r03-line-casing (1), civic-r03-line (1), civic-r03-line-approx (0), civic-r03-line-core (0), civic-r03-synthetic-outline (1), civic-r03-selected-line (0), civic-r03-point-halo (3), r07-district-fill (18), r07-district-line (18), r07-area-glow (0), r07-area-fill (0), r07-area-line (0), r07-area-approx (0), r07-sel-outline (0), r07-sel-line (0), r07-seg-casing (0), r07-seg (0), r07-seg-dashed (0), r07-obj-halo-lo (0), r07-obj-halo (0), r07-obj-dot (0), civic-r03-point-synthetic (3), civic-r03-point (3), civic-r03-selected-point (0)
- 1366x768-ru-akimat: offline-bg (0), offline-nura-minor (0), offline-nura-street-case (0), offline-nura-street (0), offline-city-major-case (1254), offline-city-major (1254), civic-explore-lines (18), civic-explore-selected (0), civic-r03-approx-fill (6), civic-r03-approx-line (6), civic-r03-area-fill (0), civic-r03-area-line (0), civic-r03-area-line-approx (0), civic-r03-line-casing (1), civic-r03-line (1), civic-r03-line-approx (0), civic-r03-line-core (0), civic-r03-synthetic-outline (1), civic-r03-selected-line (0), civic-r03-point-halo (3), r07-district-fill (18), r07-district-line (18), r07-area-glow (0), r07-area-fill (0), r07-area-line (0), r07-area-approx (0), r07-sel-outline (0), r07-sel-line (0), r07-seg-casing (0), r07-seg (0), r07-seg-dashed (0), r07-obj-halo-lo (0), r07-obj-halo (0), r07-obj-dot (0), civic-r03-point-synthetic (3), civic-r03-point (3), civic-r03-selected-point (0)
