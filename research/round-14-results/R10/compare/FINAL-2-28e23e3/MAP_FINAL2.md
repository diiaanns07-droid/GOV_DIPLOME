# R10 · эталон карты · 28e23e3d

```
{"root":"<worktree 28e23e3>","sha":"28e23e3d","when":"2026-10-11T21:03:25.171Z","base":"(свой сервер, временная база, CIVIC_DEMO=1)","repeat":3,"sizes":["1366x768","375x812"],"langs":["ru","kk"],"modes":["resident","akimat"],"chromium":"141.0.7390.37","machine":{"cpu":"Intel(R) Xeon(R) Processor @ 2.10GHz","cores":4,"mem_gb":16,"platform":"linux 6.18.44-fc-v114","node":"v22.22.0"}}
```

Загрузка, медиана из 3 окон без кэша, секунды от начала навигации (WebGL программный — сравнивать с прогоном на той же машине):

| Вариант | DOM готов | load | карта загружена | 1-й значок с числом | главная кнопка | карта успокоилась | запросов | КБ | длинные задачи, мс |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 1366x768-ru-resident | 0.20 | 0.21 | 3.85 | 2.90 | 1.47 | 4.09 | 97 | 8633 | 3428 |
| 1366x768-ru-akimat | 0.21 | 0.23 | 3.83 | 2.77 | 2.77 | 4.08 | 97 | 8633 | 3343 |
| 1366x768-kk-resident | 0.21 | 0.22 | 3.96 | 2.93 | 1.46 | 4.13 | 98 | 8721 | 3448 |
| 1366x768-kk-akimat | 0.18 | 0.20 | 4.08 | 2.89 | 2.89 | 4.32 | 98 | 8721 | 3553 |
| 375x812-ru-resident | 0.20 | 0.22 | 2.97 | 2.19 | 1.23 | 3.19 | 97 | 8633 | 2323 |
| 375x812-ru-akimat | 0.21 | 0.23 | 2.95 | 2.24 | — | 3.18 | 97 | 8633 | 2166 |
| 375x812-kk-resident | 0.19 | 0.20 | 3.02 | 2.26 | 1.25 | 3.13 | 98 | 8721 | 2216 |
| 375x812-kk-akimat | 0.20 | 0.20 | 2.88 | 2.17 | — | 3.15 | 98 | 8721 | 2049 |

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
| 1366x768-ru-resident | 3 · 350 · 9 | 4 · 317 · 11 | complaint_form: 25, mine: 56, to_akimat: 386, lang_switch: 482 |
| 1366x768-ru-akimat | 5 · 233 · 11 | 4 · 300 · 11 | hot_select: 729, day_kpi: 3, lang_switch: 472 |
| 1366x768-kk-resident | 4 · 317 · 10 | 4 · 333 · 11 | complaint_form: 155, mine: 60, to_akimat: 328, lang_switch: 195 |
| 1366x768-kk-akimat | 4 · 267 · 11 | 3 · 367 · 10 | hot_select: 611, day_kpi: 4, lang_switch: 3 |
| 375x812-ru-resident | 11 · 117 · 27 | 10 · 150 · 25 | complaint_form: 21, mine: 55, to_akimat: 105, lang_switch: 394 |
| 375x812-ru-akimat | 13 · 100 · 30 | 13 · 133 · 22 | hot_select: 553, day_kpi: 8, lang_switch: 453 |
| 375x812-kk-resident | 12 · 100 · 29 | 12 · 133 · 22 | complaint_form: 21, mine: 55, to_akimat: 97, lang_switch: 98 |
| 375x812-kk-akimat | 14 · 83 · 28 | 12 · 150 · 21 | hot_select: 523, day_kpi: 3, lang_switch: 110 |

Карточка места «Хан Шатыр» (правила 3–4 POLISH_WAVE_2):

