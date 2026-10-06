# HANDOFF — K12 раунд 9 (границы API, корпус устойчивости, fuzz на BUILD, UI, патчи)

- Ветка `claude/save-work-handoff-xuav3q`, папка `research/round-9-results/K12/`. Общий прототип не менялся.
- Итоги — `STATUS.md`, находки и патчи — `FIX_PROPOSALS.md`.
- Пакет r8 (`research/round-8-results/K12/`: харнесс v2, адаптеры, оракул v2, фикстуры) используется повторно,
  не копируется.
- Финальный проверенный SHA BUILD: `d18847f9e7c18fcfae3349c0b223b023d359a838` (код `e82214e`). Ранее проверены
  `d865dd4`, `33cc635`, `e1cbc3f`.

## Команды (из корня репозитория; копии — во временной папке)

```bash
git fetch origin claude/beautiful-clarke-sbzomj
python research/round-5-results/K12/extract_build.py d18847f9e7c18fcfae3349c0b223b023d359a838 /tmp/ce --json /tmp/ce_manifest.json
cd research/round-9-results/K12

# этап 1: прямой API (каждая проба — дочерний процесс со сторожем 10 с)
node api_guard.cjs --app-root /tmp/ce --out /tmp/api.json             # d18847f: 33 PASS / 1 FAIL / 1 ADVISORY

# этап 2: корпус устойчивости и независимый оракул
python make_resilience_fixtures.py --app-root /tmp/ce                 # fixtures_rs/, индекс, rs_oracle_problems.json
python oracle/resilience_oracle.py --app-root /tmp/ce --index FIXTURES_RS_INDEX.json                       # 59/59
python oracle/resilience_oracle.py --app-root /tmp/ce --problems rs_oracle_problems.json --out /tmp/exp.json
node resilience_stress.cjs --app-root /tmp/ce --expected /tmp/exp.json  # 63 PASS / 2 ADVISORY
node resilience_stress.cjs --app-root /tmp/ce --adapter adapters/oracle_rs_import_adapter.cjs              # самопроверка харнесса, не BUILD

# этап 3: fuzz, порядок ID, браузер
node resilience_fuzz.cjs --app-root /tmp/ce --seed 24 --cases 300     # PASS; --replay S:i, --unicode-rate 1
node id_order_probe.cjs --app-root /tmp/ce                            # JS vs Python-оракулы BUILD vs K12
NODE_PATH="$(npm root -g)" node ui_r9_browser.cjs --app-root /tmp/ce  # B, L, R: 21 PASS / 2 ADVISORY
(cd ../../round-8-results/K12 && node plan_fuzz.cjs --app-root /tmp/ce --adapter adapters/build_v2_plan_adapter.cjs \
   --seed 31 --cases 300 --strict-api-guard)                          # v2: PASS

# патч r9c на отдельной копии
(cd ../../.. && python research/round-5-results/K12/extract_build.py d18847f /tmp/ce_fix)
patch -p3 -d /tmp/ce_fix < fixes/build_e1cbc3f_k12_r9c.patch          # или git apply в checkout BUILD
node /tmp/ce_fix/tests/resilience_k12_guard.cjs && (cd /tmp/ce_fix && python3 -m unittest tests.test_id_order)
(cd /tmp/ce_fix && python3 tools/check_all.py)                        # exit 0
node api_guard.cjs --app-root /tmp/ce_fix                             # 35/35
```

- **Коды выхода:**
  - 0 — нет FAIL (ADVISORY, SKIP и NOT_RUN считаются отдельно);
  - 1 — есть FAIL;
  - 2 — неверные аргументы;
  - 3 — `resilience_fuzz.cjs`: модуля нет (NOT_RUN); `ui_r9_browser.cjs`: ошибка браузера.
- `resilience_stress.cjs` по умолчанию берёт `expected/rs_oracle_d865dd4.json`. Если `data.js` иной, сверка с
  оракулом пропускается с пометкой, а ожидания нужно пересчитать командой выше.

## Адаптеры

| Файл | Интерфейс | Для чего |
|---|---|---|
| `adapters/plan_v2_api_adapter.cjs` | `ctx, snapshot, places, validate, createSearch, optimize, sensitivity, evaluate, raw` | прямой API `plan.js` |
| `adapters/resilience_api_adapter.cjs` | то же для `validateResilience / createResilienceSearch / optimizeResilience / evaluateResilience`; `null` без модуля | прямой API `resilience.js`; `resilience_fuzz.cjs` |
| `adapters/build_resilience_import_adapter.cjs` | `snapshot, initialState, importEnvelope(text, state) → {ok, code, state}, optimize(state) → {status, nominal{ids, worst_vector[u,s,max], worst_case_ids}, robust{…}, evaluated, feasible_count, price_of_robustness_m}` | корпус против BUILD |
| `adapters/oracle_rs_import_adapter.cjs` | тот же | самопроверка харнесса через оракул K12 (**не BUILD**) |

Имена экспорта взяты из `research/round-9-results/BUILD/ADAPTER_API.md` @ `33cc635` и совпадают с CORE_SPEC r9.
Если BUILD их сменит, правится адаптер: это ошибка адаптера, не продукта.

## Версии

- Linux, Node 22.22.0, Python 3.11.15, Playwright 1.56.1 (глобальный; `NODE_PATH="$(npm root -g)"`), Chromium из
  `/opt/pw-browsers`. Иначе задать `K12_CHROMIUM`.
- Сетевых запросов нет. Секреты не нужны.

## Следующий шаг

1. **BUILD:** решить по `fixes/build_e1cbc3f_k12_r9c.patch` (G1 — дефект API; G2–G5 — ADVISORY/policy).
   Патч применяется к `d18847f`.
2. **Координатор:** записать в CORE_SPEC порядок ID (UTF-16 как в JS или кодовые точки, G4) и политику названий
   (bidi, одиночные суррогаты, U+2028, G3/G5).
3. **После нового SHA BUILD:** повторить команды выше. Если `data.js` изменится, пересчитать
   `expected/rs_oracle_*.json` и корпус (`make_resilience_fixtures.py` берёт ID записей из `data.js`).
