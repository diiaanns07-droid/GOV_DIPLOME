# R10 · эталон карты · dbf25c05

```
{"root":"/tmp/claude-0/-home-user-GOV-DIPLOME/62d68526-d416-54f0-b206-35e3353bc4a5/scratchpad/builds/pvB","sha":"dbf25c05","when":"2026-10-15T12:58:11.178Z","base":"(свой сервер, временная база, CIVIC_DEMO=1)","repeat":3,"sizes":["1366x768","375x812"],"langs":["ru","kk"],"modes":["resident","akimat"],"chromium":"141.0.7390.37","machine":{"cpu":"Intel(R) Xeon(R) Processor @ 2.80GHz","cores":4,"mem_gb":16,"platform":"linux 6.18.44-fc-v114","node":"v22.22.0"}}
```

Загрузка, медиана из 3 окон без кэша, секунды от начала навигации (WebGL программный — сравнивать с прогоном на той же машине):

| Вариант | DOM готов | load | карта загружена | 1-й значок с числом | главная кнопка | карта успокоилась | запросов | КБ | длинные задачи, мс |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 1366x768-ru-resident | 0.36 | 0.45 | 5.43 | 2.23 | 2.23 | 5.07 | 106 | 9073 | 4445 |
| 1366x768-ru-akimat | 0.37 | 0.43 | 5.95 | 2.40 | — | 5.52 | 107 | 9114 | 4885 |
| 1366x768-kk-resident | 0.38 | 0.40 | 5.93 | 2.48 | 2.48 | 5.47 | 107 | 9187 | 4969 |
| 1366x768-kk-akimat | 0.40 | 0.47 | 6.14 | 2.44 | — | 5.77 | 108 | 9228 | 5406 |
| 375x812-ru-resident | 0.42 | 0.48 | 4.37 | 2.18 | 2.18 | 5.60 | 108 | 9534 | 3101 |
| 375x812-ru-akimat | 0.37 | 0.42 | 4.13 | 2.17 | 2.04 | 4.16 | 106 | 9073 | 3153 |
| 375x812-kk-resident | 0.37 | 0.44 | 4.48 | 2.15 | 2.15 | 4.69 | 109 | 9372 | 3375 |
| 375x812-kk-akimat | 0.41 | 0.46 | 4.57 | 2.28 | 2.28 | 4.58 | 107 | 9187 | 3582 |

Вид по умолчанию (первое окно):

| Вариант | слоёв видно / всего | значков (с числом) | 3D-табличек | кнопок вне карты | меню | масштаб | кадр |
|---|---|---|---|---|---|---|---|
| 1366x768-ru-resident | 37 / 48 | 6 (6) | 0 | 22 | 3: Акимат · Житель · Для сотрудников | z10.37 | default-1366x768-ru-resident.png |
| 1366x768-ru-akimat | 37 / 48 | 6 (6) | 0 | 26 | 3: Акимат · Житель · Для сотрудников | z10.37 | default-1366x768-ru-akimat.png |
| 1366x768-kk-resident | 37 / 48 | 6 (6) | 0 | 22 | 3: Әкімдік · Тұрғын · Қызметкерлерге | z10.37 | default-1366x768-kk-resident.png |
| 1366x768-kk-akimat | 37 / 48 | 6 (6) | 0 | 26 | 3: Әкімдік · Тұрғын · Қызметкерлерге | z10.37 | default-1366x768-kk-akimat.png |
| 375x812-ru-resident | 37 / 48 | 3 (3) | 0 | 15 | 8: Карта · Мои обращения · Рядом · Идеи · Вопрос акиму · Акимат · Житель · Для сотрудников | z9 | default-375x812-ru-resident.png |
| 375x812-ru-akimat | 37 / 48 | 2 (2) | 0 | 20 | 11: Карта · Картина дня · Обращения · Проекты и идеи · Вопросы жителей · QR-таблички · Работы и отключения · Службы · Акимат | z9 | default-375x812-ru-akimat.png |
| 375x812-kk-resident | 37 / 48 | 3 (3) | 0 | 16 | 8: Карта · Менің өтініштерім · Маңайда · Идеялар · Әкімге сұрақ · Әкімдік · Тұрғын · Қызметкерлерге | z9 | default-375x812-kk-resident.png |
| 375x812-kk-akimat | 37 / 48 | 2 (2) | 0 | 21 | 11: Карта · Күн қорытындысы · Өтініштер · Жобалар мен идеялар · Тұрғындар сұрақтары · QR-тақтайшалар · Жұмыстар мен өшірулер | z9 | default-375x812-kk-akimat.png |

Плавность (кадр/с · p95 мс · кадров > 50 мс) и отклик интерфейса, мс:

| Вариант | сдвиг | полёт 12→15 | отклик |
|---|---|---|---|
| 1366x768-ru-resident | 2 · 733 · 6 | 2 · 583 · 7 | complaint_form: 29, mine: 7, to_akimat: 680, lang_switch: 614 |
| 1366x768-ru-akimat | 2 · 817 · 5 | 2 · 567 · 7 | hot_select: —, day_kpi: 31, lang_switch: 671 |
| 1366x768-kk-resident | 2 · 883 · 5 | 2 · 517 · 7 | complaint_form: 30, mine: 9, to_akimat: 743, lang_switch: 345 |
| 1366x768-kk-akimat | 2 · 817 · 6 | 2 · 650 · 6 | hot_select: —, day_kpi: 41, lang_switch: 285 |
| 375x812-ru-resident | 6 · 200 · 17 | 5 · 400 · 12 | complaint_form: 48, mine: 11, to_akimat: 219, lang_switch: 407 |
| 375x812-ru-akimat | 5 · 267 · 13 | 6 · 267 · 16 | hot_select: 599, day_kpi: 160, lang_switch: 425 |
| 375x812-kk-resident | 5 · 217 · 14 | 5 · 283 · 13 | complaint_form: 38, mine: 21, to_akimat: 219, lang_switch: 109 |
| 375x812-kk-akimat | 7 · 183 · 15 | 5 · 283 · 15 | hot_select: 661, day_kpi: 156, lang_switch: 191 |

