# K08 R8 — API модулей

Все модули — Python 3 stdlib, без сети. `APP` — извлечённая `prototypes/city-evidence` (читаются `web/data.js`, `web/evidence.js`, `inputs/k10/...`).

## planlib.py (city-plan-v2, CORE_SPEC)
| Функция | Что делает |
|---|---|
| `Context(app_root)` | срез: города, записи, bbox, release, файлы, QA (`evidence.js`), sha256 `data.js`/`evidence.js` |
| `source_snapshot(ctx, city, schema="city-plan-v2")` | `sha256(JSON.stringify([schema, city, release, places_file.sha256, placesDigest, "haversine:R=6371008.8"]))` — та же формула, что `sourceSnapshot` в `web/whatif.js`; для `schema="city-whatif-v1"` совпадает с JS сборки побайтно |
| `loads_strict(text|bytes)` | ≤256 KiB; дубликаты ключей, NaN/Infinity/1e999, целые >2^53 → `PlanError` |
| `validate_plan_scenario(obj, ctx)` | проверенный сценарий или `PlanError(code, message)`. Коды: `bad_version`, `bad_city`, `bad_category`, `foreign_snapshot`, `outside_bbox`, `bad_coords`, `bad_weight`, `bad_cost`, `duplicate_id`, `unknown_ref`, `conflict`, `unexpected_field`, … `derived_results` разрешён и игнорируется |
| `evaluate_plan(ctx, sc, ids)` | `{selected_ids, rows[{id, weight, before_mm, after_mm, delta_mm, nearest_before/after{kind: source\|hypothetical, id}}], metrics, feasibility}` |
| `optimize_plans(ctx, sc, budget=None)` | точный перебор ≤16 кандидатов: `{status: optimal\|infeasible, objectives{mean, minimax, coverage}, pareto, evaluated, feasible_count, problem_digest, metric_version, search: "exhaustive", infeasible_reasons?}` |
| `sensitivity(ctx, sc)` | бюджеты `sorted({0, B//2, B})` |
| `problem_digest(sc)` / `scenario_digest(sc)` | не зависят от порядка массивов; `selected_ids` только в `scenario_digest` |
| `plan_result(ctx, sc)` | вход генератора: сценарий, digests, context (snapshot, bbox, release, файлы, пакет K10, атрибуция), планы (manual + 3), optimization, sensitivity, `source_records` (sources, лицензия, QA) |

Метрика `haversine-mm-v1`: гаверсинус R = 6371008.8, clamp [0, 1], `floor(d_m*1000 + 0.5)` мм. Ничьи — по ключу `source:<id>` / `hypothetical:<id>`.

## report.py
| Функция | Что делает |
|---|---|
| `build_report(plan_result, generated_utc)` | `report.json` (`report_schema: k08-plan-report/v1`): source, scenario, plans, optimization, sensitivity, source_records, comparison{groups, explanation}, classes, assumptions, limitations |
| `render_html(meta)` | самодостаточный HTML: без `<script>` и внешних ресурсов, CSP `default-src 'none'`, весь текст через `html.escape`, ссылки из пользовательских полей не создаются |
| CLI | `python report.py --app-root APP build SCENARIO.json --out-dir DIR [--generated-utc T]` |

## verify_report.py
`verify_report(meta, ctx)`:
- `ok` — пересчёт совпал; `warnings`, если изменился общий `data.js`/`evidence.js`, но не срез отчёта;
- `stale` — snapshot не совпадает (с причиной: data.js / файл мест / release) или изменились QA-метки сборки;
- `tampered` — любое derived/источниковое поле не совпадает с пересчётом (путь поля) или источник записи не совпадает с исходным GeoJSON пакета K10;
- `rejected` — неизвестная `report_schema`, версия сценария или `metric_version`.

CLI: `python verify_report.py --app-root APP REPORT.json` (exit 0 только при `ok`).

## make_fixtures.py
`python make_fixtures.py --app-root APP --out fixtures` — 3 сценария над реальными срезами. Входы synthetic (`fixtures/fixtures_manifest.json`).
