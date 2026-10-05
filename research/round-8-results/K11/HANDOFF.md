# K11 round 8 — HANDOFF

Для BUILD (интеграция в `prototypes/city-evidence/`) и следующего проверяющего.

## Что взять

| Файл | Куда | Зависимости |
|---|---|---|
| `src/plan_runner.js` | `web/plan_runner.js` | нет; движок передаётся параметром `engine` |
| `src/plan_worker.js` | `web/plan_worker.js` (рядом с движком; worker делает `importScripts("plan_core.js")`) | движок как `self.CITY_PLAN_CORE` |
| `src/plan_core.js` | `web/plan_core.js`, если сборщик не пишет свой решатель | нет |
| `tools/make_worker_bundle.py` | генератор `web/worker_bundle.js` для `file://` (Blob-worker) | Python stdlib |

Свой решатель сборщика подключается через `engine`, если у него есть методы `validatePlanScenario`, `problemDigest`, `prepareProblem`, `createSearch`, `stepSearch`, `finalizeSearch`, `sensitivityBudgets`. Тогда `tests/harness.cjs` можно запустить против него, заменив `require` движка.

## Как проверить

```bash
cd research/round-8-results/K11
node tests/harness.cjs                                   # Node, без DOM
python3 oracle/plan_oracle.py fixtures/real/real_shymkent_school_16x25.json   # оракул отдельно
NODE_PATH="$(npm root -g)" node tests/browser_example.cjs [--file]            # браузер; без Playwright -> NOT_RUN (exit 3)
python3 tools/make_worker_bundle.py                      # после правки src/: пересобрать bundle примера
```

## Открытые вопросы

- Ничья «исходная запись или кандидат на одинаковом расстоянии»: K11 оставляет исходную запись (улучшение не засчитывается). CORE_SPEC требует только стабильный ключ, поэтому правило нужно согласовать с решателем сборщика.
- `problem_digest` K11 включает `engine` и `metric_version`. Digest сборщика может отличаться: runner сравнивает digest, который вычислил сам движок.

Дальнейшие этапы будут дописаны ниже.
