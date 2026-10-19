# R10 · эталон карты · c6d62440

```
{"root":"/tmp/claude-0/-home-user-GOV-DIPLOME/62d68526-d416-54f0-b206-35e3353bc4a5/scratchpad/builds/r01-c6d6","sha":"c6d62440","when":"2026-10-15T19:11:17.740Z","base":"(свой сервер, временная база, CIVIC_DEMO=1)","repeat":3,"sizes":["1366x768","375x812"],"langs":["ru","kk"],"modes":["resident","akimat"],"chromium":"141.0.7390.37","machine":{"cpu":"Intel(R) Xeon(R) Processor @ 2.80GHz","cores":4,"mem_gb":16,"platform":"linux 6.18.44-fc-v114","node":"v22.22.0"}}
```

Загрузка, медиана из 3 окон без кэша, секунды от начала навигации (WebGL программный — сравнивать с прогоном на той же машине):

| Вариант | DOM готов | load | карта загружена | 1-й значок с числом | главная кнопка | карта успокоилась | запросов | КБ | длинные задачи, мс |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 1366x768-ru-resident | 0.55 | 0.59 | 5.95 | 2.53 | 2.52 | 5.59 | 130 | 10105 | 4976 |
| 1366x768-ru-akimat | 0.44 | 0.53 | 6.15 | 2.56 | — | 5.91 | 129 | 10146 | 5201 |
| 1366x768-kk-resident | 0.40 | 0.51 | 6.43 | 2.85 | 2.85 | 6.35 | 132 | 10567 | 5187 |
| 1366x768-kk-akimat | 0.45 | 0.51 | 5.56 | 2.60 | — | 5.56 | 130 | 10332 | 5010 |
| 375x812-ru-resident | 0.44 | 0.50 | 4.25 | 2.29 | 2.29 | 4.07 | 129 | 10290 | 3005 |
| 375x812-ru-akimat | 0.49 | 0.56 | 4.35 | 2.38 | 2.29 | 4.17 | 128 | 10104 | 3220 |
| 375x812-kk-resident | 0.50 | 0.56 | 4.67 | 2.36 | 2.33 | 4.66 | 130 | 10476 | 3406 |
| 375x812-kk-akimat | 0.50 | 0.54 | 4.21 | 2.35 | 2.35 | 4.01 | 129 | 10290 | 3033 |

Вид по умолчанию (первое окно):

| Вариант | слоёв видно / всего | значков (с числом) | 3D-табличек | кнопок вне карты | меню | масштаб | кадр |
|---|---|---|---|---|---|---|---|
| 1366x768-ru-resident | 37 / 48 | 6 (6) | 0 | 24 | 3: Акимат · Житель · Для сотрудников | z10.37 | default-1366x768-ru-resident.png |
| 1366x768-ru-akimat | 37 / 48 | 6 (6) | 0 | 27 | 3: Акимат · Житель · Для сотрудников | z10.37 | default-1366x768-ru-akimat.png |
| 1366x768-kk-resident | 37 / 48 | 6 (6) | 0 | 24 | 3: Әкімдік · Тұрғын · Қызметкерлерге | z10.37 | default-1366x768-kk-resident.png |
| 1366x768-kk-akimat | 37 / 48 | 6 (6) | 0 | 27 | 3: Әкімдік · Тұрғын · Қызметкерлерге | z10.37 | default-1366x768-kk-akimat.png |
| 375x812-ru-resident | 37 / 48 | 3 (3) | 0 | 17 | 10: Уведомления · Карта · Мои обращения · Мой двор · Идеи · Сделаем вместе · Вопросы и встречи · Акимат · Житель · Для сотру | z9 | default-375x812-ru-resident.png |
| 375x812-ru-akimat | 37 / 48 | 2 (2) | 0 | 22 | 13: Карта · Картина дня · Обращения · Ведомства · Проекты и идеи · Сделаем вместе · Вопросы и встречи · Спросить Birge · Сит | z9 | default-375x812-ru-akimat.png |
| 375x812-kk-resident | 37 / 48 | 3 (3) | 0 | 17 | 10: Хабарламалар · Карта · Менің өтініштерім · Менің аулам · Идеялар · Бірге жасайық · Сұрақтар мен кездесулер · Әкімдік · Т | z9 | default-375x812-kk-resident.png |
| 375x812-kk-akimat | 37 / 48 | 2 (2) | 0 | 22 | 13: Карта · Күн қорытындысы · Өтініштер · Ведомстволар · Жобалар мен идеялар · Бірге жасайық · Сұрақтар мен кездесулер · Bir | z9 | default-375x812-kk-akimat.png |

