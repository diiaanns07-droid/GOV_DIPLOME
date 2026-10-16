# R10 · эталон карты · 83c8aa58

```
{"root":"/tmp/claude-0/-home-user-GOV-DIPLOME/62d68526-d416-54f0-b206-35e3353bc4a5/scratchpad/builds/r01-b6-83c8aa58","sha":"83c8aa58","when":"2026-10-16T20:51:22.859Z","base":"(свой сервер, временная база, CIVIC_DEMO=1)","repeat":3,"sizes":["1366x768","375x812"],"langs":["ru","kk"],"modes":["resident","akimat"],"chromium":"141.0.7390.37","machine":{"cpu":"Intel(R) Xeon(R) Processor @ 2.10GHz","cores":4,"mem_gb":16,"platform":"linux 6.18.44-fc-v139","node":"v22.22.0"}}
```

Загрузка, медиана из 3 окон без кэша, секунды от начала навигации (WebGL программный — сравнивать с прогоном на той же машине):

| Вариант | DOM готов | load | карта загружена | 1-й значок с числом | главная кнопка | карта успокоилась | запросов | КБ | длинные задачи, мс |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 1366x768-ru-resident | 0.30 | 0.34 | 2.44 | 1.61 | 1.61 | 4.00 | 134 | 10591 | 1626 |
| 1366x768-ru-akimat | 0.28 | 0.32 | 2.45 | 1.47 | — | 4.00 | 133 | 10633 | 1613 |
| 1366x768-kk-resident | 0.28 | 0.33 | 2.48 | 1.54 | 1.54 | 4.04 | 135 | 10797 | 1614 |
| 1366x768-kk-akimat | 0.31 | 0.34 | 2.46 | 1.68 | — | 3.97 | 134 | 10839 | 1653 |
| 375x812-ru-resident | 0.28 | 0.32 | 1.95 | 1.45 | 1.45 | 3.52 | 133 | 10775 | 1037 |
| 375x812-ru-akimat | 0.28 | 0.32 | 1.85 | 1.41 | 1.42 | 3.38 | 132 | 10590 | 1013 |
| 375x812-kk-resident | 0.27 | 0.29 | 1.86 | 1.33 | 1.33 | 3.40 | 134 | 10982 | 975 |
| 375x812-kk-akimat | 0.29 | 0.33 | 1.92 | 1.42 | 1.42 | 3.48 | 133 | 10796 | 956 |

Вид по умолчанию (первое окно):

| Вариант | слоёв видно / всего | значков (с числом) | 3D-табличек | кнопок вне карты | меню | масштаб | кадр |
|---|---|---|---|---|---|---|---|
| 1366x768-ru-resident | 40 / 51 | 6 (6) | 0 | 24 | 3: Акимат · Житель · Для сотрудников | z10.37 | default-1366x768-ru-resident.png |
| 1366x768-ru-akimat | 40 / 51 | 6 (6) | 0 | 27 | 3: Акимат · Житель · Для сотрудников | z10.37 | default-1366x768-ru-akimat.png |
| 1366x768-kk-resident | 40 / 51 | 6 (6) | 0 | 24 | 3: Әкімдік · Тұрғын · Қызметкерлерге | z10.37 | default-1366x768-kk-resident.png |
| 1366x768-kk-akimat | 40 / 51 | 6 (6) | 0 | 27 | 3: Әкімдік · Тұрғын · Қызметкерлерге | z10.37 | default-1366x768-kk-akimat.png |
| 375x812-ru-resident | 40 / 51 | 3 (3) | 0 | 17 | 10: Уведомления · Карта · Мои обращения · Мой двор · Идеи · Сделаем вместе · Вопросы и встречи · Акимат · Житель · Для сотру | z9 | default-375x812-ru-resident.png |
| 375x812-ru-akimat | 40 / 51 | 2 (2) | 0 | 22 | 14: Карта · Картина дня · Обращения · Ведомства · Проекты и идеи · Сделаем вместе · Вопросы и встречи · Разбор обращений · С | z9 | default-375x812-ru-akimat.png |
| 375x812-kk-resident | 40 / 51 | 3 (3) | 0 | 17 | 10: Хабарламалар · Карта · Менің өтініштерім · Аулам · Идеялар · Бірге жасайық · Сұрақтар мен кездесулер · Әкімдік · Тұрғын  | z9 | default-375x812-kk-resident.png |
| 375x812-kk-akimat | 40 / 51 | 2 (2) | 0 | 22 | 14: Карта · Күн қорытындысы · Өтініштер · Ведомстволар · Жобалар мен идеялар · Бірге жасайық · Сұрақтар мен кездесулер · Өті | z9 | default-375x812-kk-akimat.png |

