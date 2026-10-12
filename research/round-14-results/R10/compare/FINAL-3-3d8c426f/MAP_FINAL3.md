# R10 · эталон карты · 3d8c426f

```
{"root":"/home/user/bf3g","sha":"3d8c426f","when":"2026-10-12T11:58:08.542Z","base":"(свой сервер, временная база, CIVIC_DEMO=1)","repeat":3,"sizes":["1366x768","375x812"],"langs":["ru","kk"],"modes":["resident","akimat"],"chromium":"141.0.7390.37","machine":{"cpu":"Intel(R) Xeon(R) Processor @ 2.10GHz","cores":4,"mem_gb":16,"platform":"linux 6.18.44-fc-v114","node":"v22.22.0"}}
```

Загрузка, медиана из 3 окон без кэша, секунды от начала навигации (WebGL программный — сравнивать с прогоном на той же машине):

| Вариант | DOM готов | load | карта загружена | 1-й значок с числом | главная кнопка | карта успокоилась | запросов | КБ | длинные задачи, мс |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 1366x768-ru-resident | 0.23 | 0.25 | 3.16 | 1.70 | 1.70 | 3.17 | 98 | 7941 | 2358 |
| 1366x768-ru-akimat | 0.24 | 0.28 | 3.43 | 1.74 | 1.74 | 3.39 | 98 | 7941 | 2942 |
| 1366x768-kk-resident | 0.21 | 0.31 | 3.33 | 1.76 | 1.76 | 3.13 | 99 | 8044 | 2498 |
| 1366x768-kk-akimat | 0.24 | 0.27 | 3.17 | 1.58 | 1.58 | 3.31 | 100 | 8044 | 2791 |
| 375x812-ru-resident | 0.22 | 0.24 | 2.40 | 1.32 | 1.32 | 4.08 | 99 | 8216 | 1540 |
| 375x812-ru-akimat | 0.23 | 0.26 | 2.50 | 1.43 | 1.43 | 4.04 | 99 | 8216 | 1876 |
| 375x812-kk-resident | 0.23 | 0.28 | 2.53 | 1.45 | 1.45 | 4.11 | 100 | 8319 | 1635 |
| 375x812-kk-akimat | 0.23 | 0.24 | 2.32 | 1.41 | 1.41 | 3.31 | 100 | 8319 | 1836 |

Вид по умолчанию (первое окно):

| Вариант | слоёв видно / всего | значков (с числом) | 3D-табличек | кнопок вне карты | меню | масштаб | кадр |
|---|---|---|---|---|---|---|---|
| 1366x768-ru-resident | 37 / 48 | 6 (6) | 0 | 25 | 3: Акимат · Житель · Для сотрудников | z9.7 | default-1366x768-ru-resident.png |
| 1366x768-ru-akimat | 37 / 48 | 6 (6) | 0 | 24 | 3: Акимат · Житель · Для сотрудников | z9.7 | default-1366x768-ru-akimat.png |
| 1366x768-kk-resident | 37 / 48 | 6 (6) | 0 | 25 | 3: Әкімдік · Тұрғын · Қызметкерлерге | z9.7 | default-1366x768-kk-resident.png |
| 1366x768-kk-akimat | 37 / 48 | 6 (6) | 0 | 24 | 3: Әкімдік · Тұрғын · Қызметкерлерге | z9.7 | default-1366x768-kk-akimat.png |
| 375x812-ru-resident | 37 / 48 | 4 (4) | 0 | 17 | 8: Карта · Мои обращения · Рядом · Идеи · Вопрос акиму · Акимат · Житель · Для сотрудников | z9 | default-375x812-ru-resident.png |
| 375x812-ru-akimat | 37 / 48 | 4 (4) | 0 | 16 | 11: Карта · Картина дня · Обращения · Проекты и идеи · Вопросы жителей · Работы и отключения · QR-таблички · Службы · Акимат | z9 | default-375x812-ru-akimat.png |
| 375x812-kk-resident | 37 / 48 | 4 (4) | 0 | 17 | 8: Карта · Менің өтініштерім · Маңайда · Идеялар · Әкімге сұрақ · Әкімдік · Тұрғын · Қызметкерлерге | z9 | default-375x812-kk-resident.png |
| 375x812-kk-akimat | 37 / 48 | 4 (4) | 0 | 16 | 11: Карта · Күн қорытындысы · Өтініштер · Жобалар мен идеялар · Тұрғындар сұрақтары · Жұмыстар мен өшірулер · QR-тақтайшалар | z9 | default-375x812-kk-akimat.png |

Плавность (кадр/с · p95 мс · кадров > 50 мс) и отклик интерфейса, мс:

| Вариант | сдвиг | полёт 12→15 | отклик |
|---|---|---|---|
| 1366x768-ru-resident | 4 · 283 · 11 | 3 · 333 · 10 | complaint_form: 41, mine: 13, to_akimat: 422, lang_switch: 469 |
| 1366x768-ru-akimat | 4 · 383 · 9 | 3 · 350 · 11 | hot_select: 661, day_kpi: 2, lang_switch: 456 |
| 1366x768-kk-resident | 4 · 283 · 11 | 4 · 317 · 10 | complaint_form: 40, mine: 58, to_akimat: 359, lang_switch: 213 |
| 1366x768-kk-akimat | 4 · 283 · 10 | 3 · 367 · 9 | hot_select: 834, day_kpi: 2, lang_switch: 184 |
| 375x812-ru-resident | 10 · 133 · 25 | 11 · 133 · 24 | complaint_form: 22, mine: 6, to_akimat: 137, lang_switch: 249 |
| 375x812-ru-akimat | 12 · 117 · 23 | 11 · 150 · 21 | hot_select: 580, day_kpi: 9, lang_switch: 355 |
| 375x812-kk-resident | 15 · 100 · 25 | 11 · 133 · 24 | complaint_form: 19, mine: 6, to_akimat: 144, lang_switch: 126 |
| 375x812-kk-akimat | 11 · 117 · 25 | 12 · 150 · 20 | hot_select: 556, day_kpi: 5, lang_switch: 96 |

