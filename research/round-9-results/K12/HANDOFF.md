# HANDOFF — K12 раунд 9 (границы API, корпус устойчивости, fuzz на BUILD)

- Ветка `claude/save-work-handoff-xuav3q`, папка `research/round-9-results/K12/`. Общий прототип не менялся.
- Сводка — `STATUS.md`. Предыдущий пакет r8 — `research/round-8-results/K12/`: харнесс, адаптеры, оракул, фикстуры v2.
  Он используется повторно, не копируется.
- Проверяемая сборка: BUILD `d865dd4a124291e10dd0b7bb1d9eada20d34c268`. Новый BUILD r9 не опубликован, поэтому
  интеграция устойчивости — NOT_RUN.

## Команды (из корня репозитория)

```bash
git fetch origin claude/beautiful-clarke-sbzomj
python research/round-5-results/K12/extract_build.py d865dd4a124291e10dd0b7bb1d9eada20d34c268 /tmp/ce \
       --json /tmp/ce_manifest.json                                    # byte-exact копия + manifest
cd research/round-9-results/K12

# этап 1: прямой API (каждая проба — дочерний процесс со сторожем)
node api_guard.cjs --app-root /tmp/ce --out /tmp/api_guard.json        # d865dd4: 2 PASS / 20 FAIL / 9 NOT_RUN

# патч K12 r9 на отдельной копии
(cd ../../.. && python research/round-5-results/K12/extract_build.py d865dd4 /tmp/ce_fix)
patch -p3 -d /tmp/ce_fix < fixes/build_d865dd4_k12_r9.patch           # или git apply в checkout BUILD
node api_guard.cjs --app-root /tmp/ce_fix                              # 22 PASS / 0 FAIL / 9 NOT_RUN
node /tmp/ce_fix/tests/plan_api_guard.cjs                              # 19/19 (на исходной копии 15 FAIL)
(cd /tmp/ce_fix && python3 tools/check_all.py)                         # exit 0
(cd /tmp/ce_fix && NODE_PATH="$(npm root -g)" node tests/plan_smoke.cjs /tmp/out)   # 52/52
```

- Когда BUILD опубликует новый SHA: извлечь его так же и запустить `api_guard.cjs`.
  - Пробы `rs/*` запустятся автоматически, если есть `web/resilience.js` с функциями `validateResilience`,
    `evaluateResilience`, `createResilienceSearch`, `optimizeResilience`.
  - Если экспорт назван иначе, поправить `adapters/resilience_api_adapter.cjs`.
- **Коды выхода:** 0 — нет FAIL (NOT_RUN допускается и считается отдельно), 1 — есть FAIL, 2 — неверные аргументы.

## Интерфейс адаптера `api_guard.cjs`

```
module.exports = ({appRoot, D, requireWeb}) => ({
  ctx(city), snapshot(city), places(city, category) -> [source id],
  validate(obj, ctx),                     // validatePlanScenario / validateResilience
  createSearch(ctx, obj), optimize(ctx, obj), sensitivity?(ctx, obj), evaluate(ctx, obj, ids)
}) | null                                   // null = модуля нет -> NOT_RUN
```

Проба PASS, если вызов бросает ошибку со строковым `code` быстрее `--fast-ms` (200). Контрольные пробы `C_*` и `RC_*`
проверяют, что валидный вход по-прежнему работает.
