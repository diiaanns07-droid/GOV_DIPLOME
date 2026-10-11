# R10 · эталон карты · 8e67c65

```
{"root":"<worktree 8e67c65>","sha":"8e67c65","when":"2026-10-11T18:07:02.038Z","base":"(свой сервер, временная база, CIVIC_DEMO=1)","repeat":3,"sizes":["1366x768","375x812"],"langs":["ru","kk"],"modes":["resident","akimat"],"chromium":"141.0.7390.37","machine":{"cpu":"Intel(R) Xeon(R) Processor @ 2.10GHz","cores":4,"mem_gb":16,"platform":"linux 6.18.44-fc-v114","node":"v22.22.0"}}
```

Загрузка, медиана из 3 окон без кэша, секунды от начала навигации (WebGL программный — сравнивать с прогоном на той же машине):

| Вариант | DOM готов | load | карта загружена | 1-й значок с числом | главная кнопка | карта успокоилась | запросов | КБ | длинные задачи, мс |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 1366x768-ru-resident | 0.18 | 0.20 | 4.15 | 3.05 | 1.50 | 4.61 | 89 | 8272 | 3388 |
| 1366x768-ru-akimat | 0.20 | 0.22 | 4.06 | 3.13 | 3.13 | 4.67 | 89 | 8272 | 3251 |
| 1366x768-kk-resident | 0.20 | 0.21 | 4.04 | 3.07 | 1.53 | 4.64 | 90 | 8330 | 3259 |
| 1366x768-kk-akimat | 0.21 | 0.23 | 3.82 | 2.84 | 2.84 | 4.41 | 90 | 8330 | 2854 |
| 375x812-ru-resident | 0.19 | 0.20 | 2.96 | 2.22 | 1.28 | 3.79 | 89 | 8272 | 2083 |
| 375x812-ru-akimat | 0.19 | 0.21 | 2.97 | 2.25 | 2.25 | 3.80 | 89 | 8272 | 1980 |
| 375x812-kk-resident | 0.19 | 0.21 | 3.03 | 2.32 | 1.31 | 3.92 | 90 | 8330 | 2060 |
| 375x812-kk-akimat | 0.19 | 0.20 | 3.02 | 2.27 | — | 3.78 | 90 | 8330 | 2016 |

Вид по умолчанию (первое окно):

| Вариант | слоёв видно / всего | значков (с числом) | 3D-табличек | кнопок вне карты | меню | масштаб | кадр |
|---|---|---|---|---|---|---|---|
| 1366x768-ru-resident | 35 / 47 | 6 (6) | 1 | 27 | — | z8.72 | default-1366x768-ru-resident.png |
| 1366x768-ru-akimat | 35 / 47 | 5 (5) | 1 | 26 | — | z8.72 | default-1366x768-ru-akimat.png |
| 1366x768-kk-resident | 35 / 47 | 6 (6) | 1 | 26 | — | z8.72 | default-1366x768-kk-resident.png |
| 1366x768-kk-akimat | 35 / 47 | 5 (5) | 1 | 25 | — | z8.72 | default-1366x768-kk-akimat.png |
| 375x812-ru-resident | 35 / 47 | 6 (6) | 1 | 11 | 5: Карта · Картина дня · Акимат · Житель · Мои обращения | z8.23 | default-375x812-ru-resident.png |
| 375x812-ru-akimat | 35 / 47 | 6 (6) | 1 | 12 | 4: Карта · Картина дня · Акимат · Житель | z8.23 | default-375x812-ru-akimat.png |
| 375x812-kk-resident | 35 / 47 | 6 (6) | 1 | 13 | 5: Карта · Күн қорытындысы · Әкімдік · Тұрғын · Менің өтініштерім | z8.23 | default-375x812-kk-resident.png |
| 375x812-kk-akimat | 35 / 47 | 6 (6) | 1 | 14 | 4: Карта · Күн қорытындысы · Әкімдік · Тұрғын | z8.23 | default-375x812-kk-akimat.png |

Плавность (кадр/с · p95 мс · кадров > 50 мс) и отклик интерфейса, мс:

| Вариант | сдвиг | полёт 12→15 | отклик |
|---|---|---|---|
| 1366x768-ru-resident | 4 · 300 · 11 | 3 · 383 · 9 | complaint_form: 24, mine: 60, to_akimat: 420, lang_switch: 416 |
| 1366x768-ru-akimat | 4 · 267 · 11 | 3 · 417 · 9 | hot_select: 764, day_kpi: 4, lang_switch: 513 |
| 1366x768-kk-resident | 4 · 300 · 11 | 3 · 400 · 10 | complaint_form: 23, mine: 58, to_akimat: 363, lang_switch: 190 |
| 1366x768-kk-akimat | 5 · 267 · 11 | 3 · 417 · 9 | hot_select: 1010, day_kpi: 3, lang_switch: 9 |
| 375x812-ru-resident | 17 · 83 · 28 | 11 · 150 · 26 | complaint_form: 25, mine: 56, to_akimat: 136, lang_switch: 431 |
| 375x812-ru-akimat | 11 · 117 · 27 | 10 · 150 · 23 | hot_select: 563, day_kpi: 7, lang_switch: 441 |
| 375x812-kk-resident | 12 · 117 · 28 | 10 · 183 · 23 | complaint_form: 29, mine: 7, to_akimat: 128, lang_switch: 109 |
| 375x812-kk-akimat | 14 · 83 · 30 | 11 · 133 · 25 | hot_select: 628, day_kpi: 2, lang_switch: 120 |

