# Handoff K03 · round 10

- Агент: Claude Code, ветка `claude/epic-curie-iitc43` (слот K03 по `research/round-10/snapshots.json` @ `7c6fb75`), не BUILD.
- База: код `d2ff344`; входы сети — донор `d18847f` (K10, Overture `2026-09-23.1`, ODbL).
- Результаты: `research/round-10-results/K03/` (`STATUS.md`, `COVERAGE.md`).
- Этап 1 (аудит покрытия): **done**.
- Этап 2 (политика pedestrian-v1 и `build_graph.py` → `graph/<city>.graph.json` с hash/ODbL): **done**.
- Этап 3: `routing.js` + оракул `routing_ref.py`, 17 ручных графов, 243 пары двух городов, `run_tests.py` → PASS 11, INFO 1 (промежуточный commit). Осталось: замер, отрицательный контроль, adapter для BUILD, `INTEGRATION.md`.
- NEXT_STEP: `bench.cjs`, `negative_controls.py`, `adapter_example.js` + demo, `INTEGRATION.md`, финальный STATUS.
