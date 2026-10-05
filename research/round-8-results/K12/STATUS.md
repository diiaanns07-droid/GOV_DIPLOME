# STATUS — K12, раунд 8: стресс-тест и негативные планы `city-plan-v2`

- **Роль:** TASK K12 (не BUILD). Ветка `claude/save-work-handoff-xuav3q`.
- **Задание:** `research/round-8/tasks/K12.txt` и `CORE_SPEC.txt` @ `codex/research-import-2026-10-05` `c3f6c00`.
- **База:** BUILD `claude/beautiful-clarke-sbzomj` @ `a5b5e2ddbe087c4eab8e947748cdf69dbae84a0d`.
  - Папка прототипа совпадает с кандидатом `4e93f30`: проверено `git diff --stat`, расхождений нет.
  - Копия извлечена `research/round-5-results/K12/extract_build.py`, git blob 191 файла сверен.
  - Собственные тесты BUILD на копии: `whatif.cjs` — all passed, `conformance.cjs` — all passed,
    unittest — OK.
- **В базе нет кода `city-plan-v2`** (есть только v1 `web/whatif.js`). Поэтому v2 проверяется на
  эталонном модуле K12 и независимом Python-оракуле. Интеграция v2 в BUILD **не заявляется**.

## Этапы

| Этап | Статус |
|---|---|
| 1. Негативные фикстуры v2, эталон, оракул, стресс-модуль | **done** |
| 2. Атомарность, неисполнение payload, snapshot mismatch, отмена и поздние результаты | следующий |
| 3. Property/fuzz-раннер со сжатием, лимиты, benchmark, адаптер, предложения | ожидает |

## Этап 1 — сделано

- `make_fixtures_v2.py` → `fixtures_v2/*.json`, `FIXTURES_V2_INDEX.json`, `oracle_problems.json`:
  75 текстов импорта, **синтетика** (условные единицы, не тенге и не население).
  - **Позитивные (12):**
    - V01 — база;
    - V02 — Астана, поликлиника, 0 кандидатов;
    - V03 — отравленные `derived_results` с HTML и URL;
    - V04 — 25 точек × 16 кандидатов × `max_selected` 5;
    - V05 — нижние границы;
    - V06 — cost и budget = 1 000 000;
    - V07, V08 — `infeasible` по бюджету и по числу;
    - V09 — одинаковые ID точек и кандидатов (namespace);
    - V10 — перестановка массивов;
    - V11 — ручной план нарушает `excluded`;
    - V12 — ровно 256 KiB.
  - **Негативные (63):**
    - границы и типы: точки 0 и 26, кандидаты 17, `max_selected` 6, −1, 2.5, "3", true;
    - вес 0, 101, 1.5, −1, отсутствует; cost 0, 1000001, 2.5, −5, "100000";
    - бюджет −1, 1000001, 0.5; радиус 99, 5001, 150.5;
    - ссылки: неизвестные ID в required, excluded и selected; required∩excluded; повторы ID;
    - ID: 65 символов, HTML;
    - кандидат: `kind: observed`, другая категория;
    - координаты: вне bbox, lat/lon перепутаны, строка;
    - поля: `population`, `capacity`, отсутствие поля;
    - версия v1 в v2; чужой snapshot, имя файла вместо snapshot; город; категория;
      корень-массив; `selected_ids` строкой;
    - повторы ключей: `budget`, `cost`, `required_ids`; NaN, Infinity, `1e999`, −Infinity;
    - `__proto__`, `constructor`; обрезанный JSON;
    - больше 256 KiB, в том числе многобайтовый внутри `derived_results`;
    - глубина 20 000 и 33.
- `reference/plan_v2_ref.cjs`: эталон `validatePlanScenario`, `evaluatePlan`, `optimizePlans`
  (точный перебор, три цели, Парето, чувствительность), `optimizePlansAsync`, `ResultGate`,
  `importPlanScenario`, order-independent `problem_digest`.
- `oracle/plan_v2_oracle.py`: независимый Python-оракул (`itertools.combinations`, Парето попарно,
  `floor(x+0.5)`).
- `plan_stress.cjs`: переносимый Node-модуль (`--app-root`, `--adapter`, `--expected`).
  `adapters/reference_v2_adapter.cjs`.

## Проверки, которые реально выполнены (Linux, Node 22.22, Python 3.11.15)

- Оракул на `build_a5b5e2d`: 11 позитивных задач, около 2 с → `expected/oracle_a5b5e2d.json`
  (sha256 `data.js` `bb2a7e66…`).
- `node plan_stress.cjs --app-root <копия a5b5e2d> --expected expected/oracle_a5b5e2d.json`:
  **75/75 PASS**. Коды совпали, сетевых попыток 0, самый долгий импорт 13 мс
  (`results/stage1_reference_on_a5b5e2d.json`).
  - JS-эталон совпал с Python-оракулом на всех позитивных задачах (цели, метрики, Парето,
    чувствительность, `feasible_count`, `evaluated`, ручной план).
- Контроль самого сравнения: два испорченных ожидания дали ровно 2 FAIL с точной разницей.

## Ограничения

- v2 проверен на эталоне K12, а не на BUILD.
- Коды отказов — словарь эталона: CORE_SPEC их не называет. Без `--strict-codes` расхождение
  кода не считается FAIL.
- N63 (глубина 33) зависит от выбранного предела вложенности: у эталона и v1 BUILD он равен 32.
