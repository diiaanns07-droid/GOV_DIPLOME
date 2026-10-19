# R10 · эталон карты · 0f5101a3

```
{"root":"/home/user/bf2s4","sha":"0f5101a3","when":"2026-10-12T04:04:49.711Z","base":"(свой сервер, временная база, CIVIC_DEMO=1)","repeat":3,"sizes":["1366x768","375x812"],"langs":["ru","kk"],"modes":["resident","akimat"],"chromium":"141.0.7390.37","machine":{"cpu":"Intel(R) Xeon(R) Processor @ 2.10GHz","cores":4,"mem_gb":16,"platform":"linux 6.18.44-fc-v114","node":"v22.22.0"}}
```

Загрузка, медиана из 3 окон без кэша, секунды от начала навигации (WebGL программный — сравнивать с прогоном на той же машине):

| Вариант | DOM готов | load | карта загружена | 1-й значок с числом | главная кнопка | карта успокоилась | запросов | КБ | длинные задачи, мс |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 1366x768-ru-resident | 0.18 | 0.19 | 3.58 | 2.64 | 1.31 | 3.73 | 99 | 8667 | 3045 |
| 1366x768-ru-akimat | 0.16 | 0.19 | 3.43 | 2.59 | 2.59 | 3.63 | 99 | 8667 | 3059 |
| 1366x768-kk-resident | 0.19 | 0.19 | 3.51 | 2.73 | 1.34 | 3.73 | 100 | 8756 | 3143 |
| 1366x768-kk-akimat | 0.16 | 0.17 | 3.40 | 2.61 | 2.61 | 3.60 | 100 | 8756 | 2890 |
| 375x812-ru-resident | 0.17 | 0.18 | 2.73 | 2.08 | 1.22 | 3.04 | 99 | 8667 | 1798 |
| 375x812-ru-akimat | 0.17 | 0.18 | 2.64 | 2.00 | — | 3.01 | 99 | 8667 | 1887 |
| 375x812-kk-resident | 0.21 | 0.22 | 2.71 | 2.01 | 1.18 | 3.08 | 100 | 8756 | 1790 |
| 375x812-kk-akimat | 0.20 | 0.21 | 2.79 | 2.00 | — | 2.98 | 100 | 8756 | 2091 |

Вид по умолчанию (первое окно):

| Вариант | слоёв видно / всего | значков (с числом) | 3D-табличек | кнопок вне карты | меню | масштаб | кадр |
|---|---|---|---|---|---|---|---|
| 1366x768-ru-resident | 36 / 47 | 6 (6) | 0 | 27 | — | z10.25 | default-1366x768-ru-resident.png |
| 1366x768-ru-akimat | 36 / 47 | 6 (6) | 0 | 27 | — | z10.25 | default-1366x768-ru-akimat.png |
| 1366x768-kk-resident | 36 / 47 | 6 (6) | 0 | 26 | — | z10.25 | default-1366x768-kk-resident.png |
| 1366x768-kk-akimat | 36 / 47 | 6 (6) | 0 | 26 | — | z10.25 | default-1366x768-kk-akimat.png |
| 375x812-ru-resident | 36 / 47 | 6 (6) | 0 | 15 | 5: Карта · Мои обращения · Рядом · Акимат · Житель | z9 | default-375x812-ru-resident.png |
| 375x812-ru-akimat | 36 / 47 | 6 (6) | 0 | 12 | 6: Карта · Картина дня · Обращения · Ещё · Акимат · Житель | z9 | default-375x812-ru-akimat.png |
| 375x812-kk-resident | 36 / 47 | 6 (6) | 0 | 11 | 5: Карта · Менің өтініштерім · Маңайда · Әкімдік · Тұрғын | z9 | default-375x812-kk-resident.png |
| 375x812-kk-akimat | 36 / 47 | 6 (6) | 0 | 11 | 6: Карта · Күн қорытындысы · Өтініштер · Тағы · Әкімдік · Тұрғын | z9 | default-375x812-kk-akimat.png |

Плавность (кадр/с · p95 мс · кадров > 50 мс) и отклик интерфейса, мс:

| Вариант | сдвиг | полёт 12→15 | отклик |
|---|---|---|---|
| 1366x768-ru-resident | 4 · 300 · 11 | 4 · 300 · 11 | complaint_form: 20, mine: 58, to_akimat: 338, lang_switch: 505 |
| 1366x768-ru-akimat | 4 · 283 · 11 | 4 · 383 · 11 | hot_select: 597, day_kpi: 5, lang_switch: 421 |
| 1366x768-kk-resident | 4 · 250 · 12 | 4 · 367 · 11 | complaint_form: 30, mine: 56, to_akimat: 281, lang_switch: 132 |
| 1366x768-kk-akimat | 5 · 233 · 12 | 4 · 333 · 12 | hot_select: 961, day_kpi: 10, lang_switch: 183 |
| 375x812-ru-resident | 14 · 100 · 30 | 14 · 117 · 20 | complaint_form: 24, mine: 56, to_akimat: 104, lang_switch: 356 |
| 375x812-ru-akimat | 13 · 100 · 31 | 12 · 150 · 21 | hot_select: 580, day_kpi: 2, lang_switch: 309 |
| 375x812-kk-resident | 14 · 83 · 30 | 11 · 133 · 25 | complaint_form: 18, mine: 57, to_akimat: 97, lang_switch: 93 |
| 375x812-kk-akimat | 14 · 100 · 29 | 12 · 167 · 22 | hot_select: 478, day_kpi: 4, lang_switch: 95 |

