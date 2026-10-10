# R12 · раунд 14 · Точность карты — handoff

- Роль: R12 (точность карты). Ветка сессии: `claude/tender-brahmagupta-ef5ztl`.
- Основа: `claude/round-14-package` @ af77b78 (ветка сессии переставлена на неё до начала работы; своих коммитов до этого не было).
- Примечание о запуске: сообщение пользователя называло роль R12, но ссылалось на prompts/R11.txt. Выполняется
  prompts/R12.txt: роль названа явно и аккаунт s8 в ROLES.json закреплён за R12.
- Мои пути: engine/civic_geo/, data/civic/astana/geo/, web/civic/map/, web/civic/editor/, tests/civic/R12/,
  research/round-14-results/R12/, этот файл.

## Checkpoint 1 — восстановление (PARTIAL)
- web/civic/map/{civic-map-core.js,civic-map.js,civic-map.css} из claude/zen-mendel-e79iiv код f0a52f7 (голова 7de5e0b);
  streets.json не менялся (база).
- web/civic/editor/* из claude/intelligent-sagan-7shpeh @ 9c996c6.
- Прочитаны: research/handoffs/astana/R03/round-13/STATUS.md, research/round-13-results/R03/{DELIVERY,INTEGRATION,RUN}
  (на 7de5e0b); research/handoffs/astana/R04/round-13/STATUS.md (на 9c996c6).
- Тесты раунда 13 перенесены в tests/civic/R12/map/ (из tests/civic/R03 @ f0a52f7) и tests/civic/R12/editor/
  (из tests/civic/R04 @ 9c996c6) — пути к репозиторию поправлены на одну папку глубже. В раунде 14 tests/civic/R03 и R04
  принадлежат другим ролям, поэтому там ничего не меняю.
- Проверено на этой ветке (Linux, Node 22, Playwright глобально, Chromium /opt/pw-browsers):
  map core 26/26, map browser 69/69, editor core+mock 40/40, editor e2e+e2e_r13 39/39 — PASS.

## Дальше
engine/civic_geo (граф, индекс, ближайшее ребро, участок улицы, targets, проверки точности, CLI) → data/civic/astana/geo
→ demo_snapped.json и отрисовка → инструмент «Участок улицы» в редакторе → /targets.

## Checkpoint 2 — engine/civic_geo и данные (PARTIAL)
- engine/civic_geo/ (только stdlib): geo.py (метры, проекция, обрезка ломаной, полигоны, упрощение),
  graph.py (граф OSM по MANIFEST + sha256, сетка 100 м, ближайшее ребро), segment.py (участок улицы по рёбрам,
  предпочтение одной улицы), objects.py (объекты/дворы/ячейки 150 м), targets.py (1–3 кандидата по
  target_kinds из categories_v2.json), accuracy.py (CONTRACT §8), api.py (функции для R01), snap_demo.py,
  build_way_tags.py, build_geo_data.py, __main__.py (CLI report/targets/segment/bench).
- data/civic/astana/geo/: way_tags.json (34 380 линий), objects.json (20 настоящих остановок из снимка пешеходной сети),
  yards.json пуст (нет LOCAL-1), cells.json, demo_snapped.json, SOURCE.json, README.md.
- Отчёт точности: 34/34 PASS; /targets p50 0,19 мс, p95 0,47 мс (3000 точек, после загрузки графа 1,5 с).
- tests/civic/R12/test_civic_geo.py — 21/21 PASS (синтетическая фикстура + настоящий граф).

## Checkpoint 3 — карта рисует улицы по OSM (PARTIAL)
- web/civic/map: demo_snapped.json применяется по id и только при неизменной исходной геометрии; привязанная линия —
  сплошная, с подписью улицы (если у стиля есть шрифты); «примерное место» — мягкая область 120 м (или круг вокруг
  непривязанной линии/площади), уверенной линии нет; плоские слои — под 3D-зданиями хоста (и если хост добавит 3D
  позже), значки — над ними; в списке/подсказке/карточке «По улице» / «Участок улицы по карте OSM: …».
- Слоёв модуля стало 15 (+2 для «примерного места»; +1 подпись улицы при glyphs). Тесты R12/map обновлены.
- tests/civic/R12/map/r12_accuracy.test.mjs 4/4 PASS; core 28/28 PASS.
- Скриншоты: research/round-14-results/R12/screenshots/before-closure-1366.png, after-closure-1366.png, after-closure-375.png
  (подложка — оси улиц OSM из графа: OpenFreeMap в облаке 403).

## Checkpoint 4 — редактор: точная отметка (PARTIAL)
- web/civic/editor/editor.js: вместо «Линия от руки» — «Участок улицы» (1-е нажатие прилипает к оси улицы через
  /street-snap, 2-е строит участок по рёбрам через /street-segment, предпросмотр, «Готово»; «Проезжая часть / Тротуар»;
  новое нажатие перестраивает конец; гонка нажатий отсекается счётчиком); «Выбрать двор» (/yard) и «Площадь по углам»;
  после точки — подсказка «Рядом есть объект OSM» (/objects-near) и привязка одним нажатием; у линии по улице нет
  «Изменить вершины»; ошибки понятными словами (не у улицы / привязка не подключена / нет связи); o.geo=false — выкл.
- engine/civic_geo/api.py: snap_response, near_response, yard_response, handle(path, query) — один вход для R01.
- Стенд редактора: тестовый (СИНТЕТИЧЕСКИЙ) клиент геоданных; 5 старых тестов переведены с tool-line на tool-segment.
- Проверки: editor e2e+e2e_r13+joint 41/41, e2e_r12 7/7, map browser 69/69, civic_geo 21/21 — PASS.
