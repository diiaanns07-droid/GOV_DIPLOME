# SYNTHETIC: проверочные случаи валидатора (не здания Шымкента и Астаны)

Схема `k12-energy-monthly-v1`. Окно анализа: 2025-01-01 — 2025-12-31. Страны во входе: KZ. Классы данных зданий: {'unknown': 4, 'synthetic': 28}.

> Высокий EUI — **кандидат на энергообследование**, а не доказанная экономия и не доказанная неисправность. Рейтинг строится только внутри группы «город × тип объекта × класс данных» и только по зданиям с полностью покрытым окном.

**Условия использования измерений (как указаны во входе):** synthetic: invented test values. Лицензия кода/репозитория не доказывает права на измерения.

## 1. Строки

Прочитано 333, принято 317, отклонено 16. Каждая строка с причинами — `rows_validation.csv`.

| Код | Тип | Строк | Что значит |
|---|---|---|---|
| `CITY_INVALID` | отклонение | 1 | city_id не из разрешённого списка (для KZ — kz.shymkent или kz.astana) |
| `DUPLICATE_CONFLICT` | отклонение | 2 | тот же здание+период с разными значениями — отклонены все |
| `DUPLICATE_EXACT` | отклонение | 1 | точный дубликат строки (оставлена первая) |
| `KIND_INVALID` | отклонение | 1 | kind не observed / derived / synthetic |
| `PERIOD_END_BEFORE_START` | отклонение | 1 | period_end раньше period_start |
| `PERIOD_INVALID` | отклонение | 1 | дата не в формате YYYY-MM-DD |
| `PERIOD_OVERLAP` | отклонение | 4 | период пересекается с другим периодом того же здания — риск двойного учёта |
| `REQUIRED_EMPTY` | отклонение | 1 | пусто обязательное поле |
| `UNIT_NOT_ELECTRIC_ENERGY` | отклонение | 2 | единица не энергия электричества (кВт — мощность, Гкал/м³ — другой ресурс) |
| `VALUE_NEGATIVE` | отклонение | 1 | отрицательное потребление |
| `ZERO_NOT_CONFIRMED` | отклонение | 1 | 0 без value_status=reported_zero: неясно, ноль это или нет данных |
| `PERIOD_CROSSES_WINDOW` | не входит в итог окна | 1 | период выходит за границу окна анализа — не делится пропорционально |
| `COVERAGE_LOW` | предупреждение | 3 | покрытие периода учётом < 0.8 |
| `DECIMAL_COMMA` | предупреждение | 1 | десятичная запятая прочитана как точка |
| `UNIT_CONVERTED` | предупреждение | 12 | значение переведено в kWh из MWh / тыс. кВт·ч |
| `ZERO_REPORTED` | предупреждение | 1 | подтверждённый ноль за период — проверить причину (закрытие, отключение) |

Отклонённые строки (первые 40):

| Строка файла | Здание | Период | Причины |
|---|---|---|---|
| 141 | SYN-SHY-ZERO-UNCONFIRMED | 2025-08-01…2025-08-31 | ZERO_NOT_CONFIRMED |
| 160 | SYN-SHY-NEGATIVE | 2025-03-01…2025-03-31 | VALUE_NEGATIVE |
| 221 | SYN-SHY-KW | 2025-04-01…2025-04-30 | UNIT_NOT_ELECTRIC_ENERGY |
| 234 | SYN-SHY-GCAL | 2025-05-01…2025-05-31 | UNIT_NOT_ELECTRIC_ENERGY |
| 266 | SYN-SHY-DUP-EXACT | 2025-06-01…2025-06-30 | DUPLICATE_EXACT |
| 272 | SYN-SHY-DUP-CONFLICT | 2025-06-01…2025-06-30 | DUPLICATE_CONFLICT |
| 279 | SYN-SHY-DUP-CONFLICT | 2025-06-01…2025-06-30 | DUPLICATE_CONFLICT |
| 292 | SYN-SHY-OVERLAP | 2025-01-01…2025-01-31 | PERIOD_OVERLAP |
| 293 | SYN-SHY-OVERLAP | 2025-02-01…2025-02-28 | PERIOD_OVERLAP |
| 294 | SYN-SHY-OVERLAP | 2025-03-01…2025-03-31 | PERIOD_OVERLAP |
| 304 | SYN-SHY-OVERLAP | 2025-01-01…2025-03-31 | PERIOD_OVERLAP |
| 329 | SYN-ALMATY-01 | 2025-01-01…2025-01-31 | CITY_INVALID |
| 330 | SYN-SHY-BADDATE | 2025-02-30…2025-03-01 | PERIOD_INVALID |
| 331 | SYN-SHY-BACKWARDS | 2025-03-31…2025-03-01 | PERIOD_END_BEFORE_START |
| 332 | — | 2025-01-01…2025-01-31 | REQUIRED_EMPTY |
| 333 | SYN-SHY-HYPOTHESIS | 2025-01-01…2025-01-31 | KIND_INVALID |

