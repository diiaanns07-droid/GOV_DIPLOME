# K01 раунд 7 — STATUS: переносимый сценарный файл `city-whatif-v1`

- **Роль:** K01 (не BUILD); ветка `claude/loving-thompson-nmajdo`.
- **Входы:** `research/round-7/{snapshots.json,FEATURE_SPEC.txt,TASK.txt,tasks/K01.txt}` @ `codex/research-import-2026-10-05` `7927fa8`;
  срез — `prototypes/city-evidence/web/data.js` из **`c58a3b2b175cf978ad785fef7f88d8fd9b1338f2`** (`claude/beautiful-clarke-sbzomj`), извлечён во временную папку
  `research/round-5-results/K01/extract_build.py`; `web/data.js` побайтно одинаков в c58a3b2 и b3e4dc4 (`git diff --quiet`).
- **Статус: done** для минимума (валидатор + 6 фикстур + тесты). Функция в прототип **не интегрирована**: общий прототип меняет только BUILD.

## Файлы
- `whatif_v1.py` — stdlib: строгий разбор (≤256 KiB, UTF-8, без NaN/Infinity/1e999, без дубликатов ключей), проверка полей
  по FEATURE_SPEC, `source_snapshot` из содержимого среза, пересчёт до/после/delta (гаверсинус, R=6371008.8, clamp [0,1]),
  экспорт, digest для объяснения, `ScenarioStore` (отказ импорта не меняет состояние; смена города/категории сбрасывает сценарий).
- `fixtures/` — 6 гипотетических сценариев (`kind: "hypothetical"`) + `EXPECTED.json`: 2 валидных (Шымкент school с проектом;
  Астана outpatient_clinic без проекта с подложенным `computed`, который отбрасывается), 4 отклоняемых (чужой snapshot, проект вне bbox,
  URL в ID + несовпадение категории, 1e999/NaN + дубликат ключа).
- `test_whatif_v1.py` — 8 тестов; `runs/` — фактические выходы на c58a3b2; `runs/export_example_c58a3b2.json` — пример переносимого экспорта.

## source_snapshot (предложение реализации — спецификация задаёт состав, не кодировку)
`"cw1-" + sha256(canonical JSON {schema, city_id, release, bbox, places_social sha256 из манифеста сборки, sorted [id,group,lon,lat] всех записей среза, параметры расстояния})[:32]`.
На c58a3b2: shymkent `cw1-63d46116f7293e67b2b0ca63e217b9ec`, astana `cw1-94f62073b48178da3d5dedfbe8e944c4`.
Меняется при изменении любой записи, хэша манифеста, bbox или формулы (тест). Имя файла как версия не принимается (тест).
BUILD должен реализовать тот же алгоритм в JS (`crypto.subtle.digest`, тот же canonical JSON: sort_keys, separators `,`/`:`) или задать свой и обновить фикстуры.

## Реально выполненные проверки (на c58a3b2)
- `K01_APP_ROOT=<extracted>/city-evidence python3 -m unittest discover -s research/round-7-results/K01 -p test_whatif_v1.py -v` → **8/8 OK** (`runs/unittest_c58a3b2.txt`).
- CLI `whatif_v1.py --app-root … validate` по 6 фикстурам → 2 valid (exit 0), 4 rejected (exit 1) с ожидаемыми кодами (`runs/cli_fixtures_c58a3b2.txt`).
- В выходах нет абсолютных путей (`grep /home|/tmp|scratchpad` → 0).
- Проверено тестами: 256 KiB принимается, +1 байт отклоняется; bool/строка вместо координаты; вне bbox; дубликаты ID (точки и проект); длина/символы ID
  (URL, Windows-путь); лишние поля (`script`); 0 и 11 точек; два проекта; kind≠hypothetical; категория вне MVP и несовпадение категории проекта;
  неизвестный город/версия; snapshot-имя файла; Infinity/битый JSON/не UTF-8; импортированный `computed` не доверяется; экспорт → импорт даёт тот же сценарий и digest;
  проект на контрольной точке → честный 0; удаление проекта восстанавливает baseline; нет записей категории → before=null, delta=null, подпись.

## Не проверено / ограничения
- JS-интерфейс прототипа (нет реализации функции на c58a3b2); безопасный вывод строк в DOM — задача BUILD.
- Фикстура `invalid_category_mismatch_url_id` отклоняется по первому дефекту (`id`); несовпадение категории проверено отдельным тестом.
- Ближайшая запись в срезе ≠ ближайшее учреждение города; расстояние по прямой, не путь; QA-флаги не фильтруются — это поведение валидатора, отображение ограничений — задача BUILD.

## Следующий шаг
BUILD: взять `whatif_v1.py` как эталон Python (как `explain_ref.py` для K02) и фикстуры в `tests/`; реализовать snapshot/валидацию в JS и проверить JS=Python на этих 6 файлах. Затем K01 повторит тесты на новом SHA.
