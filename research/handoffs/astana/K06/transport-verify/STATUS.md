Задача / идентификатор: K06 — проверка транспортного направления (A06 Шымкент, AST-A06 Астана); task_id: transport-verify
Агент / город / сфера: K06 (Claude Code) / astana (реальные данные), Шымкент — только синтетика A06 / транспорт
Обновлено (дата, время, часовой пояс): 2026-10-05, ~05:40 UTC
Статус: ready_for_review (первый этап); общая задача остаётся partial, пока недоступны Zenodo и LFS
Рабочая ветка: claude/ecstatic-curie-hzfzn0
Исходный коммит, от которого началась работа: b87e5af6eeb6a5bdc33037a9f16d4e3377166ee5 (codex/research-import-2026-10-05), смержен в рабочую ветку обычным merge (merge-коммит 02cfbd0)
Назначенные пути / модуль: research/next-round/K06/, этот handoff. Исходники приложения и старые отчёты не изменялись.

Цель и проверяемый критерий готовности:
Найти реальный набор Астаны из AST-A06; проверить происхождение, период, охват и лицензию; прочитать скрипты и воспроизвести расчёт; описать функцию сайта, которую данные реально позволяют, и то, чего они не позволяют; отделить реальные данные от синтетики.

Что реально сделано:
- Проверен доступ: zenodo.org и mdpi.com — 403 CONNECT (политика прокси); GitHub-зеркало читается через git.
- Получено зеркало Mrithula742/Bussure @ 0356bb5 (sparse, без LFS) — тот же коммит, что у AST-A06.
- Прочитаны r1_astana_regularity.py, r1b_sensitivity.py, r2_ptal_vs_observed.py: только чтение TSV/GeoJSON и запись агрегатов, без сети.
- Воспроизведены R1/R1b/R2: JSON идентичны побайтно, CSV — по содержанию (CRLF/LF).
- Новые проверки: C1 перекрытия рейсов (0/16909), C2 CV внутри дня против объединённого (0,675 против 0,82), C4 разрывы между рейсами одной машины (76,7% ≤60 с, т.е. длительность включает отстой на конечной).
- Отчёт с функцией сайта и списком «нельзя прогнозировать», evidence JSON.

Файлы результата (точные пути от корня):
- research/next-round/K06/REPORT.md
- research/next-round/K06/k06_evidence.json
- research/next-round/K06/repro/scripts/{r1_astana_regularity.py,r1b_sensitivity.py,r2_ptal_vs_observed.py} — копии AST-A06, изменены только пути
- research/next-round/K06/repro/scripts/{k06_independent_checks.py,k06_gap_check.py} — новые проверки
- research/next-round/K06/repro/out/ — r1/*, k06_checks.json, k06_gap_check.json, k06_excess_within_day.txt, *_stdout.txt
- research/next-round/K06/source_snapshot/ — READ-ME, DOWNLOAD-CHECKS, agency, routes, 5 строк trips без vehicle_id, LFS-указатели, SHA256 входов
- research/handoffs/astana/K06/transport-verify/STATUS.md

Проверки:
- curl к zenodo.org/api/records/15769359 и mdpi.com → curl (56) CONNECT tunnel failed, response 403.
- git ls-remote https://github.com/Mrithula742/Bussure → 0356bb5b37ef0992ec0df3a4f09be35e3147b094.
- python3 (3.11.15) r1/r1b/r2 → cmp: results.json, cv_sensitivity.json, ptal_vs_observed.json IDENTICAL; diff --strip-trailing-cr: regularity.csv, trip_duration.csv идентичны.
- k06_independent_checks.py, k06_gap_check.py → результаты в repro/out (числа в REPORT.md, раздел 3).
- python3 -m json.tool для всех новых JSON → ok.
- Не запускалось: тесты приложения (код продукта не менялся); SUMO-эксперименты A06 (синтетика, к реальным данным не относится).

Доказательства и ограничения:
- Открыто: зеркало Bussure @ 0356bb5 (2026-10-05), data/astana_districts.geojson проекта. Город: Астана. Период данных: 2024-07-29..2024-09-21.
- Не открыто: Zenodo 15769359, статья doi:10.3390/data10080119 (403 прокси); LFS stop_times и segment_level_data (только указатели, повторно не запрашивались).
- Лицензия CC BY 4.0 — только по README зеркала; это гипотеза до проверки Zenodo.
- Формула ожидания H/2·(1+CV²) — допущение. C2' — приближение (H из объединённой выборки).
- A06 E1–E3 (Шымкент) — синтетические сети SUMO/Python, не данные города и не пробки.

Незавершённое:
- Подтверждение лицензии и метода реконструкции рейсов на Zenodo и в статье.
- stop_times: привязка остановок к маршрутам, интервалы на промежуточных остановках.
- Статус маршрутов 10/12/46 и ЛРТ в 2026 году.

Следующий конкретный шаг:
1. После разрешения доступа к zenodo.org (или если владелец передаст gtfs_data.zip и segment_level_data.zip с Zenodo): сверить лицензию на странице записи и запустить R1 на промежуточных остановках по stop_times.

Для воспроизведения:
- GIT_LFS_SKIP_SMUDGE=1 git clone --filter=blob:none --sparse https://github.com/Mrithula742/Bussure bussure && cd bussure && git sparse-checkout set datasets/astana && git checkout 0356bb5b37ef0992ec0df3a4f09be35e3147b094
- export BUSSURE_GTFS=$PWD/datasets/astana/gtfs_data STUPITS_GEOJSON=<repo>/data/astana_districts.geojson K06_OUT=<repo>/research/next-round/K06/repro/out
- cd $K06_OUT && python3 ../scripts/r1_astana_regularity.py && python3 ../scripts/r1b_sensitivity.py && python3 ../scripts/r2_ptal_vs_observed.py && python3 ../scripts/k06_independent_checks.py && python3 ../scripts/k06_gap_check.py
- Сверка входов: research/next-round/K06/source_snapshot/SHA256SUMS_gtfs_data.txt. Только стандартная библиотека Python, секретов нет.

Известные конфликты и зависимости от других агентов:
- K07 (доступность): OSM-граф и реестр объектов для следующей ступени. K08: независимая проверка лицензии Zenodo, если у него будет доступ.
- Предыдущий handoff этой ветки research/handoffs/unassigned/... — пустой checkpoint прошлого поручения, не изменялся.
