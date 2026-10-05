Задача / идентификатор: K05 — контракт данных и различие unknown/zero («нет данных записано как ноль»)
Агент / город / сфера: Claude Code (сессия claude/optimistic-davinci-1oiqs9) / проверенные файлы — Астана, контракт — оба города / данные и provenance
Обновлено: 2026-10-05, UTC
Статус: ready_for_review (первый этап завершён; см. «Незавершённое»)
Рабочая ветка: claude/optimistic-davinci-1oiqs9
Исходный коммит: codex/research-import-2026-10-05 @ b87e5af6eeb6a5bdc33037a9f16d4e3377166ee5, влит обычным merge (25f7378) в ветку сессии от main 834a25f
Назначенные пути / модуль: research/next-round/K05/, research/handoffs/shared/claude-optimistic-davinci-1oiqs9/K05/STATUS.md

Цель и критерий готовности:
Подтвердить или опровергнуть проблему по текущим data/real_context*.json и коду; предложить минимальный контракт наблюдения;
изолированный валидатор с примерами: настоящий ноль, отсутствие, устаревшее, синтетика. city_data.json и эталоны не менять.

Что реально сделано:
- Проблема ПОДТВЕРЖДЕНА: 25/25 ячеек real_context.json = 0 при meta.status=unavailable; источник — fetch_real_context.handle_failure().
- Воспроизведено: настоящая handle_failure() во временном каталоге пишет 25 нулей, 0 null; повторный сбой не обновляет meta.
- Подтверждено: кроме fetch_real_context.py, код (.py/.js/.html) real_context не читает — в Score/UI не попадает.
- Найдено дополнительно: сбой обновления не фиксируется; нули при status=ok означают «нет в OSM»; Сарайшык вне DISTRICT_IDS.
- Контракт k05-obs-v1 (observation.schema.json) и валидатор k05_validator.py (stdlib): правила null≠0, явный reported_zero,
  CITY_MIX, синтетика отдельно, STALE по max_age_days, BOUNDARY_MISMATCH, агрегат без подмены null нулём.
- Примеры из настоящих локальных файлов: ноль admin_level=9 и число 5 районов admin_level=6 (снимок Overpass, ODbL),
  25 missing из real_context, устаревшее (демо-политика 7 дней), синтетика city_data esil.T1=45; 6 неверных случаев.
- Ошибка собственного первого прототипа (центроид засчитал Целиноградский район) найдена и исправлена.

Файлы результата:
- research/next-round/K05/REPORT.md
- research/next-round/K05/STATUS.md
- research/next-round/K05/observation.schema.json
- research/next-round/K05/k05_validator.py
- research/next-round/K05/k05_experiment.py
- research/next-round/K05/test_k05_validator.py
- research/next-round/K05/experiment_output.json
- research/next-round/K05/examples/{real_zero_osm_admin_level9,real_count_osm_admin_level6,stale_osm_admin_level6,synthetic_city_data_esil_T1,missing_real_context_astana}.json
- research/next-round/K05/examples/invalid/invalid_cases.json
- research/handoffs/shared/claude-optimistic-davinci-1oiqs9/K05/STATUS.md (указатель)

Проверки (фактически выполнены, Python 3.11.15):
- python research/next-round/K05/k05_experiment.py → data_unchanged: true; E2 25 нулей/0 null; E3 25 missing, 0 отклонено.
- python research/next-round/K05/test_k05_validator.py → Ran 9 tests, OK.
- k05_validator.py examples/*.json examples/invalid/*.json --as-of 2026-10-05 → 35 записей, отклонено 6 (все неверные), exit 1 ожидаем.
- k05_validator.py --from-legacy data/real_context.json data/real_context_meta.json → 25 записей, отклонено 0.
- python -m json.tool по всем новым JSON → ок. git status: изменений вне research/next-round/K05 и handoff нет.
- Не запускалось: тесты продукта (код продукта не менялся); jsonschema-проверка схемы (библиотеки нет).

Доказательства и ограничения:
- Локальные источники: data/real_context*.json, fetch_real_context.py, data/geo_sources/astana_districts_overpass.json
  (osm_base 2026-09-22T08:45:51Z, retrieved 2026-09-23T11:28:06Z), data/astana_districts.geojson, data/city_data.json. SHA256 в experiment_output.json.
- Сеть: overpass-api.de и stat.gov.kz — по одному запросу, CONNECT 403 (connect_rejected, политика прокси). Повторов нет.
  Реальный образец POI и официальные показатели не получены — отсутствие доступа, а не данных.
- Синтетика: city_data.json (учебный). Демо-допущение: max_age_days=7. Примеров по Шымкенту нет (нет локальных реальных данных).

Незавершённое:
- Настоящий малый образец POI (школы/остановки) для Астаны и Шымкента — ждёт доступа к Overpass или переданного файла.
- Исправление fetch_real_context.py — только отдельным заданием (рекомендации в REPORT.md §4).

Следующий конкретный шаг:
1. При доступе к overpass-api.de: получить счётчик одной категории по одному району Астаны и Шымкента, сохранить сырой ответ с sha256
   и прогнать через k05_validator (reported/reported_zero), либо получить такой файл от K10.

Для воспроизведения: см. REPORT.md §6. Только stdlib, секретов нет.

Зависимости: K10 (доступ к источникам/образцы), координатор — решение о правке fetch_real_context.py; согласовать поля с AST-A13 IndicatorDefinition.
