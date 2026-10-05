# BUILD раунд 4 — STATUS

- owner_branch: `claude/beautiful-clarke-sbzomj` (единственный сборщик BUILD, назначен пользователем 2026-10-05)
- Пути: `prototypes/city-evidence/`, `research/round-4-results/BUILD/`
- Задание: `research/round-4/BUILD.txt` @ `codex/research-import-2026-10-05` `cadba4d200387b9a97cb2d1c5aa0a8fd5a150c1e`
- Статус: **этап 1 done; этап 2 — in_progress**

## Входные SHA (из research/round-4/snapshots.json)
- K10 `claude/save-work-handoff-j7pc05` @ `ea703f1ddd3a411430a981164a78a7dda64ec909` (данные коммита 602f0c0): package_manifest.json, data/{shymkent,astana}/{places_social,segments,connectors}.geojson, scripts/offline_check.py, geo_util.py, k10_rules.py.
- K07 `claude/save-work-handoff-ku3ej3` @ `6778deda6d3f3a7f27698f651c1b0046d2a9aae9`: prototype/index.html, prototype/app.js (основа viewer).
- Все копии с SHA256 — `prototypes/city-evidence/source_manifest.json`.

## Сделано (этап 1)
- Viewer K07 перенесён и переведён на компактные квадраты K10 раунда 3 (Шымкент 55 записей / 1 084 сегмента; Астана 65 / 1 326).
- Переключатель города со сбросом состояния, слои объектов/дорог, фильтр категорий, карточки объекта/дороги/источника, таблица, расстояние по прямой с подписью, понятные пустые/ошибочные состояния, рамка квадрата и подписи неполноты.
- Запуск: `python3 serve.py` или открыть `web/index.html` (file://).

## Реально запущенные проверки
- `python3 inputs/k10/scripts/offline_check.py` → `ok: true`, errors [] (SHA256/размеры/число объектов совпали с манифестом K10; код прочитан перед запуском: только чтение файлов, сокеты заблокированы).
- `python3 tools/build_data.py` дважды → одинаковый `web/data.js`.
- `tests/smoke.cjs` (Playwright Chromium, file://): 9/9 PASS — загрузка Шымкента, карточка из таблицы, сброс при переключении на Астану, фильтр (8 школ в срезе Астаны), пустое состояние, карточка дороги без «минут», ширина 380 px без горизонтальной прокрутки, 0 ошибок консоли, 0 сетевых запросов. Результат и скриншоты: `research/round-4-results/BUILD/smoke/`.
- Скриншоты просмотрены глазами (1280 и 380 px).

## Ограничения
- Квадраты ~2×2 км, не города; Overture — вторичный, неполный источник.
- Права прохода у большинства сегментов неизвестны → только режим просмотра дорог.
- Район не присваивается (этап 2: K03).
- Проверено только на Linux.

## Следующий шаг
Этап 2: адаптеры K03 (районы с ambiguous/unmatched), K05 (unknown ≠ 0), K02 (детерминированное объяснение по ID фактов, selector=stub) → `web/facts.js`; тесты адаптеров.
