# K06 round 9 — независимый математический оракул (HANDOFF)

Роль: K06 (не BUILD). Ветка: claude/ecstatic-curie-hzfzn0 (начало раунда от 58cf89973cf3578620e016329139697becaf860f).
Задание: origin/codex/research-import-2026-10-05 @ 0ab1667, research/round-9/tasks/K06.txt, CORE_SPEC.txt, REVIEW.txt.
**Проверенная сборка: claude/beautiful-clarke-sbzomj @ d865dd4a124291e10dd0b7bb1d9eada20d34c268**, prototypes/city-evidence/
(199 файлов извлечены побайтно, git blob id сверены; код = 3e1302a по git diff).
Мои r8-модули скопированы побайтно в `r8/` (MANIFEST.json, commit 58cf899).

## Этап 1 — 96 gold-задач через настоящий plan.js (готово)
- `run_plan_js.cjs` — адаптер: `validatePlanScenario` + `optimizePlans` из `<app-root>/web/plan.js`; меняет только форму
  контекста (records → places). plan.js и ожидания не меняются.
- `compare_plan_js.py` — ожидания из сохранённого независимого gold (r8) и свежего прогона оракула r8, НЕ из приложения;
  классы PASS / MATH / API_POLICY / REJECTED / MISSING / ERROR.
- Результат на d865dd4: **96/96 PASS** (87 optimal, 9 infeasible; победители mean/minimax/coverage с метриками, Парето,
  feasible_count совпадают). `out/plan_js_d865dd4_gold96.json`, `out/compare_d865dd4_gold96.json`.
- `mutation_check_stage1.py`: 9 испорченных выходов plan.js классифицированы верно (7 MATH, 1 API_POLICY, 1 REJECTED).
- `probe_api_policy.py` + `probe_validate.cjs`: 24 синтетических входа, принять/отклонить. Совпадает 21. Отличия — ПОЛИТИКА API:
  1. ID с пробелом / двоеточием: plan.js `bad_id` (набор символов BUILD: буквы любых алфавитов, цифры, _ . -), оракул K06
     принимал любую строку ≤ 64. По CORE_SPEC r9 правила ID — правила BUILD; кириллица NFC принимается обоими.
  2. Отсутствует weight: plan.js `bad_shape`, оракул K06 подставлял 1. CORE_SPEC: «default 1 при создании» — это UI;
     строгость plan.js при импорте/прямом вызове допустима.
  3. Коды ошибок различаются по имени при одинаковом решении (out_of_range ↔ bad_radius и т.п.).
  Математических ошибок нет.

Команды (из этой папки; `<app>` — извлечённая копия, напр. `python3 ../../round-6-results/K06/extract_build.py /tmp/r9 d865dd4…` из корня):
```
python3 r8/compare_candidate.py --problems r8/fixtures/gold_cases.json --export /tmp/p9.json
node run_plan_js.cjs <app> /tmp/p9.json out/plan_js_d865dd4_gold96.json d865dd4a124291e10dd0b7bb1d9eada20d34c268
python3 compare_plan_js.py --problems r8/fixtures/gold_cases.json --plan-js-json out/plan_js_d865dd4_gold96.json --json out/compare_d865dd4_gold96.json
python3 mutation_check_stage1.py --problems r8/fixtures/gold_cases.json --plan-js-json out/plan_js_d865dd4_gold96.json
python3 probe_api_policy.py --app-root <app> --json out/api_policy_d865dd4.json
```

## Дальше
2. Python reference city-resilience-v1 (envelope, исключения, worst-lex-v1) + small exhaustive cases.
3. Метаморфные свойства устойчивости, gold, адаптер, mutation checks; сравнение с BUILD r9 при наличии.