## 2. Здания

Всего 32, в рейтинге 15.

| Почему не в рейтинге | Зданий | Что значит |
|---|---|---|
| `AREA_NOT_POSITIVE` | 1 | площадь 0 или отрицательная |
| `AREA_UNKNOWN` | 1 | площадь неизвестна |
| `CITY_INCONSISTENT` | 1 | у здания разные city_id |
| `INCOMPLETE_WINDOW` | 9 | окно анализа покрыто не полностью — EUI за неполный период не сравнивается с годовым |
| `NORM_ACCRUAL_IN_WINDOW` | 1 | в окне есть начисления по нормативу — это не измерение |
| `NO_ACCEPTED_ROWS` | 4 | нет принятых строк |

| Предупреждение по зданию | Зданий | Что значит |
|---|---|---|
| `AREA_SOURCE_UNKNOWN` | 1 | источник площади неизвестен |
| `ESTIMATED_IN_WINDOW` | 1 | есть расчётные (estimated) показания |
| `LOW_ROW_COVERAGE` | 1 | есть периоды с покрытием < 0.8 |
| `UNIT_CONVERTED` | 1 | часть значений переведена из MWh |
| `ZERO_REPORTED_IN_WINDOW` | 1 | есть подтверждённые нулевые периоды |

| Здание | Город | Дней с данными / окно | Причины |
|---|---|---|---|
| SYN-ALMATY-01 | kz.almaty | — / 365 | NO_ACCEPTED_ROWS |
| SYN-SHY-AREA-UNKNOWN | kz.shymkent | 365 / 365 | AREA_UNKNOWN |
| SYN-SHY-AREA-ZERO | kz.shymkent | 365 / 365 | AREA_NOT_POSITIVE |
| SYN-SHY-BACKWARDS | kz.shymkent | — / 365 | NO_ACCEPTED_ROWS |
| SYN-SHY-BADDATE | kz.shymkent | — / 365 | NO_ACCEPTED_ROWS |
| SYN-SHY-BILLING-15TH | kz.shymkent | 334 / 365 | INCOMPLETE_WINDOW |
| SYN-SHY-COMMA | kz.shymkent | 31 / 365 | INCOMPLETE_WINDOW |
| SYN-SHY-DUP-CONFLICT | kz.shymkent | 335 / 365 | INCOMPLETE_WINDOW |
| SYN-SHY-GCAL | kz.shymkent | 334 / 365 | INCOMPLETE_WINDOW |
| SYN-SHY-HYPOTHESIS | kz.shymkent | — / 365 | NO_ACCEPTED_ROWS |
| SYN-SHY-KW | kz.shymkent | 335 / 365 | INCOMPLETE_WINDOW |
| SYN-SHY-MISSING-MONTH | kz.shymkent | 334 / 365 | INCOMPLETE_WINDOW |
| SYN-SHY-NEGATIVE | kz.shymkent | 334 / 365 | INCOMPLETE_WINDOW |
| SYN-SHY-NORM | kz.shymkent | 365 / 365 | NORM_ACCRUAL_IN_WINDOW |
| SYN-SHY-OVERLAP | kz.shymkent | 275 / 365 | INCOMPLETE_WINDOW |
| SYN-SHY-TWO-CITIES | kz.astana+kz.shymkent | 365 / 365 | CITY_INCONSISTENT |
| SYN-SHY-ZERO-UNCONFIRMED | kz.shymkent | 334 / 365 | INCOMPLETE_WINDOW |

