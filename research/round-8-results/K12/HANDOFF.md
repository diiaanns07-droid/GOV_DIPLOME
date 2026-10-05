# HANDOFF — K12 раунд 8 (`city-plan-v2`: стресс и негативные планы)

- Ветка `claude/save-work-handoff-xuav3q`, папка `research/round-8-results/K12/`. Общий прототип не менялся.
- Итоги и цифры — `STATUS.md`, находки и патч — `FIX_PROPOSALS.md`.
- Цели проверки:
  - снимок раунда BUILD `a5b5e2d` — без v2;
  - BUILD v2 `d865dd4` (`web/plan.js`, `web/plan-ui.js`).

## Быстрый запуск (из корня репозитория; копии — во временной папке, не в рабочем дереве)

```bash
git fetch origin claude/beautiful-clarke-sbzomj
python research/round-5-results/K12/extract_build.py a5b5e2ddbe087c4eab8e947748cdf69dbae84a0d /tmp/ce_a5     # снимок раунда
python research/round-5-results/K12/extract_build.py d865dd4a124291e10dd0b7bb1d9eada20d34c268 /tmp/ce_v2     # BUILD v2
cd research/round-8-results/K12
python make_fixtures_v2.py                                                     # fixtures_v2/, индекс, oracle_problems.json
python oracle/plan_v2_oracle.py --app-root /tmp/ce_a5 --problems oracle_problems.json --out expected/oracle_mine.json

# эталон K12 (по умолчанию adapters/reference_v2_adapter.cjs)
node plan_stress.cjs   --app-root /tmp/ce_a5 --expected expected/oracle_mine.json        # этап 1: 75 PASS
node stage2_runtime.cjs --app-root /tmp/ce_a5                                            # этап 2: 37 PASS + E2a advisory
node plan_fuzz.cjs     --app-root /tmp/ce_a5 --cases 500 --bench                         # этап 3: PASS
node mutation_score.cjs --app-root /tmp/ce_a5 --cases 200 --repro-dir /tmp/k12_mut       # 12/12 KILLED (около 90 с)

# BUILD v2
B=adapters/build_v2_plan_adapter.cjs
node plan_stress.cjs   --app-root /tmp/ce_v2 --adapter $B --expected expected/oracle_mine.json   # 73 PASS, 2 ADVISORY
node stage2_runtime.cjs --app-root /tmp/ce_v2 --adapter $B                               # 32 PASS, 6 SKIP, E2a advisory
NODE_PATH="$(npm root -g)" node ui_gate_browser.cjs --app-root /tmp/ce_v2                # 9/9 PASS (Playwright + Chromium)
node plan_fuzz.cjs     --app-root /tmp/ce_v2 --adapter $B --cases 500 --bench            # PASS, 1 ADVISORY (API-лимит)
node ../../round-7-results/K12/whatif_import_stress.cjs --app-root /tmp/ce_v2 \
     --adapter adapters/build_v1_whatif_adapter.cjs --index ../../round-7-results/K12/FIXTURES_INDEX.json   # v1: 47/49

# патч K12 на отдельной копии (не в ветке BUILD)
(cd ../../.. && python research/round-5-results/K12/extract_build.py d865dd4 /tmp/ce_fix)
patch -p3 -d /tmp/ce_fix < fixes/build_d865dd4_k12.patch                               # байт-в-байт = проверенная копия
node plan_fuzz.cjs --app-root /tmp/ce_fix --adapter $B --cases 200 --strict-api-guard  # PASS
(cd /tmp/ce_fix && python3 tools/check_all.py)                                         # как без патча
```

- **Коды выхода:** 0 — PASS (ADVISORY и SKIP допускаются), 1 — есть FAIL, 2 — неверные аргументы,
  3 — ошибка браузера.
- **Результаты прогонов:** `results/*.json`. В имени файла — реализация и SHA копии.

## Интерфейс адаптера (CommonJS)

Адаптер экспортирует `function ({appRoot, D, EV, ctx, requireWeb})` и возвращает:

