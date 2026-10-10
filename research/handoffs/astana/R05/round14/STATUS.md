# R05 · раунд 14 · 3D-превью предложений — STATUS

Ветка: `claude/r14-R05` (от `claude/round-14-package` @ 7ff639a). Пушить только в неё.
Обновлено: 2026-10-10, checkpoint 2.

## Сделано
- three.js 0.169.0 положен в `web/vendor/three/` из npm (`npm pack`, целостность sha512 совпала с реестром) — LOCAL-2 больше не блокирует; см. `web/vendor/three/SOURCE.txt`.
- `web/civic/build3d/build3d-core.js` — ядро без DOM: каталог 5 видов, меркатор как в MapLibre, локальные метры,
  точки через ~30 м, индекс улиц (участок между двумя точками по рёбрам одной улицы, форма OSM), районы,
  проверка места (город / наложение / лимит 20), хранилища предложений: API R06 и локальная заглушка.
- `web/civic/build3d/build3d-models.js` — процедурные low-poly модели: сквер, детская площадка, спортплощадка,
  остановка, освещение (опоры вдоль участка). Габариты проверены в Node.
- Фикстуры из реального графа OSM: `web/civic/build3d/data/nura-streets.json` (924 ребра, 59 улиц Нуры),
  `astana-districts.json`, `demo-basemap.json` — генератор `tests/civic/R05/build3d/make_fixtures.py`.

- `web/civic/build3d/build3d.js` + `build3d.css` — custom layer MapLibre + three.js, каталог, призрак (мышь/центр карты),
  поворот ↺ ↻ (остановка сама встаёт вдоль улицы), «Поставить», анимация постройки 1.2 с с пылью, подписи
  «Проект · 2027», карточка с голосами, «Отменить»/«Удалить», тосты. Проверено вручную в Playwright (swiftshader):
  все 5 объектов ставятся, освещение — по рёбрам ул. Сыганак (184 м → 7 фонарей).
- `web/civic/build3d/demo.html` — демо без интернета (подложка из улиц OSM).
- `data/proposals.fixture.json` — 2 примера (demo:true) по CONTRACT §7, генерируются make_fixtures.py.

## Следующий шаг
1. Тесты: tests/civic/R05/build3d/ (Node: ядро, модели, фикстуры; Playwright: размещение, перезагрузка без анимации,
   точность при наклоне 0°/60° и повороте, освобождение памяти, лимит 20, kk, 375 px).
2. Скриншоты 1366/375 × ru/kk × 0°/60° → research/round-14-results/R05/screens/.
3. DELIVERY.json, RUN.txt, INTEGRATION.txt (R01: ASSETS + подключение; R06: поля и DELETE; R11: ключи build3d.*; R12: событие).
