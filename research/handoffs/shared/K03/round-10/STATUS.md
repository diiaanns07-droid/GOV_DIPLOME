# Handoff K03 · round 10

- Агент: Claude Code, ветка `claude/epic-curie-iitc43` (слот K03 по `research/round-10/snapshots.json` @ `7c6fb75`), не BUILD.
- База: код `d2ff344`; входы сети — донор `d18847f` (K10, Overture `2026-09-23.1`, ODbL).
- Результаты: `research/round-10-results/K03/` — `STATUS.md`, `README.md`, `INTEGRATION.md`, `COVERAGE.md`.
- Этап 1 (аудит покрытия): **done**.
- Этап 2 (политика pedestrian-v1, `build_graph.py`, графы с hash/ODbL): **done**.
- Этап 3 (`routing.js` + оракул, fixtures обоих городов и ручных графов, adapter, патч для BUILD): **done**.
  - `run_tests.py`: PASS 11, INFO 1.
  - Отрицательный контроль: 6/6.
  - Браузер: 12/12.
  - Копия сайта d2ff344 + патч: 7/7.
- Не интегрировано в общий сайт; подложка и 3D здесь NOT_FETCHED (OpenFreeMap заблокирован).
- NEXT_STEP: BUILD применяет `install_for_build.py` + `patches/build_d2ff344_k03_routing_assets.patch` и встраивает режим в UI по `INTEGRATION.md`. Затем K03/K12 перепроверяют на точном новом SHA (`run_tests.py --js`, `site_copy_check.cjs`).