## 3. Рейтинг по EUI внутри групп

### kz.astana · school · synthetic — 5 зданий, топ-1

| Место | Здание | EUI, кВт·ч/м² за год | В топ-1 | P(топ) при σ_log 0,2 | Зона | Доверие | Предупреждения |
|---|---|---|---|---|---|---|---|
| 1 | SYN-AST-01 | 32.3 | да | 0.73 | boundary | high | — |
| 2 | SYN-AST-04 | 26.7 | нет | 0.24 | boundary | high | — |
| 3 | SYN-AST-02 | 20.0 | нет | 0.03 | outside | high | — |
| 4 | SYN-AST-05 | 15.0 | нет | 0.00 | outside | high | — |

Показаны места 1…4; полный список — `report.json`.

**Как меняется рейтинг.**

- Ошибка площади (σ_log = 0.1): среднее совпадение топ-1 0.909, P10 1.0.
- Ошибка площади (σ_log = 0.2): среднее совпадение топ-1 0.733, P10 0.0.
- Ошибка площади (σ_log = 0.3): среднее совпадение топ-1 0.609, P10 0.0.
- При σ_log = 0,2: устойчиво в топе 0, на границе 2, вне топа 3.
- Неполный учёт: если досчитать каждый период как значение / покрытие (допущение равномерного потребления в неучтённые часы), совпадение топа 1.0; входят —; выходят —.

### kz.shymkent · school · synthetic — 10 зданий, топ-2

| Место | Здание | EUI, кВт·ч/м² за год | В топ-2 | P(топ) при σ_log 0,2 | Зона | Доверие | Предупреждения |
|---|---|---|---|---|---|---|---|
| 1 | SYN-SHY-01 | 36.0 | да | 0.56 | boundary | high | — |
| 2 | SYN-SHY-05 | 34.7 | да | 0.46 | boundary | high | — |
| 3 | SYN-SHY-DUP-EXACT | 30.0 | нет | 0.22 | boundary | high | — |
| 4 | SYN-SHY-ESTIMATED | 30.0 | нет | 0.23 | boundary | low | ESTIMATED_IN_WINDOW |
| 5 | SYN-SHY-LOWCOV | 30.0 | нет | 0.19 | boundary | medium | LOW_ROW_COVERAGE |

Показаны места 1…5; полный список — `report.json`.

**Как меняется рейтинг.**

- Ошибка площади (σ_log = 0.1): среднее совпадение топ-2 0.735, P10 0.5.
- Ошибка площади (σ_log = 0.2): среднее совпадение топ-2 0.506, P10 0.0.
- Ошибка площади (σ_log = 0.3): среднее совпадение топ-2 0.417, P10 0.0.
- При σ_log = 0,2: устойчиво в топе 0, на границе 7, вне топа 3.
- Неполный учёт: если досчитать каждый период как значение / покрытие (допущение равномерного потребления в неучтённые часы), совпадение топа 0.5; входят SYN-SHY-LOWCOV; выходят SYN-SHY-05.

**Строгая политика учёта.** Если не принимать периоды с покрытием < 0.8, в рейтинге остаётся 14 из 15 зданий (выпадают из-за неполного окна: 1).

## 4. Чего этот отчёт не утверждает

- Не оценивает экономию, окупаемость и причину высокого потребления.
- Не сравнивает разные города и типы объектов между собой.
- Модель ошибки площади (лог-нормальная, σ_log 0,1–0,3) — допущение для чувствительности.
- Досчёт по покрытию — оценка, а не измерение; по умолчанию не используется.
