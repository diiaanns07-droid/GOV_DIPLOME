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
