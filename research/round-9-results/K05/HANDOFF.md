# HANDOFF — K05 round 9

Состояние: STATUS.md. Все команды из корня репозитория; `<app>` — извлечённая копия сборки (`git archive <SHA> prototypes/city-evidence | tar -x -C /tmp/x`, затем `/tmp/x/prototypes/city-evidence`).

```bash
R=research/round-9-results/K05
# этап 1: plan.js BUILD против задач и оракула r8
node $R/stage1/adapter_r8_vs_build.cjs --app-root <app> --cases research/round-8-results/K05/runs/cases_dump_a5b5e2d.json --oracle-dump /tmp/od.json
python3 research/round-8-results/K05/oracle/oracle.py --cases /tmp/od.json
node $R/stage1/repro_api_guard.cjs --app-root <app> --timeout 8000
# этап 2-3: модуль K05 на API сборки
node $R/tests/test_resilience.cjs --app-root <app>
node $R/tests/test_stage3.cjs --app-root <app> --bench /tmp/bench.json
# gold K06 против web/resilience.js сборки (или копии с patches/add_web_resilience_js.patch)
K=$R/inputs/k06
python3 $K/compare_resilience_js.py --fixture $K/fixtures/resilience_gold.json --export /tmp/rp.json
node $K/run_resilience_js.cjs <app> /tmp/rp.json /tmp/raw.json <SHA>
python3 $R/stage3/map_to_k06.py /tmp/raw.json /tmp/map.json
python3 $K/compare_resilience_js.py --fixture $K/fixtures/resilience_gold.json --candidate-json /tmp/map.json
node $R/stage3/k06_must_reject.cjs <app> $K/fixtures/resilience_gold.json
# две независимые реализации (нужен web/resilience.js в <app>)
node $R/stage3/cross_build_vs_k05.cjs --app-root <app> --n 96
```
Следующий шаг: на следующем SHA BUILD повторить последние пять команд (gold K06, must_reject, перекрёстная сверка) и проверить UI вкладки «Устойчивость» (Playwright) — это ещё NOT_RUN.
Входы K06 — `inputs/k06/` (b9b8145, MANIFEST.json); r8-оракул — research/round-8-results/K05 (1804f5b).