Карточка места «Хан Шатыр» (правила 3–4 POLISH_WAVE_2):

| Вариант | заголовок | видно, px | содержимое, px | кнопок | главных | главная без прокрутки | «Подробнее» | кадр |
|---|---|---:|---:|---:|---:|---|---:|---|
| 1366x768-ru-resident | Остановка «Хан Шатыр» | 555 | 517 | 3 | 1 (Я тоже) | true | 0 | card-1366x768-ru-resident.jpg |
| 1366x768-ru-akimat | Остановка «Хан Шатыр» | 555 | 624 | 4 | 1 (Взять в работу) | true | 0 | card-1366x768-ru-akimat.jpg |
| 1366x768-kk-resident | «Хан Шатыр» аялдамасы | 555 | 517 | 3 | 1 (Мен де) | true | 0 | card-1366x768-kk-resident.jpg |
| 1366x768-kk-akimat | «Хан Шатыр» аялдамасы | 555 | 624 | 4 | 1 (Жұмысқа алу) | true | 0 | card-1366x768-kk-akimat.jpg |
| 375x812-ru-resident | Остановка «Хан Шатыр» | 334 | 517 | 3 | 1 (Я тоже) | false | 0 | card-375x812-ru-resident.jpg |
| 375x812-ru-akimat | Остановка «Хан Шатыр» | 273 | 702 | 4 | 1 (Взять в работу) | false | 0 | card-375x812-ru-akimat.jpg |
| 375x812-kk-resident | «Хан Шатыр» аялдамасы | 334 | 517 | 3 | 1 (Мен де) | false | 0 | card-375x812-kk-resident.jpg |
| 375x812-kk-akimat | «Хан Шатыр» аялдамасы | 273 | 646 | 4 | 1 (Жұмысқа алу) | false | 0 | card-375x812-kk-akimat.jpg |

API (6 запросов: первый и медиана остальных):

| Запрос | первый, мс | медиана, мс | КБ | статус |
|---|---:|---:|---:|---|
| GET /api/civic/v2/modules | 14 | 2 | 4 | 200 |
| GET /api/civic/v2/heat z12 | 11 | 3 | 37 | 200 |
| GET /api/civic/v2/heat z16 | 9 | 2 | 22 | 200 |
| GET /api/civic/v2/akim/summary | 55 | 2 | 11 | 200 |
| POST /api/civic/v2/classify | 7 | 2 | 0 | 200 |
| POST /api/civic/v2/similar | 3 | 2 | 0 | 200 |
| GET /api/civic/v2/targets | 2 | 2 | 0 | 200 |
| GET /api/civic/v2/proposals | 3 | 3 | 3 | 200 |

Видимые слои стиля по умолчанию (первый вариант каждого вида):

- 1366x768-ru-resident: offline-bg (0), offline-nura-minor (0), offline-nura-street-case (0), offline-nura-street (0), offline-city-major-case (928), offline-city-major (928), civic-explore-selected (0), civic-r03-approx-fill (5), civic-r03-approx-line (5), civic-r03-area-fill (0), civic-r03-area-line (0), civic-r03-area-line-approx (0), civic-r03-line-casing (1), civic-r03-line (1), civic-r03-line-approx (0), civic-r03-line-core (0), civic-r03-synthetic-outline (1), civic-r03-selected-line (0), civic-r03-point-halo (3), r07-district-fill (8), r07-district-line (8), r07-area-glow (0), r07-area-fill (0), r07-area-line (0), r07-area-approx (0), r07-sel-outline (0), r07-sel-line (0), r07-seg-casing (0), r07-seg (0), r07-obj-halo-lo (0), r07-obj-halo (0), r07-obj-dot (0), civic-r03-point-synthetic (3), civic-r03-point (3), civic-r03-selected-point (0)
- 1366x768-ru-akimat: offline-bg (0), offline-nura-minor (0), offline-nura-street-case (0), offline-nura-street (0), offline-city-major-case (928), offline-city-major (928), civic-explore-selected (0), civic-r03-approx-fill (5), civic-r03-approx-line (5), civic-r03-area-fill (0), civic-r03-area-line (0), civic-r03-area-line-approx (0), civic-r03-line-casing (1), civic-r03-line (1), civic-r03-line-approx (0), civic-r03-line-core (0), civic-r03-synthetic-outline (1), civic-r03-selected-line (0), civic-r03-point-halo (3), r07-district-fill (8), r07-district-line (8), r07-area-glow (0), r07-area-fill (0), r07-area-line (0), r07-area-approx (0), r07-sel-outline (0), r07-sel-line (0), r07-seg-casing (0), r07-seg (0), r07-obj-halo-lo (0), r07-obj-halo (0), r07-obj-dot (0), civic-r03-point-synthetic (3), civic-r03-point (3), civic-r03-selected-point (0)
