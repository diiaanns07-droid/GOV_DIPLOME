# R05 · раунд 14 · 3D-превью предложений — STATUS

Ветка: `claude/r14-R05` (от `claude/round-14-package` @ 7ff639a). Пушить только в неё.
Обновлено: 2026-10-10, checkpoint 1.

## Сделано
- three.js 0.169.0 положен в `web/vendor/three/` из npm (`npm pack`, целостность sha512 совпала с реестром) — LOCAL-2 больше не блокирует; см. `web/vendor/three/SOURCE.txt`.
- `web/civic/build3d/build3d-core.js` — ядро без DOM: каталог 5 видов, меркатор как в MapLibre, локальные метры,
  точки через ~30 м, индекс улиц (участок между двумя точками по рёбрам одной улицы, форма OSM), районы,
  проверка места (город / наложение / лимит 20), хранилища предложений: API R06 и локальная заглушка.
- `web/civic/build3d/build3d-models.js` — процедурные low-poly модели: сквер, детская площадка, спортплощадка,
  остановка, освещение (опоры вдоль участка). Габариты проверены в Node.
- Фикстуры из реального графа OSM: `web/civic/build3d/data/nura-streets.json` (924 ребра, 59 улиц Нуры),
  `astana-districts.json`, `demo-basemap.json` — генератор `tests/civic/R05/build3d/make_fixtures.py`.

## Следующий шаг
1. `web/civic/build3d/build3d.js` — custom layer MapLibre + three.js, призрак, поворот, «Поставить», анимация, подписи «Проект · 2027».
2. `build3d.css`, `demo.html`, фикстура предложений.
3. Тесты Node + Playwright, скриншоты, DELIVERY/RUN/INTEGRATION.