Плавность (кадр/с · p95 мс · кадров > 50 мс) и отклик интерфейса, мс:

| Вариант | сдвиг | полёт 12→15 | отклик |
|---|---|---|---|
| 1366x768-ru-resident | 1 · 1217 · 4 | 2 · 650 · 6 | complaint_form: 46, mine: 19, to_akimat: 730, lang_switch: 706 |
| 1366x768-ru-akimat | 2 · 717 · 6 | 2 · 650 · 6 | hot_select: —, day_kpi: 93, lang_switch: 617 |
| 1366x768-kk-resident | 1 · 917 · 4 | 1 · 667 · 6 | complaint_form: 30, mine: 7, to_akimat: 715, lang_switch: 265 |
| 1366x768-kk-akimat | 2 · 783 · 6 | 2 · 567 · 7 | hot_select: —, day_kpi: 160, lang_switch: 306 |
| 375x812-ru-resident | 5 · 267 · 12 | 6 · 317 · 16 | complaint_form: 37, mine: 21, to_akimat: 206, lang_switch: 595 |
| 375x812-ru-akimat | 6 · 217 · 14 | 6 · 283 · 15 | hot_select: 718, day_kpi: 155, lang_switch: 466 |
| 375x812-kk-resident | 4 · 250 · 11 | 6 · 350 · 15 | complaint_form: 33, mine: 12, to_akimat: 231, lang_switch: 229 |
| 375x812-kk-akimat | 6 · 200 · 15 | 5 · 283 · 14 | hot_select: 546, day_kpi: 154, lang_switch: 192 |

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
| GET /api/civic/v2/modules | 31 | 6 | 14 | 200 |
| GET /api/civic/v2/heat z12 | 18 | 20 | 171 | 200 |
| GET /api/civic/v2/heat z16 | 68 | 4 | 19 | 200 |
| GET /api/civic/v2/akim/summary | 49 | 49 | 34 | 200 |
| POST /api/civic/v2/classify | 7 | 3 | 0 | 200 |
| POST /api/civic/v2/similar | 4 | 4 | 0 | 200 |
| GET /api/civic/v2/targets | 3 | 3 | 0 | 200 |
| GET /api/civic/v2/proposals | 7 | 7 | 5 | 200 |

Видимые слои стиля по умолчанию (первый вариант каждого вида):

- 1366x768-ru-resident: offline-bg (0), offline-nura-minor (0), offline-nura-street-case (0), offline-nura-street (0), offline-city-major-case (1244), offline-city-major (1244), civic-explore-lines (18), civic-explore-selected (0), civic-r03-approx-fill (6), civic-r03-approx-line (6), civic-r03-area-fill (0), civic-r03-area-line (0), civic-r03-area-line-approx (0), civic-r03-line-casing (1), civic-r03-line (1), civic-r03-line-approx (0), civic-r03-line-core (0), civic-r03-synthetic-outline (1), civic-r03-selected-line (0), civic-r03-point-halo (3), r07-district-fill (18), r07-district-line (18), r07-area-glow (0), r07-area-fill (0), r07-area-line (0), r07-area-approx (0), r07-sel-outline (0), r07-sel-line (0), r07-seg-casing (0), r07-seg (0), r07-seg-dashed (0), r07-obj-halo-lo (0), r07-obj-halo (0), r07-obj-dot (0), civic-r03-point-synthetic (3), civic-r03-point (3), civic-r03-selected-point (0)
- 1366x768-ru-akimat: offline-bg (0), offline-nura-minor (0), offline-nura-street-case (0), offline-nura-street (0), offline-city-major-case (1236), offline-city-major (1236), civic-explore-lines (16), civic-explore-selected (0), civic-r03-approx-fill (6), civic-r03-approx-line (6), civic-r03-area-fill (0), civic-r03-area-line (0), civic-r03-area-line-approx (0), civic-r03-line-casing (1), civic-r03-line (1), civic-r03-line-approx (0), civic-r03-line-core (0), civic-r03-synthetic-outline (1), civic-r03-selected-line (0), civic-r03-point-halo (3), r07-district-fill (16), r07-district-line (16), r07-area-glow (0), r07-area-fill (0), r07-area-line (0), r07-area-approx (0), r07-sel-outline (0), r07-sel-line (0), r07-seg-casing (0), r07-seg (0), r07-seg-dashed (0), r07-obj-halo-lo (0), r07-obj-halo (0), r07-obj-dot (0), civic-r03-point-synthetic (3), civic-r03-point (3), civic-r03-selected-point (0)
