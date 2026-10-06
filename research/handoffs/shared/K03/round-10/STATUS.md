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
- Этап 4 (BUILD `c0b276e`): патч `patches/build_c0b276e_k03_pedestrian.patch` (`case.js` + pedestrian-v1, отпечаток графа в `case_digest`, `unknown_targets`, тесты). На копии:
  - `school_case` 2312, `school_pedestrian` 622, plan/resilience/whatif PASS;
  - `web_check` OK;
  - Chromium 9/9.
- Не интегрировано в общий сайт; подложка и 3D здесь NOT_FETCHED (OpenFreeMap заблокирован).
- NEXT_STEP: BUILD применяет `install_for_build.py` + `patches/build_c0b276e_k03_pedestrian.patch` (`INTEGRATION.md`, раздел 0), добавляет переключатель метода и слой маршрутов в `school-ui.js`. Затем K03/K12 перепроверяют на точном новом SHA (`run_tests.py --js`, `school_pedestrian.cjs`, `site_copy_check.cjs`).
