# R10 · эталон карты · 61be62e6

```
{"root":"/home/user/bf3h","sha":"61be62e6","when":"2026-10-12T13:22:00.617Z","base":"(свой сервер, временная база, CIVIC_DEMO=1)","repeat":3,"sizes":["1366x768","375x812"],"langs":["ru","kk"],"modes":["resident","akimat"],"chromium":"141.0.7390.37","machine":{"cpu":"Intel(R) Xeon(R) Processor @ 2.10GHz","cores":4,"mem_gb":16,"platform":"linux 6.18.44-fc-v114","node":"v22.22.0"}}
```

Загрузка, медиана из 3 окон без кэша, секунды от начала навигации (WebGL программный — сравнивать с прогоном на той же машине):

| Вариант | DOM готов | load | карта загружена | 1-й значок с числом | главная кнопка | карта успокоилась | запросов | КБ | длинные задачи, мс |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 1366x768-ru-resident | 0.22 | 0.25 | 3.00 | 1.69 | 1.69 | 3.10 | 98 | 7977 | 2328 |
| 1366x768-ru-akimat | 0.20 | 0.24 | 3.23 | 1.69 | 1.69 | 3.24 | 98 | 7977 | 2366 |
| 1366x768-kk-resident | 0.21 | 0.24 | 2.97 | 1.66 | 1.66 | 2.97 | 99 | 8080 | 2269 |
| 1366x768-kk-akimat | 0.23 | 0.26 | 3.20 | 1.72 | 1.72 | 3.13 | 99 | 8080 | 2494 |
| 375x812-ru-resident | 0.21 | 0.25 | 2.52 | 1.40 | 1.40 | 4.11 | 99 | 8252 | 1631 |
| 375x812-ru-akimat | 0.21 | 0.23 | 2.52 | 1.41 | 1.41 | 4.08 | 99 | 8252 | 1586 |
| 375x812-kk-resident | 0.20 | 0.23 | 2.56 | 1.41 | 1.41 | 4.10 | 100 | 8355 | 1545 |
| 375x812-kk-akimat | 0.23 | 0.28 | 2.66 | 1.47 | 1.47 | 4.29 | 100 | 8355 | 1805 |

Вид по умолчанию (первое окно):

| Вариант | слоёв видно / всего | значков (с числом) | 3D-табличек | кнопок вне карты | меню | масштаб | кадр |
|---|---|---|---|---|---|---|---|
| 1366x768-ru-resident | 37 / 48 | 6 (6) | 0 | 25 | 3: Акимат · Житель · Для сотрудников | z9.69 | default-1366x768-ru-resident.png |
| 1366x768-ru-akimat | 37 / 48 | 6 (6) | 0 | 24 | 3: Акимат · Житель · Для сотрудников | z9.69 | default-1366x768-ru-akimat.png |
| 1366x768-kk-resident | 37 / 48 | 6 (6) | 0 | 25 | 3: Әкімдік · Тұрғын · Қызметкерлерге | z9.69 | default-1366x768-kk-resident.png |
| 1366x768-kk-akimat | 37 / 48 | 6 (6) | 0 | 24 | 3: Әкімдік · Тұрғын · Қызметкерлерге | z9.69 | default-1366x768-kk-akimat.png |
| 375x812-ru-resident | 37 / 48 | 4 (4) | 0 | 17 | 8: Карта · Мои обращения · Рядом · Идеи · Вопрос акиму · Акимат · Житель · Для сотрудников | z9 | default-375x812-ru-resident.png |
| 375x812-ru-akimat | 37 / 48 | 4 (4) | 0 | 16 | 11: Карта · Картина дня · Обращения · Проекты и идеи · Вопросы жителей · Работы и отключения · QR-таблички · Службы · Акимат | z9 | default-375x812-ru-akimat.png |
| 375x812-kk-resident | 37 / 48 | 4 (4) | 0 | 17 | 8: Карта · Менің өтініштерім · Маңайда · Идеялар · Әкімге сұрақ · Әкімдік · Тұрғын · Қызметкерлерге | z9 | default-375x812-kk-resident.png |
| 375x812-kk-akimat | 37 / 48 | 4 (4) | 0 | 16 | 11: Карта · Күн қорытындысы · Өтініштер · Жобалар мен идеялар · Тұрғындар сұрақтары · Жұмыстар мен өшірулер · QR-тақтайшалар | z9 | default-375x812-kk-akimat.png |

Плавность (кадр/с · p95 мс · кадров > 50 мс) и отклик интерфейса, мс:

| Вариант | сдвиг | полёт 12→15 | отклик |
|---|---|---|---|
| 1366x768-ru-resident | 4 · 350 · 10 | 3 · 350 · 9 | complaint_form: 23, mine: 56, to_akimat: 377, lang_switch: 329 |
| 1366x768-ru-akimat | 3 · 567 · 8 | 3 · 350 · 9 | hot_select: 565, day_kpi: 3, lang_switch: 429 |
| 1366x768-kk-resident | 3 · 417 · 8 | 4 · 350 · 11 | complaint_form: 46, mine: 57, to_akimat: 355, lang_switch: 218 |
| 1366x768-kk-akimat | 4 · 533 · 9 | 3 · 333 · 11 | hot_select: 846, day_kpi: 7, lang_switch: 170 |
| 375x812-ru-resident | 12 · 117 · 25 | 11 · 150 · 25 | complaint_form: 22, mine: 6, to_akimat: 111, lang_switch: 234 |
| 375x812-ru-akimat | 12 · 117 · 25 | 12 · 150 · 21 | hot_select: 592, day_kpi: 3, lang_switch: 264 |
| 375x812-kk-resident | 12 · 100 · 30 | 12 · 133 · 22 | complaint_form: 22, mine: 5, to_akimat: 117, lang_switch: 119 |
| 375x812-kk-akimat | 11 · 117 · 28 | 11 · 150 · 24 | hot_select: 589, day_kpi: 3, lang_switch: 112 |

