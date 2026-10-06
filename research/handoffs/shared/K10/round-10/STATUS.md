Задача / идентификатор: round-10 · K10 · «Астана: отдельные реальные данные и проверка переноса» (research/round-10/prompts/K10.txt @ codex/govtech-main-interface 7c6fb75)
Агент / город / сфера: K10 / astana (+ проверка переноса Шымкент ↔ Астана) / данные школ, case-пакет, перенос сценария
Обновлено: 2026-10-06, UTC
Статус: partial (этапы 0–2 готовы, этап 3 в работе)
Рабочая ветка: claude/save-work-handoff-j7pc05
Исходный коммит: 657db5207a2c92d1f64fd94f39ba98f56cc30fa8 (последний коммит прежней сессии K10, r9; роль принята по назначению пользователя)
Назначенные пути: research/round-10-results/K10/, research/handoffs/shared/K10/round-10/STATUS.md
Кодовая база: d2ff344c5ec9b9a729ea59df50ec81f981e619de (BUILD 5f81e4d — тот же код; импорта school-access-case-v1 нет)

Сделано:
- Доступ: официальные сайты РК, OSM, Wikidata, 2GIS — NOT_FETCHED (403 CONNECT); доступен бакет Overture. 0 школ сверено с официальным источником.
- Сопоставлены все 8 записей группы «Школа» среза Астаны (d2ff344):
  - 2 подтверждены двумя вторичными слоями (POI + участок OSM + здание OSM);
  - 4 — не школы: 3 учебных центра и «Почемучка» (по OSM детский сад / центр развития);
  - 1 — частная международная (restricted);
  - 1 — конфликт местоположения (СШ №8).
  Ещё 4 участка школ OSM внутри bbox в срезе отсутствуют.
- Пакет package/astana.case.json (school-access-case-v1) с schools/sources/evidence/match-review/MANIFEST:
  - 40 школ в bbox и буфере 2100 м: 29 known_public (вывод из названия), 6 restricted, 5 unknown;
  - 23 derived-точки (жилые здания OSM, не жители) и 3 гипотезы (не участки).
- Буфер: D = 1373 м по сетке 25 м, B = ceil100(1,5·D) = 2100 м; множитель 1,5 — допущение.
- scripts: overture_bbox → make_inputs → build_astana_package (байт в байт); k10case.py — stdlib-валидатор, digest k10-canon-v1 (предложение), проверка переноса.
- tests: 11 OK (33 мутации отклоняются; digest не зависит от порядка; пересборка идентична; перенос на SYNTHETIC мини-кейсе Шымкента).

Проверки:
- python3 -m unittest discover -s research/round-10-results/K10/tests -v → 11 OK (venv с shapely/pyproj); stdlib — 10 OK + 1 SKIP.
- k10case.py validate package/astana.case.json --max-school-buffer-m 2100 → OK.
- Не запускалось: UI-импорт (в BUILD нет импорта school-access-case-v1) — NOT_RUN; официальная сверка — NOT_FETCHED.

Ограничения: см. research/round-10-results/K10/STATUS.md («Ограничения»).
Следующий шаг: этап 3 — смена города на настоящей странице d2ff344; UI-import smoke для нового BUILD_SHA.
Для воспроизведения: research/round-10-results/K10/STATUS.md («Команды»).
Конфликты: общий код меняет только BUILD (K04). K01 делает Шымкент по тому же CONTRACT; K10 не пишет в его папку. digest k10-canon-v1 — предложение, канон — BUILD.
