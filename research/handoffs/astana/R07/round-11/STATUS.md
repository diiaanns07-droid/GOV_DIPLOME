# R07 — Симулятор последствий ограничений (раунд 11, Астана)

- Роль: R07; ветка: `claude/brave-hopper-bkc58b`; исходный HEAD 834a25f
- PACK_SHA: 9c2f5c0dae14b46c0697a9dfc7f854351bfd570d (origin/codex/govtech-main-interface)
- Источник для сравнения: b2cb2e02c602c166ba6d47c02d8e902e5478c791 (web/govtech/k03/astana.graph.json, routing.js) — не изменялся
- Пути: engine/civic_scenarios/, web/civic/scenarios/, tests/civic/R07/, research/round-11-results/R07/, этот файл
- Код проверенного состояния: d77ec45 (DELIVERY.json code_commit)

## Итог — DONE (ready для интеграции R01)
- `compare(payload, graph)` civic-scenario-v1: baseline + планы A/B, Δ по сопоставимым парам, ok/unknown/unreachable,
  coverage, warnings, digests (payload/scenario/graph/result). Stdlib.
- Stretch `timeline(...)`: все границы интервалов, м·ч и пара·ч раздельно.
- Графы: `synthetic-tiny-v1` (ручные ожидания), `k03-astana-pedestrian-r10` (walking, derived, адаптер K03 с проверкой hash). driving — NOT_READY.
- UI: `window.CivicScenarios.mount({root,map,api,apiPrefix?}) -> {destroy}`; demo.html + devserver (loopback).
- Результаты: research/round-11-results/R07/results/*, AB_CARD_*.md, bench.json, compare_k03_routing.json, browser_check.json, скриншоты.

## Проверки (код d77ec45)
- PASS `python3 -m pytest -q tests/civic/R07` — 51 passed; весь `python3 -m pytest -q` — 163 passed
- PASS сверка с K03 routing.js: 400 пар, 355 длин совпали до мм, 45 no-path совпали
- PASS `python3 -m engine.civic_scenarios.build_graphs --check`
- PASS браузер (Chromium, Playwright): 15/15, `?basemap=none`
- NOT_RUN подложка OpenFreeMap / 3D — внешние хосты закрыты прокси (403)
- NOT_RUN интеграция в app.py/web_server.py — зона R01

## Найдено и исправлено в ходе работы
- `inf` в length_m давал ValueError при digest -> теперь invalid_graph (структура проверяется до digest).
- UI пропускал перерисовку: `map.isStyleLoaded()` ложно во время setData -> собственный флаг готовности стиля.

## Риски
- Срез 2×2 км и 64% рёбер с неизвестным доступом: многие пары могут стать unknown — это честный результат, не ошибка.
- api.request префикс: если R01 добавляет /api/civic/v1 сам — передать apiPrefix: "".

## Следующий шаг
R01 подключает по research/round-11-results/R07/INTEGRATION.txt; R10 — fixtures_R10/compare_cases.json.
