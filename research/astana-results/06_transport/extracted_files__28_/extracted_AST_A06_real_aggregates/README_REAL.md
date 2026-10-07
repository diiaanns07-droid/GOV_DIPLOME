# AST-A06 — реальные агрегаты по открытому набору автобусов Астаны
Выполнено 2026-10-05 (UTC). Python 3.12.3, только стандартная библиотека (r1, r1b, r2); pandas — только для профиля стороннего CSV (версия в r1/versions.txt).
Входы: зеркало набора Mansurova et al. (Zenodo 15769359) в github.com/Mrithula742/Bussure, коммит 0356bb5b37ef, каталог datasets/astana/gtfs_data
(trips.txt, routes.txt, stops.txt, calendar_dates.txt; stop_times.txt недоступен — Git LFS-хост заблокирован).
Границы районов: stupits/data/astana_districts.geojson (OSM, снимок Overpass 2026-09-22T08:45:51Z, коммит 834a25f).
Лицензия набора: CC BY 4.0 по README зеркала — на Zenodo не проверено. Атрибуция обязательна.
## Команды
```
python3 r1_astana_regularity.py   # r1/results.json, regularity.csv, trip_duration.csv
python3 r1b_sensitivity.py        # r1/cv_sensitivity.json (raw / clean / clean_weekday)
python3 r2_ptal_vs_observed.py    # r1/ptal_vs_observed.json
```
## Ограничения
Интервалы измерены между началами рейсов (start_time) одного маршрута/направления/дня — это конечная, не каждая остановка.
start_time реконструирован из GPS авторами набора; правила очистки (дубликаты, интервалы <60 с, неполные дни) — мои, см. r1b.
direction_id в наборе = 1/2 (GTFS требует 0/1). Период: 2024-07-29…2024-09-21, 3 маршрута (10, 12, 46) — не вся сеть.
Формула ожидания E[H]/2·(1+CV²) — допущение (случайный приход пассажиров); при длинных интервалах и онлайн-табло ожидание меньше.
Файл sample_stops_5rows.json — 5 неизменённых строк stops.txt для проверки формата.
