# R10 · эталон карты · 12c925ad

```
{"root":"/home/user/bf2f","sha":"12c925ad","when":"2026-10-12T05:12:02.482Z","base":"(свой сервер, временная база, CIVIC_DEMO=1)","repeat":3,"sizes":["1366x768","375x812"],"langs":["ru","kk"],"modes":["resident","akimat"],"chromium":"141.0.7390.37","machine":{"cpu":"Intel(R) Xeon(R) Processor @ 2.10GHz","cores":4,"mem_gb":16,"platform":"linux 6.18.44-fc-v114","node":"v22.22.0"}}
```

Загрузка, медиана из 3 окон без кэша, секунды от начала навигации (WebGL программный — сравнивать с прогоном на той же машине):

| Вариант | DOM готов | load | карта загружена | 1-й значок с числом | главная кнопка | карта успокоилась | запросов | КБ | длинные задачи, мс |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 1366x768-ru-resident | 0.21 | 0.23 | 3.51 | 2.85 | 1.39 | 3.51 | 94 | 7950 | 2698 |
| 1366x768-ru-akimat | 0.18 | 0.20 | 3.27 | 2.69 | 2.69 | 3.37 | 94 | 7950 | 2835 |
| 1366x768-kk-resident | 0.17 | 0.19 | 3.49 | 2.66 | 1.31 | 3.41 | 95 | 8040 | 2721 |
| 1366x768-kk-akimat | 0.17 | 0.17 | 2.54 | 2.81 | 2.81 | 3.47 | 95 | 8040 | 2819 |
| 375x812-ru-resident | 0.17 | 0.19 | 2.20 | 2.09 | 1.08 | 2.92 | 94 | 7950 | 1696 |
| 375x812-ru-akimat | 0.16 | 0.18 | 2.35 | 1.91 | — | 2.97 | 94 | 7950 | 1321 |
| 375x812-kk-resident | 0.16 | 0.18 | 2.36 | 1.98 | 1.12 | 2.98 | 95 | 8040 | 1402 |
| 375x812-kk-akimat | 0.18 | 0.20 | 2.52 | 2.16 | — | 3.09 | 95 | 8040 | 1671 |

Вид по умолчанию (первое окно):

| Вариант | слоёв видно / всего | значков (с числом) | 3D-табличек | кнопок вне карты | меню | масштаб | кадр |
|---|---|---|---|---|---|---|---|
| 1366x768-ru-resident | 37 / 48 | 6 (6) | 0 | 27 | — | z10.25 | default-1366x768-ru-resident.png |
| 1366x768-ru-akimat | 37 / 48 | 6 (6) | 0 | 27 | — | z10.25 | default-1366x768-ru-akimat.png |
| 1366x768-kk-resident | 37 / 48 | 6 (6) | 0 | 26 | — | z10.25 | default-1366x768-kk-resident.png |
| 1366x768-kk-akimat | 37 / 48 | 6 (6) | 0 | 26 | — | z10.25 | default-1366x768-kk-akimat.png |
| 375x812-ru-resident | 37 / 48 | 6 (6) | 0 | 15 | 5: Карта · Мои обращения · Рядом · Акимат · Житель | z9 | default-375x812-ru-resident.png |
| 375x812-ru-akimat | 37 / 48 | 6 (6) | 0 | 12 | 6: Карта · Картина дня · Обращения · Ещё · Акимат · Житель | z9 | default-375x812-ru-akimat.png |
| 375x812-kk-resident | 37 / 48 | 6 (6) | 0 | 11 | 5: Карта · Менің өтініштерім · Маңайда · Әкімдік · Тұрғын | z9 | default-375x812-kk-resident.png |
| 375x812-kk-akimat | 37 / 48 | 6 (6) | 0 | 11 | 6: Карта · Күн қорытындысы · Өтініштер · Тағы · Әкімдік · Тұрғын | z9 | default-375x812-kk-akimat.png |

Плавность (кадр/с · p95 мс · кадров > 50 мс) и отклик интерфейса, мс:

| Вариант | сдвиг | полёт 12→15 | отклик |
|---|---|---|---|
| 1366x768-ru-resident | 4 · 300 · 10 | 3 · 350 · 11 | complaint_form: 22, mine: 56, to_akimat: 341, lang_switch: 469 |
| 1366x768-ru-akimat | 4 · 283 · 12 | 4 · 317 · 12 | hot_select: 640, day_kpi: 3, lang_switch: 571 |
| 1366x768-kk-resident | 4 · 267 · 12 | 4 · 283 · 11 | complaint_form: 19, mine: 55, to_akimat: 290, lang_switch: 127 |
| 1366x768-kk-akimat | 5 · 250 · 13 | 3 · 350 · 10 | hot_select: 628, day_kpi: 4, lang_switch: 155 |
| 375x812-ru-resident | 13 · 117 · 27 | 11 · 133 · 26 | complaint_form: 19, mine: 55, to_akimat: 126, lang_switch: 333 |
| 375x812-ru-akimat | 14 · 100 · 31 | 14 · 133 · 15 | hot_select: 596, day_kpi: 4, lang_switch: 426 |
| 375x812-kk-resident | 11 · 117 · 28 | 13 · 117 · 19 | complaint_form: 18, mine: 54, to_akimat: 85, lang_switch: 78 |
| 375x812-kk-akimat | 15 · 100 · 31 | 14 · 133 · 20 | hot_select: 534, day_kpi: 3, lang_switch: 81 |

