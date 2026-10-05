# K05 round 4 (REVIEW) — контракт наблюдений на новых входах: STATUS

Роль: REVIEW, slot K05. Ветка: `claude/optimistic-davinci-1oiqs9`. Статус: **done** для объёма задания (адаптер и тесты обоих городов, REPORT.md, FIELD_MAPPING.md).
Задание: `research/round-4/review/K05.txt` @ codex/research-import-2026-10-05 (cadba4d).
Входы: K10 round 3 `claude/save-work-handoff-j7pc05` @ ea703f1ddd3a411430a981164a78a7dda64ec909 → `inputs/k10_r3/` (Python `git show` + write_bytes, git blob сверен, sha256 places = package_manifest). Свои: v1.1 @ d913554 (не изменён).

## Сделано
- `schema/k05-obs-v1.2.schema.json` — выведена из v1.1 скриптом, добавлено обязательное `spatial_unit` (bbox/полигон/unknown) и `source.query`.
- `k05r4_contract.py` — правила v1.1 + территория: SPATIAL_UNKNOWN, BBOX, CITY_MISMATCH, CROSSES_DISTRICTS, агрегат SPATIAL_MIX/OVERLAP/LEGACY_UNIT, проверка объектов (город, точка в bbox, повтор id, неизвестная confidence).
- `k05r4_adapter.py` — счётчики записей по 7 группам × 2 порога для квадрата каждого города + missing «park не извлекался». Шымкент и Астана.
- Случаи `cases/cases.json`: настоящий 0, missing≠0, разные периоды, район E02 vs квадрат, пересечение bbox, unknown период/территория/confidence, повтор объекта, несовпадающий город.

## Проверки (реально выполнены)
- K10 `scripts/offline_check.py` на извлечённой копии пакета (git archive ea703f1) → ok, errors []; `unittest discover -s tests` K10 → 8 OK.
- `python research/round-4-results/K05/k05r4_adapter.py` → счёт при confidence ≥ 0 совпал с K10 expected_counts в обоих городах.
- `python research/round-4-results/K05/tests/test_k05r4.py` → 16 OK (jsonschema 4.26.0); `research/round-3-results/K05/tests/test_k05r3.py` → OK.

- Повторный запуск адаптера — те же sha256 выходов; синтаксис всех JSON — ok.
- Не запускалось: пересборка пакета K10 из сети; тесты продукта (код не менялся).

## Результаты и находки
- `REPORT.md`: v1.1 без `spatial_unit` сложила бы квадрат с районом (двойной счёт) — поэтому v1.2; квадраты делят по два района; 10/55 записей Шымкента в одной точке-заглушке (69.5958, 42.3167); ложные дубликаты по адресу госзданий; ошибки классификации («Реклама 42» как school).
- `FIELD_MAPPING.md`: отображение полей K10 → v1.2 и запреты для сборщика.

## Ограничения
Overture — вторичный источник; «полный» охват относится только к запросу K10 для одного квадрата одного выпуска. Доли районов — по полигонам Overture/OSM, не официальным.

## Следующий шаг
Сборщику: подключать счётчики квадратов только через `k05r4_contract.validate`/`aggregate_sum` по FIELD_MAPPING.md; объекты с `COLOCATED` помечать на карте. K10: при следующей выгрузке отделить записи с координатой-заглушкой до выбора квадрата.
