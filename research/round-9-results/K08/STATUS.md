# STATUS — K08, раунд 9: экспорт устойчивого плана

**Статус:** done — этапы 1–3 выполнены на BUILD d865dd4. Новой сборки после d865dd4 нет: прогоны на более новом SHA — NOT_RUN. Модуль устойчивости в BUILD отсутствует: его интеграция — NOT_RUN, отчёт проверен через мой адаптер поверх API BUILD.

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

## Этап 3 — устойчивость, печать без сети, повторная проверка
`python3 check_stage3.py --app-root <d865dd4> --json run/stage3_d865dd4.json` → **9 PASS / 0 FAIL**:
- T1: кириллица и казахские буквы в ID и подписях, HTML в подписях — только текст; точный JSON roundtrip;
- T2: поддельные производные/результаты во входе → `derived_not_accepted` / `unknown_field`;
- T3: report.json как вход отклоняется — отчёт всегда пересчитывается;
- T4: чужой snapshot, ID другого города, кандидат вместо исходной записи, подмена города/категории → типизированные отказы;
- T5: перестановка случаев, исключений, кандидатов и точек — те же планы, W, худшие случаи, digests, цена;
- T6: `selected_ids` входит только в scenario digest;
- T7: строгий JSON (NaN, дубликат ключа, 1e999, >256 KiB) и границы r9 (13 кандидатов → `too_many_candidates` до вычислений, 8 случаев, `base`, подпись 121 / 120 / управляющий символ, пустые и дублирующиеся исключения, дубль id, версия);
- T8: изменённый срез → `bad_plan:foreign_snapshot`;
- T9: замороженный контекст BUILD не мутируется; base = `evaluatePlan` v2.

Печать и чтение без сети (`offline_print_check.cjs`, Chromium, `offline: true` + блокировка всех запросов, 1100 и 380 px, `emulateMedia print` + PDF):
- отчёты устойчивости (адаптер): 0 запросов, 0 ошибок, PDF создаётся, нет горизонтальной прокрутки — **PASS**;
- `reportHtml` BUILD d865dd4: 0 запросов, 0 ошибок, PDF создаётся, но страница шире экрана — 691 px на 380 px; с 64-символьными ID (допустимы правилами BUILD) 2296 px даже на 1100 px. В PDF содержимое не теряется (23/23 стоимости, 50/50 весов из HTML). **FAIL (макет экрана, без потери данных в печати).** Repro: `reports/build_d865dd4/astana_school_maxsize.reportHtml.html`.

## Предложение для BUILD (не FIXED — в BUILD не внесено)
`proposal/report_provenance.patch` (`web/plan.js` +13/−3, `web/plan-ui.js` +9/−1); `git apply --check` на d865dd4 проходит:
- `reportHtml`: таблицы в `.tw` с собственной прокруткой, `overflow-wrap:anywhere`; необязательный `m.provenance` — bbox, файл мест, таблица ближайших исходных записей (ID, название, категория Overture, источник · лицензия · дата, QA-тексты `qaOf`);
- `plan-ui.reportText` строит `provenance` по ближайшим записям ручного плана.

Проверено на копии d865dd4 с patch:
- `check_stage1` **11/11** (S10 PASS);
- тесты сборки: `plan.cjs`, `whatif.cjs`, `conformance.cjs` ok, `plan_smoke.cjs` 52/52, `smoke.cjs` 24/24 (оригинал plan_smoke 52/52);
- отчёт, скачанный кнопкой `#plReport` в plan_smoke, содержит раздел «Исходные записи в отчёте», bbox, sha256 файла, лицензии и QA-тексты, разметка чистая (`reports/build_patched_on_d865dd4/ui_download_plan_smoke.html`);
- нет горизонтальной прокрутки на 380 и 1100 px.

## Итог PASS / FAIL / SKIP / NOT_RUN
- Этап 1 на d865dd4: 10 PASS, 1 FAIL (S10 provenance).
- Этап 2 (адаптер на d865dd4): 8 PASS.
- Этап 3 (адаптер на d865dd4): 9 PASS; печать/офлайн отчётов адаптера PASS; макет `reportHtml` BUILD — FAIL.
- NOT_RUN: модуль устойчивости BUILD (`resilience.js` в d865dd4 нет); прогон на более новом SHA (нет новой сборки).

## Ограничения
- Адаптер повторяет вызов `reportHtml` из `plan-ui.reportText`; если BUILD изменит этот вызов, адаптер нужно синхронизировать.
- Python-оракул — мой r8 planlib (независим от JS); для устойчивости — свой перебор с отфильтрованными записями.
- Фикстуры: план — synthetic demo (места, стоимости, веса, бюджет); исключения — реальные source IDs, выбор пользовательский, не утверждение о закрытии.

## Следующий шаг
Сборщику:
- применить или переписать `proposal/report_provenance.patch`;
- при появлении `web/resilience.js` сравнить его `optimizeResilience` с `resilience_report.js` и `check_stage2.py` на `fixtures/*_r9.json` (математика, не байты digest);
- повторить `check_stage1/2/3` на новом SHA.