Карточка места «Хан Шатыр» (правила 3–4 POLISH_WAVE_2):

| Вариант | заголовок | видно, px | содержимое, px | кнопок | главных | главная без прокрутки | «Подробнее» | кадр |
|---|---|---:|---:|---:|---:|---|---:|---|
| 1366x768-ru-resident | Остановка «Хан Шатыр» | 551 | 517 | 3 | 1 (Я тоже) | true | 0 | card-1366x768-ru-resident.jpg |
| 1366x768-ru-akimat | Остановка «Хан Шатыр» | 551 | 686 | 5 | 1 (Взять в работу) | true | 0 | card-1366x768-ru-akimat.jpg |
| 1366x768-kk-resident | «Хан Шатыр» аялдамасы | 551 | 517 | 3 | 1 (Мен де) | true | 0 | card-1366x768-kk-resident.jpg |
| 1366x768-kk-akimat | «Хан Шатыр» аялдамасы | 551 | 686 | 5 | 1 (Жұмысқа алу) | true | 0 | card-1366x768-kk-akimat.jpg |
| 375x812-ru-resident | карточка не открылась ||||||||
| 375x812-ru-akimat | карточка не открылась ||||||||
| 375x812-kk-resident | карточка не открылась ||||||||
| 375x812-kk-akimat | карточка не открылась ||||||||

API (6 запросов: первый и медиана остальных):

| Запрос | первый, мс | медиана, мс | КБ | статус |
|---|---:|---:|---:|---|
| GET /api/civic/v2/modules | 12 | 5 | 6 | 200 |
| GET /api/civic/v2/heat z12 | 5 | 4 | 37 | 200 |
| GET /api/civic/v2/heat z16 | 8 | 3 | 22 | 200 |
| GET /api/civic/v2/akim/summary | 3 | 3 | 21 | 200 |
| POST /api/civic/v2/classify | 5 | 2 | 0 | 200 |
| POST /api/civic/v2/similar | 3 | 2 | 0 | 200 |
| GET /api/civic/v2/targets | 2 | 2 | 0 | 200 |
| GET /api/civic/v2/proposals | 3 | 3 | 3 | 200 |

Видимые слои стиля по умолчанию (первый вариант каждого вида):

- 1366x768-ru-resident: offline-bg (0), offline-nura-minor (0), offline-nura-street-case (0), offline-nura-street (0), offline-city-major-case (1254), offline-city-major (1254), civic-explore-lines (18), civic-explore-selected (0), civic-r03-approx-fill (6), civic-r03-approx-line (6), civic-r03-area-fill (0), civic-r03-area-line (0), civic-r03-area-line-approx (0), civic-r03-line-casing (1), civic-r03-line (1), civic-r03-line-approx (0), civic-r03-line-core (0), civic-r03-synthetic-outline (1), civic-r03-selected-line (0), civic-r03-point-halo (3), r07-district-fill (18), r07-district-line (18), r07-area-glow (0), r07-area-fill (0), r07-area-line (0), r07-area-approx (0), r07-sel-outline (0), r07-sel-line (0), r07-seg-casing (0), r07-seg (0), r07-obj-halo-lo (0), r07-obj-halo (0), r07-obj-dot (0), civic-r03-point-synthetic (3), civic-r03-point (3), civic-r03-selected-point (0)
- 1366x768-ru-akimat: offline-bg (0), offline-nura-minor (0), offline-nura-street-case (0), offline-nura-street (0), offline-city-major-case (1254), offline-city-major (1254), civic-explore-lines (18), civic-explore-selected (0), civic-r03-approx-fill (6), civic-r03-approx-line (6), civic-r03-area-fill (0), civic-r03-area-line (0), civic-r03-area-line-approx (0), civic-r03-line-casing (1), civic-r03-line (1), civic-r03-line-approx (0), civic-r03-line-core (0), civic-r03-synthetic-outline (1), civic-r03-selected-line (0), civic-r03-point-halo (3), r07-district-fill (18), r07-district-line (18), r07-area-glow (0), r07-area-fill (0), r07-area-line (0), r07-area-approx (0), r07-sel-outline (0), r07-sel-line (0), r07-seg-casing (0), r07-seg (0), r07-obj-halo-lo (0), r07-obj-halo (0), r07-obj-dot (0), civic-r03-point-synthetic (3), civic-r03-point (3), civic-r03-selected-point (0)
