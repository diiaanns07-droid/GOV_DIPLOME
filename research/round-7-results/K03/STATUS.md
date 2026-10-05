# K03 round 7 — «Принадлежность точек и границы»: STATUS

| Поле | Значение |
|---|---|
| Слот | K03 (`research/round-7/tasks/K03.txt` @ `7927fa8`), не BUILD |
| Ветка | `claude/epic-curie-iitc43` |
| База (проверенный SHA) | `claude/beautiful-clarke-sbzomj` @ **`c58a3b2b175cf978ad785fef7f88d8fd9b1338f2`**, `prototypes/city-evidence/`. Код совпадает с кандидатом `b3e4dc4`: `git diff` по папке прототипа пуст, проверено мной |
| Обновлено | 2026-10-05, ~09:40 UTC |
| Статус | **done** для объёма задания. Это помощник, fixtures и тест; в прототип **не интегрировано**, функция «Если добавить объект» в сборке не проверялась |

## Сделано

- `point_check.js` / `point_check.py` — проверка координат контрольной точки и проектного объекта по bbox текущего среза. Правила — в `README.md`. Район не требуется: `ambiguous` на границе районов внутри квадрата допустим.
- `fixtures.json` — 41 случай, построенный из bbox сборки c58a3b2 (`web/evidence.js` spatial_unit = `web/data.js`), с ожидаемым исходом по правилу и пояснением.
  - Справка K03 для 11 точек взята из модуля сборки `inputs/k03v21_root` (`k03_info`, только информационно, `not_verified`):
    - центры квадратов → `matched`;
    - гипотетический объект на общей границе Байконур/Сарыарка и Әл-Фараби/Еңбекші внутри квадрата → K03 `ambiguous`, но bbox-проверка **принимает** (`inside`); в 5 м от границы → `matched`;
    - точки спорных зон AST-Z1 (эксклав, `ambiguous`), AST-Z2 (без района, `unmatched`), AST-Z3 (полоса версий, `ambiguous`) лежат вне квадрата и отклоняются **по bbox** (`outside_bbox`), а не по району.
- `make_fixtures.py`, `test_point_check.py`, `test_point_check.cjs`, `README.md` — с указанием, как сборщику подключить помощник и перепроверить интегрированную копию.

## Реально выполненные проверки (на извлечённой копии c58a3b2)

- `python3 research/round-7-results/K03/make_fixtures.py --app-root <копия> --target-sha c58a3b2…` → 41 fixture (K03 вызывался через shapely 2.1.2 / pyproj 3.7.2).
- `python3 research/round-7-results/K03/test_point_check.py --app-root <копия>` → **PASS 4, FAIL 0, SKIP 0** (`runs/test_c58a3b2.json`):
  - bbox и `edges_inclusive` обоих городов совпадают с fixtures;
  - Python 41/41;
  - JS (node v22.22.0) 41/41;
  - паритет Python/JS — 0 расхождений.
- Отрицательный контроль (`runs/negative_controls.txt`): копия JS без проверки конечности → 4 расхождения, FAIL; с игнорированием `edges_inclusive` → 6, FAIL.
- Встроенная проверка `web/app.js:416` в c58a3b2 при NaN считает точку внутри квадрата. Воспроизведено в node; клик по карте такого не даёт.

Не запускалось: браузерный smoke и тесты сборки — прототип не менялся; проверка интеграции в UI — её ещё нет.

## Ограничения

- Проверяются только координаты по bbox. Остальной контракт city-whatif-v1 (ID, `schema_version`, `source_snapshot`, категория проекта, лимит 256 KiB, строгий JSON) — вне этого помощника.
- Сравнение точное: точку на 1e-9° за стороной квадрата отклоняем; это сознательно, без допуска.
- `k03_info` — справка по данным OSM/Overture, юридически не проверена.
- Попутно замечено и не перепроверялось в этом раунде: в `inputs/k03v21_root` реестр и `validator_selftest.json` по-прежнему с меткой `k03_assign_v1`. Это находка I3 раунда 6.

## Следующий шаг

Сборщик подключает `point_check.js` к добавлению, перемещению и импорту точек и запускает:

```bash
python3 research/round-7-results/K03/test_point_check.py --app-root <копия нового SHA> --js <копия>/web/point_check.js
```

После этого K03 может проверить интеграцию на конкретном SHA.

## Воспроизведение

```bash
git fetch origin claude/beautiful-clarke-sbzomj
python3 research/round-5-results/K03/extract_build.py --sha c58a3b2b175cf978ad785fef7f88d8fd9b1338f2 --out /tmp/app7
python3 research/round-7-results/K03/test_point_check.py --app-root /tmp/app7          # нужен node для JS-части
python3 research/round-7-results/K03/make_fixtures.py --app-root /tmp/app7 --target-sha c58a3b2b175cf978ad785fef7f88d8fd9b1338f2   # shapely+pyproj
```
