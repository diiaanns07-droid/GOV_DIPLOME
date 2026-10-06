# K09 r9: находки по BUILD resilience.js и предлагаемый патч (для BUILD; общий прототип K09 не меняет)

| Что | Значение |
|---|---|
| Проверено | BUILD `33cc635ec212e522b3e17fb0b598fad0ad602f71` (этап 2) и `d18847f9e7c18fcfae3349c0b223b023d359a838` (этап 4, код `e82214e`) |
| Находки сохраняются | на обоих SHA |
| Источник находок | независимый состязательный обзор (`results/stage3/independent/build_review/findings.json`) |
| Воспроизведение | K09, на байтовых копиях обоих SHA |
| Скрипт находок | `results/stage3/independent/build_review/findings_repro.cjs` (прочитан до запуска) |

## Находки

| # | Важность | Суть | Как воспроизводится | Затронуто |
|---|---|---|---|---|
| F1 | medium | Пределы проверяются по длине **исходного** массива, а вычисление идёт по массиву, прочитанному повторно. Объект с getter или Proxy обходит пределы: optimizeResilience возвращает `optimal` для 18 кандидатов (262 144 подмножества), 30 случаев или пустого исключения. То же в `plan.js validatePlanScenario` (16 кандидатов v2) | `node patches/test_build_r9_patch.cjs <web>` — F1a…F1e | Только прямой вызов JS API. Импорт JSON и UI дают обычные объекты, поэтому это не удалённая атака. Нарушает CORE_SPEC: «изменение переданного объекта не должно обходить ограничения», ≤ 4096 подмножеств, 1..7 случаев |
| F2 | low | Метка с U+FFFD принимается, но собственный экспорт не импортируется обратно: parseStrict отклоняет U+FFFD как `bad_encoding` | F2 | круг JSON round-trip |
| F3 | low | Результат evaluate и `explainResilience` не связаны с digest сценария. Объяснение можно собрать из результата другого envelope; optimizeResilience без `F` даёт digest = null | `findings_repro.cjs`, F3 | ПРОВЕНАНС CORE_SPEC (request_id + digest). Возможно, закрыто на уровне UI — модульный API не проверяет. **Патчем не исправлено, рекомендация** |
| F4 | low | `evaluateResilience(ctx, env, selectedIds)` не проверяет selectedIds: undefined, null, число или объект дают нетипизированный TypeError, а строка разбирается по символам | F4 | typed errors API |
| F5 | info | Метка принимает невидимые символы (только U+200B), bidi-override (U+202E) и одиночный суррогат | F5 | «без управляющих символов, отображается только текстом» — граница толкования |

Кроме того, в сверке валидации (60 входов) BUILD строже K09 там, где политика различается:
- пробельная метка;
- U+2028.

Это не дефект BUILD, а различие политики (`results/stage3/validation/conformance_*.json`).

## Патч

`patches/build_33cc635_k09.patch` — 60 строк, sha256 `dcef5e9a…`. Проверено:
- применяется без конфликтов к 33cc635 и к d18847f;
- исправляет F1, F2, F4 и F5.

Что меняет патч:
- **plan.js:** повторная проверка числа точек и кандидатов по чистым копиям — после map, до бюджета.
- **resilience.js:**
  - повторная проверка ≤12 кандидатов по чистому плану, до предвычислений;
  - число случаев и непустота исключений проверяются по чистым копиям;
  - метка отклоняется при одиночных суррогатах, Bidi_Control или U+FFFD, а также при отсутствии видимых символов. Эмодзи с ZWJ разрешены;
  - selectedIds должен быть массивом строк, иначе `bad_shape`.

| Проверка | 33cc635 | 33cc635 + патч | d18847f | d18847f + патч |
|---|---|---|---|---|
| `patches/test_build_r9_patch.cjs` (17 проверок) | 14 FAIL (находки воспроизводятся) | 17 PASS | 14 FAIL | 17 PASS |
| `tests/resilience.cjs` BUILD | 111/111 | 111/111 | 112/112 | PASS (all) |
| `tests/plan.cjs` BUILD | 164/164 | 164/164 | 164/164 | PASS (all) |
| `tests/whatif.cjs` BUILD | 71/71 | 71/71 | 71/71 | — |
| T3 1340 задач против оракула K09 | 0 расхождений | 0 расхождений | 0 расхождений | — |
| Валидация, 60 входов | 54 / 2 / 4 / 0 | 54 / 2 / 4 / 0 | 54 / 2 / 4 / 0 | — |

Не запускалось: браузерные и UI-тесты BUILD (smoke, keyboard) с патчем, а также check_all.py. Патч затрагивает только валидацию.

Применение — решение BUILD; K09 общий прототип не меняет:

```
git apply research/round-9-results/K09/patches/build_33cc635_k09.patch
node tests/resilience.cjs && node tests/plan.cjs && node research/round-9-results/K09/patches/test_build_r9_patch.cjs prototypes/city-evidence/web
```

Рекомендация по F3, без патча: возвращать `resilience_scenario_digest` и `request_id` из evaluate и optimize всегда. `explainResilience` должен принимать digest на момент запроса и отклонять устаревшее объяснение, как `explainPlans` (`stale_explanation`).