Карточка места «Хан Шатыр» (правила 3–4 POLISH_WAVE_2):

| Вариант | заголовок | видно, px | содержимое, px | кнопок | главных | главная без прокрутки | «Подробнее» | кадр |
|---|---|---:|---:|---:|---:|---|---:|---|
| 1366x768-ru-resident | Остановка «Хан Шатыр» | 374 | 374 | 3 | 1 (Я тоже) | true | 2 | card-1366x768-ru-resident.jpg |
| 1366x768-ru-akimat | Остановка «Хан Шатыр» | 650 | 653 | 5 | 1 (Взять в работу) | true | 3 | card-1366x768-ru-akimat.jpg |
| 1366x768-kk-resident | «Хан Шатыр» аялдамасы | 395 | 395 | 3 | 1 (Мен де) | true | 2 | card-1366x768-kk-resident.jpg |
| 1366x768-kk-akimat | «Хан Шатыр» аялдамасы | 650 | 675 | 5 | 1 (Жұмысқа алу) | true | 3 | card-1366x768-kk-akimat.jpg |
| 375x812-ru-resident | Остановка «Хан Шатыр» | 417 | 395 | 3 | 1 (Я тоже) | true | 2 | card-375x812-ru-resident.jpg |
| 375x812-ru-akimat | Остановка «Хан Шатыр» | 417 | 675 | 5 | 1 (Взять в работу) | true | 3 | card-375x812-ru-akimat.jpg |
| 375x812-kk-resident | «Хан Шатыр» аялдамасы | 417 | 395 | 3 | 1 (Мен де) | true | 2 | card-375x812-kk-resident.jpg |
| 375x812-kk-akimat | «Хан Шатыр» аялдамасы | 417 | 675 | 5 | 1 (Жұмысқа алу) | true | 3 | card-375x812-kk-akimat.jpg |

API (6 запросов: первый и медиана остальных):

| Запрос | первый, мс | медиана, мс | КБ | статус |
|---|---:|---:|---:|---|
| GET /api/civic/v2/modules | 13 | 3 | 8 | 200 |
| GET /api/civic/v2/heat z12 | 14 | 5 | 55 | 200 |
| GET /api/civic/v2/heat z16 | 13 | 3 | 32 | 200 |
| GET /api/civic/v2/akim/summary | 149 | 3 | 23 | 200 |
| POST /api/civic/v2/classify | 6 | 2 | 0 | 200 |
| POST /api/civic/v2/similar | 3 | 2 | 0 | 200 |
| GET /api/civic/v2/targets | 2 | 2 | 0 | 200 |
| GET /api/civic/v2/proposals | 3 | 4 | 3 | 200 |

Видимые слои стиля по умолчанию (первый вариант каждого вида):

- 1366x768-ru-resident: offline-bg (0), offline-nura-minor (0), offline-nura-street-case (0), offline-nura-street (0), offline-city-major-case (1100), offline-city-major (1100), civic-explore-lines (12), civic-explore-selected (0), civic-r03-approx-fill (6), civic-r03-approx-line (6), civic-r03-area-fill (0), civic-r03-area-line (0), civic-r03-area-line-approx (0), civic-r03-line-casing (1), civic-r03-line (1), civic-r03-line-approx (0), civic-r03-line-core (0), civic-r03-synthetic-outline (1), civic-r03-selected-line (0), civic-r03-point-halo (3), r07-district-fill (12), r07-district-line (12), r07-area-glow (0), r07-area-fill (0), r07-area-line (0), r07-area-approx (0), r07-sel-outline (0), r07-sel-line (0), r07-seg-casing (0), r07-seg (0), r07-seg-dashed (0), r07-obj-halo-lo (0), r07-obj-halo (0), r07-obj-dot (0), civic-r03-point-synthetic (3), civic-r03-point (3), civic-r03-selected-point (0)
- 1366x768-ru-akimat: offline-bg (0), offline-nura-minor (0), offline-nura-street-case (0), offline-nura-street (0), offline-city-major-case (1100), offline-city-major (1100), civic-explore-lines (12), civic-explore-selected (0), civic-r03-approx-fill (6), civic-r03-approx-line (6), civic-r03-area-fill (0), civic-r03-area-line (0), civic-r03-area-line-approx (0), civic-r03-line-casing (1), civic-r03-line (1), civic-r03-line-approx (0), civic-r03-line-core (0), civic-r03-synthetic-outline (1), civic-r03-selected-line (0), civic-r03-point-halo (3), r07-district-fill (12), r07-district-line (12), r07-area-glow (0), r07-area-fill (0), r07-area-line (0), r07-area-approx (0), r07-sel-outline (0), r07-sel-line (0), r07-seg-casing (0), r07-seg (0), r07-seg-dashed (0), r07-obj-halo-lo (0), r07-obj-halo (0), r07-obj-dot (0), civic-r03-point-synthetic (3), civic-r03-point (3), civic-r03-selected-point (0)
