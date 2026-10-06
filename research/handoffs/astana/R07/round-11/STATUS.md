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

## Checkpoint 2 — PARTIAL
DONE: 42 теста рисков (время [start,end), offset, digest, мутация, перестановка, лимиты, boundary);
исправлен дефект: inf в графе давал ValueError -> теперь invalid_graph.
Адаптер K03 -> civic graph `k03-astana-pedestrian-r10` (walking, derived, 2309 узлов/3269 рёбер),
проверка sha256 файла и пересчёт graph_sha256 источника; MANIFEST.json; registry; HTTP-адаптер.
Сверка с routing.js b2cb2e0: research/round-11-results/R07/compare_k03_routing.json — PASS (400 пар).
NEXT: UI web/civic/scenarios/, timeline (stretch), DELIVERY.json/INTEGRATION.txt.

## Checkpoint 3 — PARTIAL
DONE: timeline (stretch: м·ч, пара·ч по всем границам интервалов, ручные ожидания в тестах);
демо-кейс K03 (гипотеза, генератор make_k03_case.py); UI web/civic/scenarios/ (CivicScenarios.mount,
CSS, demo.html), devserver (loopback). Браузерная проверка Chromium: browser_check.json — PASS 15/15,
скриншоты реальные (подложка отключена: OpenFreeMap/unpkg недоступны из среды, 403 proxy).
Исправлен UI-дефект: isStyleLoaded()==false во время setData пропускал перерисовку.
NEXT: README/INTEGRATION/contract_delta/DELIVERY, результаты+digest, бенчмарк, fixtures для R10.