Карточка места «Хан Шатыр» (правила 3–4 POLISH_WAVE_2):

| Вариант | заголовок | видно, px | содержимое, px | кнопок | главных | главная без прокрутки | «Подробнее» | кадр |
|---|---|---:|---:|---:|---:|---|---:|---|
| 1366x768-ru-resident | Остановка «Хан Шатыр» | 551 | 517 | 3 | 1 (Я тоже) | true | 0 | card-1366x768-ru-resident.jpg |
| 1366x768-ru-akimat | Остановка «Хан Шатыр» | 551 | 722 | 5 | 1 (Взять в работу) | true | 0 | card-1366x768-ru-akimat.jpg |
| 1366x768-kk-resident | «Хан Шатыр» аялдамасы | 551 | 517 | 3 | 1 (Мен де) | true | 0 | card-1366x768-kk-resident.jpg |
| 1366x768-kk-akimat | «Хан Шатыр» аялдамасы | 551 | 722 | 5 | 1 (Жұмысқа алу) | true | 0 | card-1366x768-kk-akimat.jpg |
| 375x812-ru-resident | Остановка «Хан Шатыр» | 415 | 517 | 3 | 1 (Я тоже) | true | 0 | card-375x812-ru-resident.jpg |
| 375x812-ru-akimat | Остановка «Хан Шатыр» | 415 | 800 | 5 | 1 (Взять в работу) | true | 0 | card-375x812-ru-akimat.jpg |
| 375x812-kk-resident | «Хан Шатыр» аялдамасы | 415 | 517 | 3 | 1 (Мен де) | true | 0 | card-375x812-kk-resident.jpg |
| 375x812-kk-akimat | «Хан Шатыр» аялдамасы | 415 | 744 | 5 | 1 (Жұмысқа алу) | true | 0 | card-375x812-kk-akimat.jpg |

API (6 запросов: первый и медиана остальных):

| Запрос | первый, мс | медиана, мс | КБ | статус |
|---|---:|---:|---:|---|
| GET /api/civic/v2/modules | 15 | 4 | 6 | 200 |
| GET /api/civic/v2/heat z12 | 6 | 6 | 54 | 200 |
| GET /api/civic/v2/heat z16 | 11 | 3 | 32 | 200 |
| GET /api/civic/v2/akim/summary | 163 | 3 | 23 | 200 |
| POST /api/civic/v2/classify | 6 | 2 | 0 | 200 |
| POST /api/civic/v2/similar | 3 | 2 | 0 | 200 |
| GET /api/civic/v2/targets | 2 | 2 | 0 | 200 |
| GET /api/civic/v2/proposals | 3 | 3 | 3 | 200 |

Видимые слои стиля по умолчанию (первый вариант каждого вида):

- 1366x768-ru-resident: offline-bg (0), offline-nura-minor (0), offline-nura-street-case (0), offline-nura-street (0), offline-city-major-case (1254), offline-city-major (1254), civic-explore-lines (18), civic-explore-selected (0), civic-r03-approx-fill (6), civic-r03-approx-line (6), civic-r03-area-fill (0), civic-r03-area-line (0), civic-r03-area-line-approx (0), civic-r03-line-casing (1), civic-r03-line (1), civic-r03-line-approx (0), civic-r03-line-core (0), civic-r03-synthetic-outline (1), civic-r03-selected-line (0), civic-r03-point-halo (3), r07-district-fill (18), r07-district-line (18), r07-area-glow (0), r07-area-fill (0), r07-area-line (0), r07-area-approx (0), r07-sel-outline (0), r07-sel-line (0), r07-seg-casing (0), r07-seg (0), r07-seg-dashed (0), r07-obj-halo-lo (0), r07-obj-halo (0), r07-obj-dot (0), civic-r03-point-synthetic (3), civic-r03-point (3), civic-r03-selected-point (0)
- 1366x768-ru-akimat: offline-bg (0), offline-nura-minor (0), offline-nura-street-case (0), offline-nura-street (0), offline-city-major-case (1254), offline-city-major (1254), civic-explore-lines (18), civic-explore-selected (0), civic-r03-approx-fill (6), civic-r03-approx-line (6), civic-r03-area-fill (0), civic-r03-area-line (0), civic-r03-area-line-approx (0), civic-r03-line-casing (1), civic-r03-line (1), civic-r03-line-approx (0), civic-r03-line-core (0), civic-r03-synthetic-outline (1), civic-r03-selected-line (0), civic-r03-point-halo (3), r07-district-fill (18), r07-district-line (18), r07-area-glow (0), r07-area-fill (0), r07-area-line (0), r07-area-approx (0), r07-sel-outline (0), r07-sel-line (0), r07-seg-casing (0), r07-seg (0), r07-seg-dashed (0), r07-obj-halo-lo (0), r07-obj-halo (0), r07-obj-dot (0), civic-r03-point-synthetic (3), civic-r03-point (3), civic-r03-selected-point (0)
