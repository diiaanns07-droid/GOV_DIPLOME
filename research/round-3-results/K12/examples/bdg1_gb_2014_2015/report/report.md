# BDG1, Великобритания, 74 школы, Dec 2014 – Nov 2015 (НЕ Шымкент, НЕ Астана)

Схема `k12-energy-monthly-v1`. Окно анализа: 2014-12-01 — 2015-11-30. Страны во входе: GB. Классы данных зданий: {'real': 74}.

> Высокий EUI — **кандидат на энергообследование**, а не доказанная экономия и не доказанная неисправность. Рейтинг строится только внутри группы «город × тип объекта × класс данных» и только по зданиям с полностью покрытым окном.

**Условия использования измерений (как указаны во входе):** unknown: repository LICENSE is MIT (software); terms of the original measurement sources are not listed. Лицензия кода/репозитория не доказывает права на измерения.

## 1. Строки

Прочитано 888, принято 888, отклонено 0. Каждая строка с причинами — `rows_validation.csv`.

| Код | Тип | Строк | Что значит |
|---|---|---|---|
| `COVERAGE_LOW` | предупреждение | 62 | покрытие периода учётом < 0.8 |

## 2. Здания

Всего 74, в рейтинге 74.

| Предупреждение по зданию | Зданий | Что значит |
|---|---|---|
| `AREA_SOURCE_WEAK` | 74 | площадь не из техпаспорта/энергопаспорта |
| `LOW_ROW_COVERAGE` | 62 | есть периоды с покрытием < 0.8 |

## 3. Рейтинг по EUI внутри групп

### gb.unknown · school · real — 74 зданий, топ-15

| Место | Здание | EUI, кВт·ч/м² за год | В топ-15 | P(топ) при σ_log 0,2 | Зона | Доверие | Предупреждения |
|---|---|---|---|---|---|---|---|
| 1 | bdg1:PrimClass_Jaiden | 92.5 | да | 1.00 | stable_in_top | medium | AREA_SOURCE_WEAK, LOW_ROW_COVERAGE |
| 2 | bdg1:PrimClass_Jazmin | 91.3 | да | 1.00 | stable_in_top | medium | AREA_SOURCE_WEAK |
| 3 | bdg1:PrimClass_Jacob | 61.9 | да | 0.89 | boundary | medium | AREA_SOURCE_WEAK, LOW_ROW_COVERAGE |
| 4 | bdg1:PrimClass_Jamie | 61.2 | да | 0.88 | boundary | medium | AREA_SOURCE_WEAK, LOW_ROW_COVERAGE |
| 5 | bdg1:PrimClass_Johnathon | 60.8 | да | 0.84 | boundary | medium | AREA_SOURCE_WEAK, LOW_ROW_COVERAGE |
| 6 | bdg1:PrimClass_Johnnie | 59.0 | да | 0.83 | boundary | medium | AREA_SOURCE_WEAK, LOW_ROW_COVERAGE |
| 7 | bdg1:PrimClass_Jake | 56.8 | да | 0.76 | boundary | medium | AREA_SOURCE_WEAK |
| 8 | bdg1:PrimClass_Jon | 54.9 | да | 0.74 | boundary | medium | AREA_SOURCE_WEAK, LOW_ROW_COVERAGE |
| 9 | bdg1:PrimClass_Jane | 54.4 | да | 0.69 | boundary | medium | AREA_SOURCE_WEAK |
| 10 | bdg1:PrimClass_Janelle | 51.4 | да | 0.57 | boundary | medium | AREA_SOURCE_WEAK, LOW_ROW_COVERAGE |
| 11 | bdg1:PrimClass_Jediah | 50.7 | да | 0.54 | boundary | medium | AREA_SOURCE_WEAK, LOW_ROW_COVERAGE |
| 12 | bdg1:PrimClass_Joanna | 50.4 | да | 0.55 | boundary | medium | AREA_SOURCE_WEAK, LOW_ROW_COVERAGE |
| 13 | bdg1:PrimClass_Joey | 49.7 | да | 0.51 | boundary | medium | AREA_SOURCE_WEAK, LOW_ROW_COVERAGE |
| 14 | bdg1:PrimClass_Joel | 47.6 | да | 0.44 | boundary | medium | AREA_SOURCE_WEAK, LOW_ROW_COVERAGE |
| 15 | bdg1:PrimClass_Juanita | 46.8 | да | 0.38 | boundary | medium | AREA_SOURCE_WEAK, LOW_ROW_COVERAGE |
| 16 | bdg1:PrimClass_Jacquelyn | 46.5 | нет | 0.39 | boundary | medium | AREA_SOURCE_WEAK, LOW_ROW_COVERAGE |
| 17 | bdg1:PrimClass_Julio | 45.5 | нет | 0.37 | boundary | medium | AREA_SOURCE_WEAK, LOW_ROW_COVERAGE |
| 18 | bdg1:PrimClass_Josue | 44.8 | нет | 0.32 | boundary | medium | AREA_SOURCE_WEAK, LOW_ROW_COVERAGE |

Показаны места 1…18; полный список — `report.json`.

**Как меняется рейтинг.**

- Ошибка площади (σ_log = 0.1): среднее совпадение топ-15 0.851, P10 0.8.
- Ошибка площади (σ_log = 0.2): среднее совпадение топ-15 0.708, P10 0.6.
- Ошибка площади (σ_log = 0.3): среднее совпадение топ-15 0.607, P10 0.467.
- При σ_log = 0,2: устойчиво в топе 2, на границе 29, вне топа 43.
- Неполный учёт: если досчитать каждый период как значение / покрытие (допущение равномерного потребления в неучтённые часы), совпадение топа 0.933; входят bdg1:PrimClass_Jacquelyn; выходят bdg1:PrimClass_Juanita.

**Строгая политика учёта.** Если не принимать периоды с покрытием < 0.8, в рейтинге остаётся 12 из 74 зданий (выпадают из-за неполного окна: 62).

## 4. Чего этот отчёт не утверждает

- Не оценивает экономию, окупаемость и причину высокого потребления.
- Не сравнивает разные города и типы объектов между собой.
- Модель ошибки площади (лог-нормальная, σ_log 0,1–0,3) — допущение для чувствительности.
- Досчёт по покрытию — оценка, а не измерение; по умолчанию не используется.
