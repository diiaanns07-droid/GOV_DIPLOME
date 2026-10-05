# K01 раунд 8 — STATUS: контракт city-plan-v2, импорт и воспроизводимость

- Роль: K01 (не BUILD), ветка `claude/loving-thompson-nmajdo`. Общий прототип не изменялся.
- Цель-срез: BUILD `claude/beautiful-clarke-sbzomj` @ **`a5b5e2ddbe087c4eab8e947748cdf69dbae84a0d`** (`web/data.js`, `web/facts.js`), извлечён по SHA во временную папку.
- Входы: `research/round-8/{snapshots.json,CORE_SPEC.txt,TASK.txt,tasks/K01.txt}` @ `codex/research-import-2026-10-05` `c3f6c00`.

| Этап | Статус |
|---|---|
| 1. Строгий validator (JSON Schema + семантика) + адаптер для BUILD | **done** |
| 2. Импорт/экспорт/roundtrip, атомарное состояние, v1→v2 без выдумывания cost, фикстуры обоих городов с хэшами | **done** |
| 3. Canonical digest: перестановки/budget/weights/cost, Unicode/ключи, forged derived; CLI + интеграция | in progress |

## Этап 1 — проверки (реально запущены)
- `node test_planv2.cjs --app-root <extracted a5b5e2d>/city-evidence` → **48 passed, 0 failed, 0 skipped** (`runs/stage1_node_a5b5e2d.txt`):
  манифест фикстур; real-контексты == `contextFromData(data.js, facts.js)` прототипа; 46 synthetic фикстур — вердикт и код JS == EXPECTED == Python-оракул, digest JS == Python.

## Этап 2 — проверки (реально запущены)
- `node test_state.cjs --app-root <extracted a5b5e2d>/city-evidence` → **11 passed, 0 failed, 0 skipped** (`runs/stage2_state_a5b5e2d.txt`):
  roundtrip export→import (3 сценария, оба города, scenario_digest сохраняется), JS-экспорт → Python-импорт идентичен, экспорт без путей/URL;
  `PlanStore`: 20+ невалидных импортов не меняют состояние и request_id; откат невалидной правки; устаревший/чужой ответ worker отклоняется;
  смена города/категории/среза сбрасывает сценарий и предложения; «Применить» переносит предложение в ручной план;
  v1: `whatif.js` BUILD по-прежнему импортирует свой экспорт (оба города), v2-импорт его отклоняет (`unknown_field`, режимы раздельны);
  `migrateV1` без явных `budget`/`cost` → `cost_required`, cost пользователя сохраняется точно, веса = 1, свой v2-snapshot.
- `fixtures/v1/*` создаются `make_v1_fixtures.cjs` через `whatif.js` BUILD; тест сверяет байты. MANIFEST: 51 файл.
