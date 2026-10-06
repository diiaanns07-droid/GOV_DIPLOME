# STATUS — K08, раунд 9: экспорт устойчивого плана

**Статус:** этапы 1–2 из 3 выполнены; этап 3 в работе.

- Роль K08 (не BUILD), ветка `claude/dazzling-mayer-drhsxk`. Задание `research/round-9/tasks/K08.txt`, CORE_SPEC r9 @ codex/research-import-2026-10-05.
- **Проверенный BUILD:** `claude/beautiful-clarke-sbzomj` @ `d865dd4a124291e10dd0b7bb1d9eada20d34c268` (HEAD ветки на 2026-10-06; код = 3e1302a по `git diff`). Извлечён через `git archive`; sha256 файлов web — `run/build_manifest_d865dd4.sha256`. Прототип не менялся.
- Мои входы r8: `research/round-8-results/K08/` @ 7fb81b9 (planlib.py — независимый Python-оракул, fixtures).

## Этап 1 — reportHtml / exportPlanScenario BUILD против ожиданий r8
Инструменты:
- `build_adapter.cjs` — вызывает API `web/plan.js` сборки в Node так же, как `plan-ui.js`: validate → export → import → evaluate → optimize → sensitivity → reportHtml. Плюс подделка derived и чужой snapshot.
- `build_compat.py` — r8-оракул с формулой snapshot BUILD. Единственное отличие от моего r8: последним элементом идёт `METRIC "haversine-mm-v1"`, а не строка формулы.
- `check_stage1.py` — вердикты.

`python3 check_stage1.py --app-root <d865dd4> --json run/stage1_d865dd4.json` → **10 PASS, 1 FAIL**:

| Проверка | Вердикт |
|---|---|
| S0 API BUILD вызывается без исключений (7 заданий) | PASS |
| S1 source_snapshot BUILD = независимый пересчёт (оба города) | PASS |
| S2 export → import: тот же сценарий | PASS |
| S3 изменённые derived_results → `forged_derived` | PASS |
| S4 чужой snapshot → `foreign_snapshot` | PASS |
| S5 ручной план, строки, mean/minimax/coverage, Парето, feasible_count = r8-оракул (4 фикстуры, вкл. 16 кандидатов) | PASS |
| S6 без исходных записей (synthetic): before/delta = null в API, экспорте и отчёте, не 0 | PASS |
| S7 max-size (25 точек, 16 кандидатов, 64-символьные кириллические ID): экспорт 21 600 B ≤ 256 KiB, импорт ok | PASS |
| S8 reportHtml: белый список тегов/атрибутов, CSP `default-src 'none'`, нет внешних загрузок | PASS |
| S9 HTML в имени записи/городе/выпуске/атрибуции/объяснении → только текст | PASS |
| **S10** provenance ближайших записей в отчёте | **FAIL** |

**S10 (пробел продукта относительно r8/CORE_SPEC «видимые source/QA»):** в `reportHtml` (`web/plan.js:376–410`) есть source_snapshot, release, digests и общая строка атрибуции. Но нет:
- id ближайших исходных записей (в строках только имя через `m.names`);
- источника/лицензии каждой записи;
- QA-флагов;
- bbox среза;
- sha256 файла мест.

Repro: `reportHtml(m)` для `shymkent_school_demo` — этих полей в тексте нет. Это не ошибка адаптера: адаптер передаёт ровно то, что передаёт `plan-ui.js:reportText`.

## Этап 2 — адаптер отчёта устойчивости (city-resilience-v1)
В d865dd4 нет `resilience.js`, поэтому сделан узкий адаптер **поверх API BUILD**, а не второй движок.
- `resilience_report.js`:
  - `validateResilience(text|obj, deps)` → envelope или `ResilienceError`. Строгий JSON через `whatif.parseStrict`. Полная проверка envelope и plan (`PL.validatePlanScenario`) до вычислений. Коды отказов:
    - `too_many_candidates` — больше 12 кандидатов, проверяется до `makeContext`/precompute;
    - `reserved_id`, `bad_label` — ≤120 code points, без `\p{Cc}`;
    - `bad_exclusions`, `candidate_not_source`, `unknown_source`, `duplicate_id`, `derived_not_accepted`, `unknown_field`.
  - `buildResilienceReport(env, deps)`:
    - для каждого случая — новый объект контекста с отфильтрованными `places` (исходный замороженный ctx не меняется); `PL.precompute` один раз на случай, `PL.evaluatePlan(..., pre)`;
    - nominal = `PL.optimizePlans` → mean на base; robust = перебор ≤4096 по (W, L_base, cost, ids);
    - W, `worst_case_ids` (все равные), цена устойчивости или `price_reason`;
    - provenance исключённых и ближайших записей (sources, лицензия, QA), `same_exclusions_as`;
    - digests: resilience_problem / scenario / exclusions + v2.
  - `renderResilienceHtml(report)` — статический HTML без скриптов, CSP `default-src 'none'`.
  - `exportResilienceEnvelope(env)` — только вход.
- `resilience_cli.cjs` — `node resilience_cli.cjs --app-root APP --in ENV.json --out-dir DIR` (или `--check`).
- `make_envelopes.py` и `fixtures/{shymkent_school_r9,astana_clinic_r9}.json`:
  - план — r8 synthetic demo; исключения — реальные source IDs срезов;
  - Шымкент: 3 записи с QA-сомнением, 2 ближайшие, их дубль с другой подписью, все 15 записей;
  - Астана: запись Foursquare, 3 ближайшие.
- `reports/<fixture>/report.{json,html}`. Шымкент: обычный c2,c3 → устойчивый c2,c5, цена +21,0 м (среднее base), худший случай «все_записи». Астана: планы совпадают, цена 0,000 м — отчёт пишет «преимущества нет».

`python3 check_stage2.py --app-root <d865dd4> --json run/stage2_d865dd4.json` → **8 PASS / 0 FAIL**:
- R1 ×2: manual/nominal/robust, метрики по случаям, W, worst_case_ids, цена = независимый Python-оракул (r8 planlib с отфильтрованными записями, свой полный перебор);
- R2 ×2: provenance и QA каждой исключённой записи, snapshot плана не подменён, версии и digests;
- R3 ×2: HTML по белому списку, CSP, подписи и исключения видны текстом;
- R4: дубль набора помечен, результат от него не зависит;
- R5: экспорт только входа.

## Следующий шаг
Этап 3: печать/чтение без сети (Chromium, emulateMedia print, блокировка сети), кириллица, HTML в подписях, поддельные результаты в envelope, перепутанный срез/город, порядок случаев, отказы строгого импорта; standalone examples; patch-предложение для S10 (provenance в reportHtml).
