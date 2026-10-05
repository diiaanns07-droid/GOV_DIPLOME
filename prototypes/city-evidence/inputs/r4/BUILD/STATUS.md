# BUILD раунд 4 — STATUS

- owner_branch: `claude/beautiful-clarke-sbzomj` (единственный сборщик BUILD, назначен пользователем 2026-10-05)
- Пути: `prototypes/city-evidence/`, `research/round-4-results/BUILD/`
- Задание: `research/round-4/BUILD.txt` @ `codex/research-import-2026-10-05` `cadba4d200387b9a97cb2d1c5aa0a8fd5a150c1e`
- Статус: **этап 1 done; этап 2 done** (в объёме ниже); визуальная проверка — headless Chromium, ручная проверка человеком не выполнялась

## Входные SHA (research/round-4/snapshots.json)
- K10 `claude/save-work-handoff-j7pc05` @ `ea703f1ddd3a411430a981164a78a7dda64ec909` (данные 602f0c0)
- K07 `claude/save-work-handoff-ku3ej3` @ `6778deda6d3f3a7f27698f651c1b0046d2a9aae9`
- K03 `claude/epic-curie-iitc43` @ `44585de31be01dd131ecb7677c462fc85b4d4cc4`
- K05 `claude/optimistic-davinci-1oiqs9` @ `d913554bf2617a74d921af260ab8c22743ccb4b5`
- K02 `claude/clever-mccarthy-pywscu` @ `24c1750f70d9e444ae551030d116bb6aa8ce5b7b`
- K08 `claude/dazzling-mayer-drhsxk` @ `e1e3c7170f827550948afc0448695ecb8e9bc464`; K04 @ `7fb8bb8`
- Все копии (40 файлов) с SHA256: `prototypes/city-evidence/source_manifest.json`. Ветки не сливались.

## Сделано
Этап 1: viewer K07 на компактных квадратах K10 r3; город/слои/фильтр/карточки/таблица/пустые состояния/рамка; file:// и `serve.py`.
Этап 2:
- `tools/build_evidence.py`: K03 `assign()` для каждой записи (без правок кода K03), 19 наблюдений k05-obs-v1.1 на город, проверка K05 `validate()`; ошибки K05 останавливают сборку (по ходу исправлены 3 реальные ошибки моих записей, найденные валидатором).
- `web/facts.js`: каталог фактов по городу/фильтру/срезу, заглушка-селектор (только ID), порт K02 `validate_plan`/`render`; подпись «шаблонное объяснение … не LLM»; устаревший ответ после смены города/фильтра отбрасывается.
- UI: район (ru/kk) или «не присвоен» с кандидатами; каталог фактов с «нет данных» ≠ 0; источники с K03/K05/K08.

## Реально запущенные проверки (2026-10-05, Linux)
- `inputs/k10/scripts/offline_check.py` → ok: true, errors [] (код прочитан: только чтение, сокеты заблокированы).
- `tools/build_evidence.py` → Шымкент 55/55 matched (Әл-Фараби 41, Еңбекші 14), Астана 65/65 matched (Байқоңыр 34, Сарыарқа 31); ошибок K05 0; предупреждения только PARTIAL_COVERAGE.
- `python -m unittest discover -s tests` (venv с shapely 2.1.2/pyproj 3.7.2): 7/7 OK — битый файл, отсутствующий файл и манифест отклоняются; K03 selftest (все 5 статусов) проходит; точка-тройник → ambiguous без района; K05 ZERO_ON_PARTIAL. Без shapely: 5 OK, 2 skipped.
- `node tests/conformance.cjs`: 18/18 — текст JS = K02 Python в 6 случаях (ru/kk, разные фильтры); unknown_id, foreign_city, stale_scenario, not_an_id, null_as_fact, value_in_gaps; null vs 0.
- Тесты K02 на скопированном модуле (`pytest`, venv + numpy): 16 passed.
- `tests/smoke.cjs` (Playwright Chromium, file://): 16/16 — оба города, сброс при переключении, фильтр, пустое состояние, карточка дороги без «минут», 380 px без горизонтальной прокрутки, районы, шаблонное объяснение, отброс устаревшего ответа, карточка источников, отсутствующие data.js/evidence.js, 0 ошибок консоли, 0 сетевых запросов. Скриншоты: `smoke/`.
- `serve.py`: index, data.js, evidence.js, facts.js, app.js → HTTP 200 на 127.0.0.1.

## Ограничения
- Квадраты ~2×2 км; Overture вторичен и неполон; районы юридически не проверены.
- ambiguous/unmatched на реальных записях этих квадратов не встретились (проверены синтетикой K03).
- LLM не подключён (не требовался); kk-подписи — черновик.
- Ручная проверка человеком в обычном браузере и ОС, кроме Linux, не выполнялась.

## Следующий шаг
Показ владельцу; при выборе — расширение квадратов или выгрузка K10 для одного района целиком, затем маршрутный режим только после проверки прав прохода (graph_check K07).