Плавность (кадр/с · p95 мс · кадров > 50 мс) и отклик интерфейса, мс:

| Вариант | сдвиг | полёт 12→15 | отклик |
|---|---|---|---|
| 1366x768-ru-resident | 3 · 350 · 8 | 4 · 300 · 10 | complaint_form: 22, mine: 6, to_akimat: 343, lang_switch: 410 |
| 1366x768-ru-akimat | 4 · 283 · 11 | 4 · 350 · 10 | hot_select: —, day_kpi: 82, lang_switch: 364 |
| 1366x768-kk-resident | 3 · 383 · 8 | 3 · 350 · 9 | complaint_form: 39, mine: 5, to_akimat: 333, lang_switch: 169 |
| 1366x768-kk-akimat | 4 · 283 · 11 | 4 · 300 · 12 | hot_select: —, day_kpi: 72, lang_switch: 158 |
| 375x812-ru-resident | 10 · 117 · 22 | 12 · 150 · 24 | complaint_form: 21, mine: 8, to_akimat: 95, lang_switch: 110 |
| 375x812-ru-akimat | 11 · 100 · 28 | 10 · 150 · 23 | hot_select: 629, day_kpi: 154, lang_switch: 230 |
| 375x812-kk-resident | 11 · 117 · 24 | 11 · 133 · 24 | complaint_form: 26, mine: 10, to_akimat: 106, lang_switch: 107 |
| 375x812-kk-akimat | 14 · 100 · 28 | 10 · 167 · 24 | hot_select: 655, day_kpi: 154, lang_switch: 89 |

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
| GET /api/civic/v2/modules | 19 | 4 | 14 | 200 |
| GET /api/civic/v2/heat z12 | 11 | 12 | 171 | 200 |
| GET /api/civic/v2/heat z16 | 47 | 3 | 19 | 200 |
| GET /api/civic/v2/akim/summary | 30 | 28 | 34 | 200 |
| POST /api/civic/v2/classify | 6 | 2 | 0 | 200 |
| POST /api/civic/v2/similar | 3 | 3 | 0 | 200 |
| GET /api/civic/v2/targets | 2 | 2 | 0 | 200 |
| GET /api/civic/v2/proposals | 8 | 4 | 5 | 200 |

Видимые слои стиля по умолчанию (первый вариант каждого вида):

- 1366x768-ru-resident: offline-bg (0), offline-nura-minor (0), offline-nura-street-case (0), offline-nura-street (0), offline-city-major-case (1244), offline-city-major (1244), civic-explore-lines (18), civic-explore-selected (0), civic-r03-approx-fill (0), civic-r03-approx-line (0), civic-r03-area-fill (0), civic-r03-area-line (0), civic-r03-area-line-approx (0), civic-r03-line-casing (0), civic-r03-line (0), civic-r03-line-approx (0), civic-r03-line-core (0), civic-r03-synthetic-outline (0), civic-r03-selected-line (0), civic-r03-point-halo (0), r07-district-fill (18), r07-district-line (18), r07-area-glow (0), r07-area-fill (0), r07-area-line (0), r07-area-approx (0), r07-sel-outline (0), r07-sel-line (0), r07-seg-casing (0), r07-seg (0), r07-seg-dashed (0), r07-obj-halo-lo (0), r07-obj-halo (0), r07-obj-dot (0), r07-place-line (0), r07-place-approx (0), r07-place-ring (0), civic-r03-point-synthetic (0), civic-r03-point (0), civic-r03-selected-point (0)
- 1366x768-ru-akimat: offline-bg (0), offline-nura-minor (0), offline-nura-street-case (0), offline-nura-street (0), offline-city-major-case (1236), offline-city-major (1236), civic-explore-lines (16), civic-explore-selected (0), civic-r03-approx-fill (0), civic-r03-approx-line (0), civic-r03-area-fill (0), civic-r03-area-line (0), civic-r03-area-line-approx (0), civic-r03-line-casing (0), civic-r03-line (0), civic-r03-line-approx (0), civic-r03-line-core (0), civic-r03-synthetic-outline (0), civic-r03-selected-line (0), civic-r03-point-halo (0), r07-district-fill (16), r07-district-line (16), r07-area-glow (0), r07-area-fill (0), r07-area-line (0), r07-area-approx (0), r07-sel-outline (0), r07-sel-line (0), r07-seg-casing (0), r07-seg (0), r07-seg-dashed (0), r07-obj-halo-lo (0), r07-obj-halo (0), r07-obj-dot (0), r07-place-line (0), r07-place-approx (0), r07-place-ring (0), civic-r03-point-synthetic (0), civic-r03-point (0), civic-r03-selected-point (0)
