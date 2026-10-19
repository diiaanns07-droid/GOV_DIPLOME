# R10 · эталон карты · 8e67c65f

```
{"root":"<worktree 8e67c65>","sha":"8e67c65f","when":"2026-10-11T20:39:07.868Z","base":"(свой сервер, временная база, CIVIC_DEMO=1)","repeat":3,"sizes":["1366x768","375x812"],"langs":["ru","kk"],"modes":["resident","akimat"],"chromium":"141.0.7390.37","machine":{"cpu":"Intel(R) Xeon(R) Processor @ 2.10GHz","cores":4,"mem_gb":16,"platform":"linux 6.18.44-fc-v114","node":"v22.22.0"}}
```

Загрузка, медиана из 3 окон без кэша, секунды от начала навигации (WebGL программный — сравнивать с прогоном на той же машине):

| Вариант | DOM готов | load | карта загружена | 1-й значок с числом | главная кнопка | карта успокоилась | запросов | КБ | длинные задачи, мс |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 1366x768-ru-resident | 0.19 | 0.21 | 3.83 | 2.76 | 1.42 | 4.36 | 89 | 8272 | 3040 |
| 1366x768-ru-akimat | 0.19 | 0.21 | 3.85 | 2.76 | 2.76 | 4.33 | 89 | 8272 | 3126 |
| 1366x768-kk-resident | 0.18 | 0.20 | 3.79 | 2.76 | 1.41 | 4.33 | 90 | 8330 | 3030 |
| 1366x768-kk-akimat | 0.16 | 0.17 | 3.79 | 2.81 | 2.81 | 4.37 | 90 | 8330 | 3122 |
| 375x812-ru-resident | 0.18 | 0.20 | 2.92 | 2.20 | 1.31 | 3.74 | 89 | 8272 | 2018 |
| 375x812-ru-akimat | 0.18 | 0.20 | 2.89 | 2.18 | 2.18 | 3.74 | 89 | 8272 | 1908 |
| 375x812-kk-resident | 0.17 | 0.18 | 2.92 | 2.04 | 1.19 | 3.76 | 90 | 8330 | 2059 |
| 375x812-kk-akimat | 0.17 | 0.18 | 2.95 | 2.06 | — | 3.61 | 90 | 8330 | 1985 |

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
| 1366x768-ru-resident | 4 · 267 · 10 | 3 · 367 · 9 | complaint_form: 21, mine: 56, to_akimat: 314, lang_switch: 563 |
| 1366x768-ru-akimat | 4 · 250 · 12 | 4 · 333 · 11 | hot_select: 507, day_kpi: 3, lang_switch: 524 |
| 1366x768-kk-resident | 4 · 283 · 11 | 3 · 333 · 10 | complaint_form: 25, mine: 56, to_akimat: 154, lang_switch: 157 |
| 1366x768-kk-akimat | 4 · 283 · 12 | 4 · 333 · 11 | hot_select: 518, day_kpi: 7, lang_switch: 171 |
| 375x812-ru-resident | 15 · 83 · 28 | 11 · 150 · 25 | complaint_form: 22, mine: 55, to_akimat: 119, lang_switch: 382 |
| 375x812-ru-akimat | 16 · 83 · 28 | 12 · 150 · 24 | hot_select: 581, day_kpi: 6, lang_switch: 373 |
| 375x812-kk-resident | 14 · 83 · 30 | 12 · 133 · 24 | complaint_form: 43, mine: 58, to_akimat: 103, lang_switch: 121 |
| 375x812-kk-akimat | 14 · 83 · 31 | 11 · 167 · 20 | hot_select: 652, day_kpi: 3, lang_switch: 113 |

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
| GET /api/civic/v2/modules | 13 | 3 | 4 | 200 |
| GET /api/civic/v2/heat z12 | 10 | 3 | 37 | 200 |
| GET /api/civic/v2/heat z16 | 7 | 2 | 22 | 200 |
| GET /api/civic/v2/akim/summary | 70 | 2 | 11 | 200 |
| POST /api/civic/v2/classify | 7 | 2 | 0 | 200 |
| POST /api/civic/v2/similar | 2 | 2 | 0 | 200 |
| GET /api/civic/v2/targets | 2 | 2 | 0 | 200 |
| GET /api/civic/v2/proposals | 3 | 3 | 3 | 200 |

Видимые слои стиля по умолчанию (первый вариант каждого вида):

- 1366x768-ru-resident: offline-bg (0), offline-nura-minor (0), offline-nura-street-case (0), offline-nura-street (0), offline-city-major-case (928), offline-city-major (928), civic-explore-selected (0), civic-r03-approx-fill (5), civic-r03-approx-line (5), civic-r03-area-fill (0), civic-r03-area-line (0), civic-r03-area-line-approx (0), civic-r03-line-casing (1), civic-r03-line (1), civic-r03-line-approx (0), civic-r03-line-core (0), civic-r03-synthetic-outline (1), civic-r03-selected-line (0), civic-r03-point-halo (3), r07-district-fill (8), r07-district-line (8), r07-area-glow (0), r07-area-fill (0), r07-area-line (0), r07-area-approx (0), r07-sel-outline (0), r07-sel-line (0), r07-seg-casing (0), r07-seg (0), r07-obj-halo-lo (0), r07-obj-halo (0), r07-obj-dot (0), civic-r03-point-synthetic (3), civic-r03-point (3), civic-r03-selected-point (0)
- 1366x768-ru-akimat: offline-bg (0), offline-nura-minor (0), offline-nura-street-case (0), offline-nura-street (0), offline-city-major-case (928), offline-city-major (928), civic-explore-selected (0), civic-r03-approx-fill (5), civic-r03-approx-line (5), civic-r03-area-fill (0), civic-r03-area-line (0), civic-r03-area-line-approx (0), civic-r03-line-casing (1), civic-r03-line (1), civic-r03-line-approx (0), civic-r03-line-core (0), civic-r03-synthetic-outline (1), civic-r03-selected-line (0), civic-r03-point-halo (3), r07-district-fill (8), r07-district-line (8), r07-area-glow (0), r07-area-fill (0), r07-area-line (0), r07-area-approx (0), r07-sel-outline (0), r07-sel-line (0), r07-seg-casing (0), r07-seg (0), r07-obj-halo-lo (0), r07-obj-halo (0), r07-obj-dot (0), civic-r03-point-synthetic (3), civic-r03-point (3), civic-r03-selected-point (0)
