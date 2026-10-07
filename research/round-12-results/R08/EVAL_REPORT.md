# R08 — отчёт об оценке классификатора (генерируется `python -m ml.civic_classifier evaluate`)

**DEMONSTRATION: synthetic/agent-authored data; real-data quality NOT_EVALUATED**

- Модель: `civic-clf-logreg-kw-cf4464341-pe9ba054a` (logreg + признаки словаря); порог из validation: 0.3
- Корпус: `f446434196768da0…`; альтернатива для сравнения: `civic-clf-nb-cf4464341-p378f4882`
- Порядок экспериментов: experiment 2: test viewed for the 2nd time (experiment 1 = plain logreg, see exp1/); selection still on validation only
- Реальные обращения: **NOT_EVALUATED** — нет легально доступного корпуса реальных обращений с метками; источники в research/round-12-results/R08/DATA_SOURCES.json

## Test — невиданные шаблоны синтетического корпуса (n=631)

| Метод | Accuracy | Macro-F1 | 95% ДИ macro-F1 |
|---|---|---|---|
| logreg+keywords (selected) | 0.880 | 0.871 | 0.780–0.927 (template clusters (n=44)) |
| keyword_heuristic | 0.853 | 0.848 | 0.745–0.912 (template clusters (n=44)) |
| nb (alternative) | 0.567 | 0.557 | 0.435–0.648 (template clusters (n=44)) |

Парный бутстрэп Δmacro-F1 (выбранная − эвристика): +0.022 [-0.048; +0.096], доля ресэмплов с Δ>0: 0.732.

| Класс | Precision | Recall | F1 | Support |
|---|---|---|---|---|
| roads | 0.992 | 0.880 | 0.933 | 142 |
| sidewalks | 0.984 | 0.976 | 0.980 | 126 |
| transport_stops | 1.000 | 0.990 | 0.995 | 97 |
| lighting | 0.702 | 0.985 | 0.820 | 67 |
| landscaping | 0.818 | 0.766 | 0.791 | 94 |
| other | 0.716 | 0.695 | 0.705 | 105 |

Матрица ошибок выбранной модели (строки — истина, столбцы — прогноз):

| истина \ прогноз | roads | sidewalks | transport_stops | lighting | landscaping | other |
|---|---|---|---|---|---|---|
| roads | 125 | 1 | 0 | 4 | 1 | 11 |
| sidewalks | 1 | 123 | 0 | 0 | 0 | 2 |
| transport_stops | 0 | 0 | 96 | 0 | 0 | 1 |
| lighting | 0 | 0 | 0 | 66 | 0 | 1 |
| landscaping | 0 | 1 | 0 | 7 | 72 | 14 |
| other | 0 | 0 | 0 | 17 | 15 | 73 |

Срезы (выбранная модель / эвристика):

- **language** — kk: n=249, F1 0.802 / 0.806; mixed: n=79, F1 0.926 / 0.678; ru: n=303, F1 0.914 / 0.892
- **short_le_3_words** — False: n=620, F1 0.868; True: n=11, F1 0.881
- **ambiguous** — False: n=572, F1 0.885; True: n=59, F1 0.873
- **max_train_jaccard** — 0.4-0.6: n=275, F1 0.888; <0.4: n=316, F1 0.870; >=0.6: n=40, F1 0.798

- Калибровка (ECE max-score): 0.031 — score не является вероятностью.
- Порог 0.3 (если бы ему доверяли): авто-доля 0.837, точность авто 0.913. В runtime для синтетической модели needs_review=True всегда.
- Близость к train (Jaccard 3-грамм): среднее 0.41, доля ≥0.6: 0.063.

## Пробный набор — 112 сообщений, написанных агентом вне генератора (перенос стиля) (n=112)

| Метод | Accuracy | Macro-F1 | 95% ДИ macro-F1 |
|---|---|---|---|
| logreg+keywords (selected) | 0.830 | 0.837 | 0.767–0.896 (items) |
| keyword_heuristic | 0.821 | 0.832 | 0.756–0.891 (items) |
| nb (alternative) | 0.768 | 0.770 | 0.682–0.838 (items) |

