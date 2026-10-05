# K03, раунд 7: проверка координат точек по bbox среза (city-whatif-v1)

Это маленький помощник для функции «Если добавить объект» (`research/round-7/FEATURE_SPEC.txt`). Он решает, можно ли принять контрольную точку или проектный объект в текущем срезе. Общий прототип не изменён: интеграцию делает сборщик.

## Правило `checkPoint(slice, point, otherSlices)`

`slice` = `{city_id, bbox: [W, S, E, N], edges_inclusive}` из `web/evidence.js → cities.<город>.spatial_unit` (совпадает с `web/data.js`). `point` = `[долгота, широта]` или `{id, lon, lat[, category, kind]}`.

Порядок проверок:
1. `bad_slice`
2. `bad_shape` (не пара, лишние поля — например, URL)
3. `not_number` (null, строка, bool)
4. `not_finite` (NaN, ±Infinity, 1e999, слишком длинное целое) — **до** сравнений, потому что любое сравнение с NaN ложно
5. `out_of_range`
6. попадание в bbox: `inside` или `on_edge`
7. `lon_lat_swapped` — перестановка в bbox попадает. Только распознаётся, не исправляется
8. `other_city` — точка в квадрате другого города, не переносится
9. `outside_bbox`

Принимаются только `inside` и `on_edge`. Сравнение точное, без допуска и округления: при `edges_inclusive=true` границы включены, точка на 1e-9° снаружи отклоняется.

**Район не проверяется и не требуется.** В браузере нет полигонов районов, и это правильно: точка на общей границе районов внутри квадрата — допустимая контрольная точка или гипотетический объект. В fixtures `k03_info` — справка K03 (`informational_only`, `legal_status: not_verified`), а не условие приёма и не официальная принадлежность.

## Файлы

| Файл | Что |
|---|---|
| `point_check.js` | помощник для браузера и node (UMD → `window.K03_POINT_CHECK.checkPoint`), без зависимостей |
| `point_check.py` | эталон тех же правил (stdlib) |
| `fixtures.json` | 41 случай: центр, углы, стороны, ±1e-9°, перестановка, другой город, далеко, NaN/Infinity/1e999/длинное целое, null/строка/bool, форма, диапазон, плохой bbox, `edges_inclusive=false`; гипотетический объект на границе районов внутри квадрата и в 0,5 / 5 м от неё; точки спорных зон AST-Z1/Z2/Z3 |
| `make_fixtures.py` | пересоздать fixtures для конкретной сборки (`--app-root`, `--target-sha`) |
| `test_point_check.py` + `test_point_check.cjs` | прогон Python и JS на fixtures, их паритет и сверка bbox с проверяемой сборкой |
| `runs/` | результаты реальных прогонов на c58a3b2 и отрицательные контроли |

## Как сборщику использовать

1. Скопировать `point_check.js` в `web/` и подключить до `app.js`. Перед добавлением или перемещением точки и при импорте сценария вызывать `checkPoint(sliceOf(city), [lon, lat], otherSlices)`. При `ok=false` показать `message` и точку не принимать.
2. Проверить интегрированную копию:
   ```bash
   python3 research/round-7-results/K03/test_point_check.py --app-root <копия> --js <копия>/web/point_check.js
   ```
3. Если bbox среза изменился, тест вернёт `TEST_INCOMPATIBLE`. Тогда fixtures пересоздаются `make_fixtures.py` для нового SHA.

Встроенная проверка режима точки `web/app.js:416` считает NaN «внутри квадрата» (`runs/negative_controls.txt`). Клик по карте NaN не даёт, а импорт JSON может. Поэтому для новых путей ввода лучше использовать помощник.