| Вариант | заголовок | видно, px | содержимое, px | кнопок | главных | главная без прокрутки | «Подробнее» | кадр |
|---|---|---:|---:|---:|---:|---|---:|---|
| 1366x768-ru-resident | Остановка «Хан Шатыр» | 551 | 517 | 3 | 1 (Я тоже) | true | 0 | card-1366x768-ru-resident.jpg |
| 1366x768-ru-akimat | Остановка «Хан Шатыр» | 551 | 624 | 4 | 1 (Взять в работу) | true | 0 | card-1366x768-ru-akimat.jpg |
| 1366x768-kk-resident | «Хан Шатыр» аялдамасы | 551 | 517 | 3 | 1 (Мен де) | true | 0 | card-1366x768-kk-resident.jpg |
| 1366x768-kk-akimat | «Хан Шатыр» аялдамасы | 551 | 624 | 4 | 1 (Жұмысқа алу) | true | 0 | card-1366x768-kk-akimat.jpg |
| 375x812-ru-resident | карточка не открылась ||||||||
| 375x812-ru-akimat | карточка не открылась ||||||||
| 375x812-kk-resident | карточка не открылась ||||||||
| 375x812-kk-akimat | карточка не открылась ||||||||

API (6 запросов: первый и медиана остальных):

| Запрос | первый, мс | медиана, мс | КБ | статус |
|---|---:|---:|---:|---|
| GET /api/civic/v2/modules | 16 | 2 | 6 | 200 |
| GET /api/civic/v2/heat z12 | 4 | 4 | 37 | 200 |
| GET /api/civic/v2/heat z16 | 8 | 3 | 22 | 200 |
| GET /api/civic/v2/akim/summary | 3 | 3 | 21 | 200 |
| POST /api/civic/v2/classify | 5 | 2 | 0 | 200 |
| POST /api/civic/v2/similar | 2 | 2 | 0 | 200 |
| GET /api/civic/v2/targets | 2 | 2 | 0 | 200 |
| GET /api/civic/v2/proposals | 3 | 3 | 3 | 200 |

Видимые слои стиля по умолчанию (первый вариант каждого вида):

- 1366x768-ru-resident: offline-bg (0), offline-nura-minor (0), offline-nura-street-case (0), offline-nura-street (0), offline-city-major-case (1254), offline-city-major (1254), civic-explore-lines (18), civic-explore-selected (0), civic-r03-approx-fill (6), civic-r03-approx-line (6), civic-r03-area-fill (0), civic-r03-area-line (0), civic-r03-area-line-approx (0), civic-r03-line-casing (1), civic-r03-line (1), civic-r03-line-approx (0), civic-r03-line-core (0), civic-r03-synthetic-outline (1), civic-r03-selected-line (0), civic-r03-point-halo (3), r07-district-fill (18), r07-district-line (18), r07-area-glow (0), r07-area-fill (0), r07-area-line (0), r07-area-approx (0), r07-sel-outline (0), r07-sel-line (0), r07-seg-casing (0), r07-seg (0), r07-obj-halo-lo (0), r07-obj-halo (0), r07-obj-dot (0), civic-r03-point-synthetic (3), civic-r03-point (3), civic-r03-selected-point (0)
- 1366x768-ru-akimat: offline-bg (0), offline-nura-minor (0), offline-nura-street-case (0), offline-nura-street (0), offline-city-major-case (1254), offline-city-major (1254), civic-explore-lines (18), civic-explore-selected (0), civic-r03-approx-fill (6), civic-r03-approx-line (6), civic-r03-area-fill (0), civic-r03-area-line (0), civic-r03-area-line-approx (0), civic-r03-line-casing (1), civic-r03-line (1), civic-r03-line-approx (0), civic-r03-line-core (0), civic-r03-synthetic-outline (1), civic-r03-selected-line (0), civic-r03-point-halo (3), r07-district-fill (18), r07-district-line (18), r07-area-glow (0), r07-area-fill (0), r07-area-line (0), r07-area-approx (0), r07-sel-outline (0), r07-sel-line (0), r07-seg-casing (0), r07-seg (0), r07-obj-halo-lo (0), r07-obj-halo (0), r07-obj-dot (0), civic-r03-point-synthetic (3), civic-r03-point (3), civic-r03-selected-point (0)