Карточка места «Хан Шатыр» (правила 3–4 POLISH_WAVE_2):

| Вариант | заголовок | видно, px | содержимое, px | кнопок | главных | главная без прокрутки | «Подробнее» | кадр |
|---|---|---:|---:|---:|---:|---|---:|---|
| 1366x768-ru-resident | Остановка «Хан Шатыр» | 385 | 385 | 4 | 1 (Я тоже) | true | 0 | card-1366x768-ru-resident.jpg |
| 1366x768-ru-akimat | Остановка «Хан Шатыр» | 600 | 532 | 7 | 1 (Отметить исправленным) | true | 0 | card-1366x768-ru-akimat.jpg |
| 1366x768-kk-resident | «Хан Шатыр» аялдамасы | 385 | 385 | 4 | 1 (Мен де) | true | 0 | card-1366x768-kk-resident.jpg |
| 1366x768-kk-akimat | «Хан Шатыр» аялдамасы | 600 | 532 | 7 | 1 (Түзетілді деп белгілеу) | true | 0 | card-1366x768-kk-akimat.jpg |
| 375x812-ru-resident | Остановка «Хан Шатыр» | 417 | 416 | 4 | 1 (Я тоже) | true | 0 | card-375x812-ru-resident.jpg |
| 375x812-ru-akimat | Остановка «Хан Шатыр» | 417 | 563 | 7 | 1 (Отметить исправленным) | true | 0 | card-375x812-ru-akimat.jpg |
| 375x812-kk-resident | «Хан Шатыр» аялдамасы | 417 | 407 | 4 | 1 (Мен де) | true | 0 | card-375x812-kk-resident.jpg |
| 375x812-kk-akimat | «Хан Шатыр» аялдамасы | 417 | 554 | 7 | 1 (Түзетілді деп белгілеу) | true | 0 | card-375x812-kk-akimat.jpg |

API (6 запросов: первый и медиана остальных):

| Запрос | первый, мс | медиана, мс | КБ | статус |
|---|---:|---:|---:|---|
| GET /api/civic/v2/modules | 36 | 6 | 14 | 200 |
| GET /api/civic/v2/heat z12 | 16 | 16 | 171 | 200 |
| GET /api/civic/v2/heat z16 | 44 | 5 | 19 | 200 |
| GET /api/civic/v2/akim/summary | 1717 | 6 | 34 | 200 |
| POST /api/civic/v2/classify | 9 | 4 | 0 | 200 |
| POST /api/civic/v2/similar | 12 | 5 | 0 | 200 |
| GET /api/civic/v2/targets | 3 | 4 | 0 | 200 |
| GET /api/civic/v2/proposals | 9 | 7 | 3 | 200 |

Видимые слои стиля по умолчанию (первый вариант каждого вида):

- 1366x768-ru-resident: offline-bg (0), offline-nura-minor (0), offline-nura-street-case (0), offline-nura-street (0), offline-city-major-case (1244), offline-city-major (1244), civic-explore-lines (18), civic-explore-selected (0), civic-r03-approx-fill (6), civic-r03-approx-line (6), civic-r03-area-fill (0), civic-r03-area-line (0), civic-r03-area-line-approx (0), civic-r03-line-casing (1), civic-r03-line (1), civic-r03-line-approx (0), civic-r03-line-core (0), civic-r03-synthetic-outline (1), civic-r03-selected-line (0), civic-r03-point-halo (3), r07-district-fill (18), r07-district-line (18), r07-area-glow (0), r07-area-fill (0), r07-area-line (0), r07-area-approx (0), r07-sel-outline (0), r07-sel-line (0), r07-seg-casing (0), r07-seg (0), r07-seg-dashed (0), r07-obj-halo-lo (0), r07-obj-halo (0), r07-obj-dot (0), civic-r03-point-synthetic (3), civic-r03-point (3), civic-r03-selected-point (0)
- 1366x768-ru-akimat: offline-bg (0), offline-nura-minor (0), offline-nura-street-case (0), offline-nura-street (0), offline-city-major-case (1236), offline-city-major (1236), civic-explore-lines (16), civic-explore-selected (0), civic-r03-approx-fill (6), civic-r03-approx-line (6), civic-r03-area-fill (0), civic-r03-area-line (0), civic-r03-area-line-approx (0), civic-r03-line-casing (1), civic-r03-line (1), civic-r03-line-approx (0), civic-r03-line-core (0), civic-r03-synthetic-outline (1), civic-r03-selected-line (0), civic-r03-point-halo (3), r07-district-fill (16), r07-district-line (16), r07-area-glow (0), r07-area-fill (0), r07-area-line (0), r07-area-approx (0), r07-sel-outline (0), r07-sel-line (0), r07-seg-casing (0), r07-seg (0), r07-seg-dashed (0), r07-obj-halo-lo (0), r07-obj-halo (0), r07-obj-dot (0), civic-r03-point-synthetic (3), civic-r03-point (3), civic-r03-selected-point (0)