Карточка места «Хан Шатыр» (правила 3–4 POLISH_WAVE_2):

| Вариант | заголовок | видно, px | содержимое, px | кнопок | главных | главная без прокрутки | «Подробнее» | кадр |
|---|---|---:|---:|---:|---:|---|---:|---|
| 1366x768-ru-resident | Остановка «Хан Шатыр» | 374 | 374 | 3 | 1 (Я тоже) | true | 2 | card-1366x768-ru-resident.jpg |
| 1366x768-ru-akimat | Остановка «Хан Шатыр» | 654 | 653 | 5 | 1 (Взять в работу) | true | 3 | card-1366x768-ru-akimat.jpg |
| 1366x768-kk-resident | «Хан Шатыр» аялдамасы | 395 | 395 | 3 | 1 (Мен де) | true | 2 | card-1366x768-kk-resident.jpg |
| 1366x768-kk-akimat | «Хан Шатыр» аялдамасы | 654 | 675 | 5 | 1 (Жұмысқа алу) | true | 3 | card-1366x768-kk-akimat.jpg |
| 375x812-ru-resident | Остановка «Хан Шатыр» | 417 | 395 | 3 | 1 (Я тоже) | true | 2 | card-375x812-ru-resident.jpg |
| 375x812-ru-akimat | Остановка «Хан Шатыр» | 417 | 675 | 5 | 1 (Взять в работу) | true | 3 | card-375x812-ru-akimat.jpg |
| 375x812-kk-resident | «Хан Шатыр» аялдамасы | 417 | 395 | 3 | 1 (Мен де) | true | 2 | card-375x812-kk-resident.jpg |
| 375x812-kk-akimat | «Хан Шатыр» аялдамасы | 417 | 675 | 5 | 1 (Жұмысқа алу) | true | 3 | card-375x812-kk-akimat.jpg |

API (6 запросов: первый и медиана остальных):

| Запрос | первый, мс | медиана, мс | КБ | статус |
|---|---:|---:|---:|---|
| GET /api/civic/v2/modules | 13 | 3 | 8 | 200 |
| GET /api/civic/v2/heat z12 | 6 | 4 | 55 | 200 |
| GET /api/civic/v2/heat z16 | 12 | 3 | 32 | 200 |
| GET /api/civic/v2/akim/summary | 117 | 3 | 23 | 200 |
| POST /api/civic/v2/classify | 6 | 2 | 0 | 200 |
| POST /api/civic/v2/similar | 3 | 2 | 0 | 200 |
| GET /api/civic/v2/targets | 2 | 2 | 0 | 200 |
| GET /api/civic/v2/proposals | 3 | 3 | 3 | 200 |

Видимые слои стиля по умолчанию (первый вариант каждого вида):

- 1366x768-ru-resident: offline-bg (0), offline-nura-minor (0), offline-nura-street-case (0), offline-nura-street (0), offline-city-major-case (1100), offline-city-major (1100), civic-explore-lines (12), civic-explore-selected (0), civic-r03-approx-fill (6), civic-r03-approx-line (6), civic-r03-area-fill (0), civic-r03-area-line (0), civic-r03-area-line-approx (0), civic-r03-line-casing (1), civic-r03-line (1), civic-r03-line-approx (0), civic-r03-line-core (0), civic-r03-synthetic-outline (1), civic-r03-selected-line (0), civic-r03-point-halo (3), r07-district-fill (12), r07-district-line (12), r07-area-glow (0), r07-area-fill (0), r07-area-line (0), r07-area-approx (0), r07-sel-outline (0), r07-sel-line (0), r07-seg-casing (0), r07-seg (0), r07-seg-dashed (0), r07-obj-halo-lo (0), r07-obj-halo (0), r07-obj-dot (0), civic-r03-point-synthetic (3), civic-r03-point (3), civic-r03-selected-point (0)
- 1366x768-ru-akimat: offline-bg (0), offline-nura-minor (0), offline-nura-street-case (0), offline-nura-street (0), offline-city-major-case (1100), offline-city-major (1100), civic-explore-lines (12), civic-explore-selected (0), civic-r03-approx-fill (6), civic-r03-approx-line (6), civic-r03-area-fill (0), civic-r03-area-line (0), civic-r03-area-line-approx (0), civic-r03-line-casing (1), civic-r03-line (1), civic-r03-line-approx (0), civic-r03-line-core (0), civic-r03-synthetic-outline (1), civic-r03-selected-line (0), civic-r03-point-halo (3), r07-district-fill (12), r07-district-line (12), r07-area-glow (0), r07-area-fill (0), r07-area-line (0), r07-area-approx (0), r07-sel-outline (0), r07-sel-line (0), r07-seg-casing (0), r07-seg (0), r07-seg-dashed (0), r07-obj-halo-lo (0), r07-obj-halo (0), r07-obj-dot (0), civic-r03-point-synthetic (3), civic-r03-point (3), civic-r03-selected-point (0)
