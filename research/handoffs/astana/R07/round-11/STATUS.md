# R07 — Симулятор последствий ограничений (раунд 11, Астана)

- Роль: R07; ветка: `claude/brave-hopper-bkc58b`
- Исходный HEAD: 834a25f (main-снимок в ветке)
- PACK_SHA: 9c2f5c0dae14b46c0697a9dfc7f854351bfd570d (origin/codex/govtech-main-interface)
- Источник для сравнения: b2cb2e02c602c166ba6d47c02d8e902e5478c791 (claude/beautiful-clarke-sbzomj): web/govtech/k03/astana.graph.json, routing.js
- Пути: engine/civic_scenarios/, web/civic/scenarios/, tests/civic/R07/, research/round-11-results/R07/, этот файл

## Checkpoint 1 — PARTIAL
DONE: compare(payload, graph) (stdlib), валидатор графа/payload, Дейкстра в мм с tie-break,
синтетический граф 10 узлов + ручные ожидания. `python3 -m pytest -q tests/civic/R07` → 6 passed.
NEXT: тесты рисков (время, offset, digest, мутация, перестановка), адаптер K03.