Парный бутстрэп Δmacro-F1 (выбранная − эвристика): +0.005 [-0.024; +0.037], доля ресэмплов с Δ>0: 0.599.

| Класс | Precision | Recall | F1 | Support |
|---|---|---|---|---|
| roads | 0.882 | 0.682 | 0.769 | 22 |
| sidewalks | 0.842 | 0.889 | 0.865 | 18 |
| transport_stops | 1.000 | 0.944 | 0.971 | 18 |
| lighting | 0.882 | 0.833 | 0.857 | 18 |
| landscaping | 0.933 | 0.778 | 0.849 | 18 |
| other | 0.593 | 0.889 | 0.711 | 18 |

Матрица ошибок выбранной модели (строки — истина, столбцы — прогноз):

| истина \ прогноз | roads | sidewalks | transport_stops | lighting | landscaping | other |
|---|---|---|---|---|---|---|
| roads | 15 | 2 | 0 | 0 | 0 | 5 |
| sidewalks | 0 | 16 | 0 | 1 | 0 | 1 |
| transport_stops | 0 | 0 | 17 | 0 | 0 | 1 |
| lighting | 0 | 1 | 0 | 15 | 0 | 2 |
| landscaping | 1 | 0 | 0 | 1 | 14 | 2 |
| other | 1 | 0 | 0 | 0 | 1 | 16 |

Срезы (выбранная модель / эвристика):

- **language** — kk: n=31, F1 0.935 / 0.875; mixed: n=12, F1 1.000 / 1.000; ru: n=69, F1 0.769 / 0.787
- **short_le_3_words** — False: n=98, F1 0.832; True: n=14, F1 0.892
- **ambiguous** — False: n=101, F1 0.837; True: n=11, F1 0.850
- **max_train_jaccard** — 0.4-0.6: n=1, F1 1.000; <0.4: n=110, F1 0.833; >=0.6: n=1, F1 1.000
- **style** — formal: n=31, F1 0.870 / 0.877; mixed: n=13, F1 1.000 / 1.000; narrative: n=36, F1 0.832 / 0.799; short: n=13, F1 0.856 / 0.856; slang: n=13, F1 0.861 / 0.861; translit: n=6, F1 0.048 / 0.048

- Калибровка (ECE max-score): 0.094 — score не является вероятностью.
- Порог 0.3 (если бы ему доверяли): авто-доля 0.750, точность авто 0.917. В runtime для синтетической модели needs_review=True всегда.
- Близость к train (Jaccard 3-грамм): среднее 0.196, доля ≥0.6: 0.009.

## Validation — справочно (на нём выбраны метод и порог, не независимая оценка) (n=581)

| Метод | Accuracy | Macro-F1 | 95% ДИ macro-F1 |
|---|---|---|---|
| logreg+keywords (selected) | 0.890 | 0.888 | 0.804–0.941 (template clusters (n=37)) |
| keyword_heuristic | 0.847 | 0.845 | 0.746–0.914 (template clusters (n=37)) |
| nb (alternative) | 0.590 | 0.589 | 0.446–0.682 (template clusters (n=37)) |

Парный бутстрэп Δmacro-F1 (выбранная − эвристика): +0.043 [-0.002; +0.090], доля ресэмплов с Δ>0: 0.968.

| Класс | Precision | Recall | F1 | Support |
|---|---|---|---|---|
| roads | 0.990 | 0.797 | 0.883 | 128 |
| sidewalks | 0.869 | 0.946 | 0.906 | 112 |
| transport_stops | 0.979 | 1.000 | 0.989 | 92 |
| lighting | 0.819 | 0.872 | 0.845 | 78 |
| landscaping | 0.885 | 0.863 | 0.873 | 80 |
| other | 0.792 | 0.879 | 0.833 | 91 |

Матрица ошибок выбранной модели (строки — истина, столбцы — прогноз):

