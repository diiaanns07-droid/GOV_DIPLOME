# HANDOFF — K08 R9: экспорт устойчивого плана

Проверенный BUILD: `claude/beautiful-clarke-sbzomj` @ `d865dd4a124291e10dd0b7bb1d9eada20d34c268` (sha256 web — `run/build_manifest_d865dd4.sha256`).
Мои входы r8: `research/round-8-results/K08/` @ 7fb81b9. Подробности и вердикты — STATUS.md.

## Команды (из корня репозитория)
```bash
mkdir -p /tmp/r9 && git archive d865dd4a124291e10dd0b7bb1d9eada20d34c268 prototypes/city-evidence | tar -x -C /tmp/r9
APP=/tmp/r9/prototypes/city-evidence; K=research/round-9-results/K08; export NODE_PATH=$(npm root -g)
python3 $K/check_stage1.py --app-root $APP --json /tmp/s1.json     # reportHtml/export BUILD vs r8-оракул (ожидается S10 FAIL на d865dd4)
python3 $K/make_envelopes.py --app-root $APP --out $K/fixtures
node $K/resilience_cli.cjs --app-root $APP --in $K/fixtures/shymkent_school_r9.json --out-dir /tmp/rr
python3 $K/check_stage2.py --app-root $APP --json /tmp/s2.json      # отчёт устойчивости vs независимый оракул
python3 $K/check_stage3.py --app-root $APP --json /tmp/s3.json      # устойчивость входа, порядок, подделки, срез
node $K/offline_print_check.cjs --pdf-dir /tmp/pdf $K/reports/*/report.html
# patch-предложение:
git worktree add /tmp/wt d865dd4a124291e10dd0b7bb1d9eada20d34c268 && (cd /tmp/wt && git apply $PWD/$K/proposal/report_provenance.patch)
python3 $K/check_stage1.py --app-root /tmp/wt/prototypes/city-evidence   # 11/11
```

## API адаптера устойчивости (`resilience_report.js`, Node и браузер)
- `validateResilience(text|obj, {PL,F,X,data,obs})` → envelope `{schema_version:"city-resilience-v1", plan, cases}` или `ResilienceError(code)`.
- `buildResilienceReport(env, deps)` → `k08-resilience-report/v1`:
  - `source{snapshot, release, bbox, places_file, attribution}`;
  - `cases` (+base, `same_exclusions_as`);
  - `plans{manual, nominal, robust}` с `per_case`, `worst_vector` (null вместо ∞), `worst_case_ids`;
  - `price_of_robustness_m | null + price_reason`;
  - `search{status, evaluated, feasible_count}`, `source_records` (sources, лицензии, QA);
  - digests `resilience_problem/scenario/exclusions` + v2.
- `renderResilienceHtml(report)` — статический HTML; `exportResilienceEnvelope(env)` — только вход.
- Использует только API `web/plan.js` (validatePlanScenario, makeContext, precompute, evaluatePlan(pre), feasibility, optimizePlans, problemDigest, scenarioDigest) и `whatif.parseStrict`. Это не второй движок.
