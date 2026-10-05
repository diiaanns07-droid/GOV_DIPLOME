# K05 round 3 — адаптер реальных данных: STATUS

Статус: **partial** (checkpoint 1: regression + patch готовы; адаптер в работе)
Обновлено: 2026-10-05 UTC. Ветка: `claude/optimistic-davinci-1oiqs9`.
Задание: `research/round-3/prompts/K05.txt` @ codex/research-import-2026-10-05 (6602bb8).
Предыдущий результат K05: 6d39cc5 (`research/next-round/K05/`, не изменялся).
Входы K10: `claude/save-work-handoff-j7pc05` @ e91898d596164bcf6e853b921a49f82126074a35 → `inputs/k10/`, manifest `inputs/MANIFEST.json` (git blob каждого файла сверен).

## Сделано (checkpoint 1)
- `patches/fetch_real_context_null_on_failure.patch` — минимальный patch: null вместо 0 при отсутствии данных; при сохранённом предыдущем успехе — `meta.last_attempt` (время, ошибка). `git apply --check` к HEAD проходит; к продукту **не применён**.
- `regression/test_handle_failure.py` — 3 сценария во временном каталоге, для копии с patch и для текущего продукта.

## Проверки (реально выполнены)
- `python research/round-3-results/K05/regression/test_handle_failure.py` → `Ran 6 tests, OK (expected failures=3)`: текущий продукт нарушает все 3 сценария, копия с patch проходит все 3.
- sha256 `data/real_context*.json` и `fetch_real_context.py` до и после теста совпадают.

## Дальше
Адаптер k05-obs-v1.1 на samples/E02 K10 для обоих городов, проверка схемы библиотекой jsonschema, REPORT.
