# R07 — Симулятор: сравнение вариантов работ и объяснение своего результата (раунд 13, Астана)

- Роль: R07; ветка сессии `claude/brave-hopper-bkc58b` — та же сессия, что делала R07 раунда 11 (22fa413)
  и R06 раунда 12 (1139eeb). R07 раунда 12 в этой и других ветках нет (проверено по всем origin/*).
- REFERENCE_BASE_SHA: 56538a3a7504d4589c38ab4d3c5107f12aa7f8a6; пакет раунда 13: origin/codex/govtech-main-interface @ c076569
- Пути: engine/civic_scenarios/, web/civic/scenarios/, tests/civic/R07/, tests/civic/test_citywide_osm.py,
  data/civic/astana/osm-walking/, web/civic/map/streets.json, research/round-13-results/R07/, этот файл
- Источник соседей для проверки: R09 claude/fervent-dijkstra-1cqrg5 @ f2ebaf9 (code f8aea9a);
  R01 claude/affectionate-ride-bol5v8 @ 6dc1660 (code 223296e)

## BASE_MISMATCH
Ветка основана на старом main; перевод на 56538a3 merge-коммитом ранее отклонён правилами среды.
Разработка и проверки — в worktree от 56538a3; в ветке — пути R07 (= 56538a3 + изменения) и
`research/round-13-results/R07/r07_vs_56538a3.patch` (git apply --check на чистом 56538a3).
Данные OSM и граф 28.8 МБ — побайтно те же blob'ы, что в 56538a3 (не пересобирались).

## Checkpoint 1 — PARTIAL
DONE: engine 1.1.0 — snap.py (точка -> ближайший узел allowed-сети, порог 150 м, отказ too_far/
outside_graph, ближе ли линия с неизвестным доступом, фрагмент vs основная сеть, альтернатива основной
сети только как явный выбор); compare: closed_on_baseline_routes, closure_not_on_baseline_routes,
a_vs_b.identical_active_closures + plans_identical_at_analysis_at; http.handle(..., on_result) для кэша R09.
Пример RUN: Байтерек -> Хан Шатыр (`python -m engine.civic_scenarios.example --check`): база 2230.228 м,
A 2290.625 (+60.397), B 2387.062 (+156.834), B−A 96.437; в 21:00 A не действует, B действует.
Длины совпали с независимой простой Дейкстрой по JSON графа (±0.05 м).
Проверки (worktree 56538a3): pytest tests/civic/R07 tests/civic/test_citywide_osm.py — PASS.
NEXT: UI — места вместо node ID, явный выбор участков, состояния pending/stale/cancel, помощник R09.

## Checkpoint 2 — PARTIAL
DONE: новый web/civic/scenarios/scenarios.js — путь без node ID: «Откуда/Куда» кликом в явном режиме выбора,
привязка в браузере = snap.py (паритет проверен в Node на 155 точках города), показ исходной/найденной
точки, расстояния и порога, отказ без переноса, предупреждение о фрагменте и явный выбор узла основной сети;
варианты A/B — явный выбор участков, список при наложении линий (мосты/уровни), периоды и момент;
состояния pending/cancel/stale/error, отмена при изменении входа во время расчёта; таблица база/A/B/B−A
в метрах, «нет пути» ≠ 0; объяснение R09 через scenarioId "result:"+digest, снимается при устаревании,
подсказка пересчитать при scenario_not_found; Escape (capture+preventDefault), событие civic-scenarios:tool,
destroy снимает слои/источники/курсор/слушатели.
Исправлено по браузерной проверке: кнопка «Отменить расчёт» передавала event как silent (кнопка «Сравнить»
оставалась заблокированной); переполнение таблицы на 390 px.
Кандидат для проверки (scratch, не поставка): 56538a3 + r07 patch + R09 f2ebaf9 (agent/civic_assistant,
web/civic/assistant) + R09 r01_integration.patch + proposed_patches (R01 shell, R03 pauseMapInput).
Браузер (Chromium/Playwright, app.py на временной БД с seed-demo): browser_r07_r13.cjs — 31/31 PASS.
NEXT: проверка истёкшего кэша (перезапуск сервера) и паузы кликов R03; замер производительности; RUN/DELIVERY.

## Checkpoint 3 — PARTIAL
DONE: стык с оболочкой и картой (browser_r07_r13_shell.cjs, 8/8): без режима клик открывает карточку R03,
в режиме выбора — нет (proposed_patches/ R03 pauseMapInput + R01 civic-scenarios:tool); пример из списка
проходит ту же привязку; истёкший кэш проверен настоящим перезапуском сервера (PID сменился):
ответ unavailable/scenario_not_found + просьба пересчитать, после «Сравнить» объяснение снова есть.
Производительность: смежность без перекрытий кэшируется (≤3 варианта), перекрытия пропускаются в Дейкстре,
ранняя остановка по целям. result_digest до/после совпали на 10 сценариях (optimization_digest_check.json).
Город 66 027/94 089: compare примера 2.316 -> 0.327 с (первый), 2.669 -> 0.023 с (повтор); недостижимая
цель 0.699 с; холодная загрузка графа 2.0 с (bench_r13.json, 4 CPU, Python 3.13, облачный контейнер).
Браузер на финальном коде: browser_r07_r13.cjs 31/31, browser_r07_r13_shell.cjs 8/8. Состав кандидата: CANDIDATE_BUILD.json.
NEXT: RUN.txt, INTEGRATION.txt, DELIVERY.json, итоговые проверки и push.
