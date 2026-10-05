# whatif.js — API и JSON (city-whatif-v1), K05 round 7

Отдельный модуль, готовый к подключению. В общий прототип не встроен. Спецификация — `research/round-7/FEATURE_SPEC.txt` @ 7927fa8. Проверялся на данных сборки `c58a3b2b175cf978ad785fef7f88d8fd9b1338f2` (`prototypes/city-evidence/web/data.js`, `evidence.js`).

## Подключение (для сборщика)
```html
<script src="whatif.js"></script>   <!-- после data.js и evidence.js; даёт window.CITY_WHATIF -->
```
```js
const W = window.CITY_WHATIF;
const ctx = W.makeContext(city, window.CITY_EVIDENCE.cities[city], window.CITY_OBS.cities[city]); // 3-й аргумент — запись города из evidence.js (нужен .qa)
const scn = { schema_version: W.SCHEMA, city_id: city, source_snapshot: ctx.snapshots[cat], category: cat,
              control_points: [{id:"c1", lon, lat}], proposed_object: null | {id, lon, lat, category: cat, kind: "hypothetical"} };
const v = W.validateScenario(scn, ctx);         // {ok, errors[]}: показать errors как текст (textContent)
const result = W.compute(ctx, scn);             // бросает Error, если сценарий невалиден
const {text, digest} = W.explain(result);       // шаблон, не LLM
const json = JSON.stringify(W.exportScenario(scn, result));
const imp = W.parseImport(text, ctx);           // {ok, errors, scenario}; result из файла отбрасывается
const {reset, reason} = W.resetOnChange(prevScn, {city_id, category});
```
Node: `const W = require("./whatif.js")`.

## Правила расчёта (по спецификации)
- Расстояние: гаверсинус, R = 6371008.8 м, вход `[lon, lat]`, промежуточное значение зажато в [0, 1]. Округление — только при выводе (`explain` округляет до метра).
- База — записи `cities[city].places` с `group == category`; квадрат среза, не город. С городскими наблюдениями не складывается.
- `before` — минимум по исходным записям. При равных расстояниях берётся меньший `id`, длина от этого не меняется.
- `after = min(before, d_proj)`; при равенстве источником остаётся существующая запись (`after_source: "existing"`), `delta = 0`.
- Если записей нет: `before = null`, `after = d_proj` (или `null` без проекта), `delta = null`, `note` = «В срезе нет исходных записей; улучшение не вычисляется».
- Без проекта: `after = before`, `delta = 0`, если `before` известен.
- `delta = before − after ≥ 0` — только уменьшение расстояния по прямой.
- QA-флаги ближайшей записи (`category_doubt:*`, `colocated:N`, `possible_duplicate:*`) передаются в `before_record.qa_flags`. Записи не удаляются. Отсутствие флага не означает «проверено».
- `before_record.kind = "observed_secondary"`, проект — `kind: "hypothetical"`; они не смешиваются.

## source_snapshot
`"wif1-sha256:" + sha256(canon({schema, city_id, category, release, places_sha256, bbox, records: [[id, lon, lat], …] по id, params}))`. Отпечаток считается из фактических записей категории и параметров расчёта; имя файла не принимается (`SNAPSHOT_MISMATCH`). На c58a3b2:

| город | school | outpatient_clinic |
|---|---|---|
| shymkent | `wif1-sha256:5dc3255eb1ed72ef1a050e0fe12bd0d8cad710467d662b1c77e295948e835454` | `wif1-sha256:fefec30ff78af31a994e700d61f24cb0291fe307971c131c6d00e1dce78f9438` |
| astana | `wif1-sha256:25aeca19200e7ab9f9a2b22877efafa9515264d38f3a64c75518209a02dd5d15` | `wif1-sha256:a3563f9144d7498ffa13ff07fc994f25c86a5f9a73afea53383b332b5bc515d5` |

## Результат `city-whatif-result-v1`
```json
{ "schema_version": "city-whatif-result-v1", "scenario_schema": "city-whatif-v1",
  "city_id": "shymkent", "category": "school", "source_snapshot": "wif1-sha256:…", "release": "2026-09-23.1",
  "bbox": [xmin, ymin, xmax, ymax], "n_source_records": 15,
  "formula": {"name": "haversine", "radius_m": 6371008.8, "straight_line": true, "units": "m", "rounding": "только при выводе"},
  "proposed_object": null | {"id", "lon", "lat", "category", "kind": "hypothetical"},
  "rows": [{ "point_id", "lon", "lat", "before_m": number|null,
             "before_record": {"id", "name", "lon", "lat", "kind": "observed_secondary", "qa_flags": []} | null,
             "distance_to_proposed_m": number|null, "after_m": number|null,
             "after_source": "existing"|"proposed"|null, "delta_m": number|null, "note": string|null }],
  "limitations": ["…5 строк…"] }
```

## Валидация и импорт (коды ошибок)
`SCHEMA_VERSION`, `CITY`, `CITY_MISMATCH`, `CATEGORY`, `SNAPSHOT_MISMATCH`, `CONTROL_POINTS` (1..10), `DUPLICATE_ID` (точки и проект вместе), `id` 1–64 символа `[A-Za-z0-9_.-]`, конечные координаты в диапазоне, `OUTSIDE_BBOX`, `PROPOSED` (один, `kind=hypothetical`, категория = `category`), `UNKNOWN_FIELD`, `FORBIDDEN_CONTENT` (URL/код). Импорт дополнительно: `IMPORT_TOO_LARGE` (> 256 KiB), `JSON` (синтаксис, в том числе NaN), `JSON_DUPLICATE_KEY`, `JSON_NONFINITE` (1e999). Поле `result` из импорта не доверяется: отбрасывается и пересчитывается. Адреса из импортированного текста не загружаются, модуль не делает сетевых запросов.

## Ограничения модуля
- Интерфейс (карта, кнопки, таблица) не реализован: это задача сборщика.
- Казахский шаблон объяснения не сделан (`lang` пока игнорируется).
- `duplicateKey` — простой сканер, рассчитанный на корректный после `JSON.parse` текст.