| Функция | Обязательно | Смысл |
|---|---|---|
| `snapshot(city)` | да | текущий `source_snapshot` среза |
| `initialState()` | да | пустое состояние |
| `importScenario(text, state)` | да | `{ok, code, state}`; при отказе `state` прежний; вход не менять; не бросать исключения |
| `evaluate(state)` | желательно | `{selected_ids, rows[{id, before_mm, after_mm, delta_mm}], metrics{unknown_count, weighted_sum_mm, max_mm, covered_weight, cost}, feasibility{feasible}}` |
| `optimize(state)` | желательно | `{status, reasons[code], objectives{mean, minimax, coverage: {selected_ids, metrics} \| null}, pareto[{cost, weighted_sum_mm, selected_ids}], evaluated, feasible_count, problem_digest, sensitivity[{budget, status, feasible_count, mean{selected_ids, …} \| null}]}` |
| `problemDigest(state)` | желательно | независимость от порядка |
| `currentState()` | если состояние внутри модуля | |
| `optimizeAsync(state, {requestId, signal, chunk, yieldFn})` | этап 2 D1/D7, benchmark | при отмене `status: "cancelled"`, `complete: false` |
| `gate()` | этап 2 D2–D6 | `begin(digest) → requestId`, `accept(result) → {accepted, reason}`, `reset()`; без него SKIP, браузерная проверка `ui_gate_browser.cjs` |
| `sources()` | этап 2 B1 | пути исходников для статического просмотра |
| `optimizeUnchecked(obj)` | лимиты API | оптимизация объекта **без** валидации; ожидается `too_large` или типизированное исключение до перебора |

Примеры:

- `adapters/reference_v2_adapter.cjs` — эталон;
- `adapters/build_v2_plan_adapter.cjs` — BUILD `web/plan.js`;
- `adapters/build_v1_whatif_adapter.cjs` — v1;
- `adapters/mutant_adapter.cjs` — эталон с одной внесённой ошибкой, `K12_MUTANT=<имя>`.

## `plan_fuzz.cjs` — параметры

| Флаг | По умолчанию | Смысл |
|---|---|---|
| `--app-root` | — | копия `prototypes/city-evidence` (`web/data.js`, `evidence.js`, …) |
| `--adapter` | эталон | реализация |
| `--seed` / `--cases` | 12 / 200 | детерминированный набор случаев |
| `--max-ms` | 120000 | бюджет времени; при исчерпании `truncated_by_time_budget: true` |
| `--replay S:i` | — | один случай `i` из seed `S` (команда записана в каждом repro) |
| `--no-oracle` / `--python` | оракул вкл. / `python3` | сверка с `oracle/plan_v2_oracle.py` |
| `--repro-dir` | `repro/` | куда писать минимальные repro (первый случай каждого свойства) |
| `--strict-api-guard` | выкл. | API-лимит считать FAIL, а не ADVISORY |
| `--limit-timeout-ms` | 20000 | сторож дочернего процесса лимитов |
| `--bench` | выкл. | худший случай 25 × 16 × 5: синхронно, async, оракул |
| `--out` | — | JSON-отчёт: `summary`, `limits`, `advisories`, `bench`, `failures` |

## Источники и версии

- `CORE_SPEC.txt` и `tasks/K12.txt` @ `c3f6c00`; BUILD `a5b5e2d` и `d865dd4`.
- Node 22.22.0, Python 3.11.15, Playwright 1.56.1 (глобальный, `NODE_PATH="$(npm root -g)"`); Chromium из
  `/opt/pw-browsers`. Иначе задать `K12_CHROMIUM=<путь>`.
- Все сценарии синтетические: условные единицы, веса — приоритеты, не население. Это не городская статистика.

## Что дальше (для BUILD и координатора)

1. **BUILD:** решить по F1 и F2 (`FIX_PROPOSALS.md`); патч готов и проверен на копии.
2. **Координатор:** определить в CORE_SPEC `evaluated` для `infeasible` (P3) и политику для поддельных
   `derived_results` (P1).
3. **После изменений BUILD:** повторить команды выше с новым SHA. Ожидания оракула пересчитать, если изменится
   `data.js` (sha256 записан в результатах).