| истина \ прогноз | roads | sidewalks | transport_stops | lighting | landscaping | other |
|---|---|---|---|---|---|---|
| roads | 102 | 16 | 0 | 6 | 0 | 4 |
| sidewalks | 0 | 106 | 2 | 3 | 0 | 1 |
| transport_stops | 0 | 0 | 92 | 0 | 0 | 0 |
| lighting | 0 | 0 | 0 | 68 | 2 | 8 |
| landscaping | 0 | 0 | 0 | 3 | 69 | 8 |
| other | 1 | 0 | 0 | 3 | 7 | 80 |

Срезы (выбранная модель / эвристика):

- **language** — kk: n=200, F1 0.908 / 0.837; mixed: n=48, F1 1.000 / 0.989; ru: n=333, F1 0.868 / 0.844
- **short_le_3_words** — False: n=581, F1 0.888
- **ambiguous** — False: n=517, F1 0.911; True: n=64, F1 0.418
- **max_train_jaccard** — 0.4-0.6: n=199, F1 0.881; <0.4: n=367, F1 0.887; >=0.6: n=15, F1 0.847

- Калибровка (ECE max-score): 0.039 — score не является вероятностью.
- Порог 0.3 (если бы ему доверяли): авто-доля 0.826, точность авто 0.910. В runtime для синтетической модели needs_review=True всегда.
- Близость к train (Jaccard 3-грамм): среднее 0.372, доля ≥0.6: 0.026.

## Время и память

Файл модели 104804 байт; загрузка 0.157 с; пик выделений Python 5.2 МБ; classify в среднем 1.695 мс, p95 3.136 мс (n=743). одно ядро CPU, CPython, без GPU/сети; время — в этой облачной среде.

## Ошибки на пробном наборе (19)

| id | текст | истина | прогноз | score | эвристика | стиль |
|---|---|---|---|---|---|---|
| probe-000 | Колдобины такие, что подвеску разбил, когда уже заделают? | roads | other | 0.745 | other | slang |
| probe-002 | Светофор на пересечении у торгового центра показывает зелёный сразу и пешеходам и машинам | roads | sidewalks | 0.94 | sidewalks | narrative |
| probe-003 | Прошу проверить состояние дорожного покрытия на въезде в жилой комплекс, образовалась глубокая колея | roads | other | 0.452 | other | formal |
| probe-006 | зебру возле садика совсем не видно, дети переходят где попало | roads | sidewalks | 0.993 | sidewalks | narrative |
| probe-016 | yama na doroge vozle shkoly, opasno | roads | other | 0.694 | other | translit |
| probe-017 | Ямища! | roads | other | 0.763 | other | short |
| probe-021 | лежачих полицейских понаставили слишком высоких, днищем цепляем | roads | other | 0.403 | other | slang |
| probe-036 | net trotuara vdol ulicy, hodim po doroge | sidewalks | other | 0.685 | other | translit |
| probe-039 | Жер асты өтпесінде жарық бар, бірақ еден су | sidewalks | lighting | 0.994 | lighting | narrative |
| probe-054 | na ostanovke net navesa | transport_stops | other | 0.688 | other | translit |
| probe-059 | Прошу восстановить уличное освещение вдоль пешеходной аллеи | lighting | sidewalks | 0.605 | lighting | formal |
| probe-061 | нет света на улице | lighting | other | 0.391 | other | short |
| probe-072 | fonari ne goryat vo dvore | lighting | other | 0.682 | other | translit |
| probe-076 | Во дворе спилили все старые тополя, остались одни пни, дети играют на солнцепёке | landscaping | other | 0.454 | other | narrative |
| probe-090 | detskaya ploshadka slomana | landscaping | other | 0.696 | other | translit |
| probe-092 | Көше бойына жасыл желек отырғызу қажет | landscaping | lighting | 0.647 | other | formal |
| probe-093 | Посадили саженцы, но их никто не поливает, половина засохла | landscaping | roads | 0.29 | other | narrative |
| probe-095 | Прошу принять меры в отношении строительной площадки, работы ведутся после 23:00 | other | landscaping | 0.974 | landscaping | formal |
| probe-098 | Хочу поблагодарить за отремонтированную дорогу, ездить стало приятно | other | roads | 0.87 | roads | narrative |
