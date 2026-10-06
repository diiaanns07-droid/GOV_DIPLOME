# Предложения по исправлению — K12, раунд 9

Два патча. Оба проверены на отдельных копиях, общий прототип K12 не менял. Применять или нет, решает BUILD.

| Патч | База | Состав | Статус |
|---|---|---|---|
| `fixes/build_d865dd4_k12_r9.patch` | `d865dd4` (закреплён в snapshots r9) | `evaluatePlan` и `createSearch` валидируют вход и работают с копией; F2 в `whatif.js`; тест `tests/plan_api_guard.cjs` | BUILD уже закрыл это своим исправлением в `e990f01`; патч оставлен как доказательство и альтернатива |
| `fixes/build_33cc635_k12_r9b.patch` (sha256 `9e474546…`) | `33cc635` (новый BUILD) | G1–G4 ниже; тесты `tests/resilience_k12_guard.cjs` и `tests/test_id_order.py` | предложение для BUILD |

Как применить: `git apply research/round-9-results/K12/fixes/<patch>` в checkout BUILD.

- Проверено `git apply --cached --check` против дерева коммита (временный индекс, рабочее дерево не трогалось).
- `patch -p3` на свежей копии даёт байт-в-байт проверенные файлы.

## Находки на `33cc635` и исправления r9b

| # | Находка | Тип | Repro | Исправление |
|---|---|---|---|---|
| G1 | `evaluateResilience(ctx, env, null)` → `TypeError: selectedIds is not iterable`. Строка вместо массива перебирается по символам: `"ﬀ"` молча выбирает кандидата `ﬀ`, а `"c1"` даёт `unknown_ref` по символу `c` | дефект API: нужен типизированный отказ | `api_guard.cjs` → `rs/R_selected_null`; `tests/resilience_k12_guard.cjs` | `if (!Array.isArray(selectedIds)) fail("bad_shape", …)` |
| G2 | `PL.internal.createSearch` экспортирован без проверки: непроверенный объект с 20 кандидатами создаёт поиск на 1 048 576 наборов. CORE_SPEC допускает внутренний проверенный путь, но этот достижим снаружи | ADVISORY, защита в глубину | `api_guard.cjs` → `v2/I_internal_export` | O(1)-проверка `candidates.length > 16` в `createSearchInternal`; проверенные вызовы не затронуты |
| G3 | label с U+202E/U+2066 (bidi, категория Cf) и с одиночным суррогатом принимается | ADVISORY (policy: CORE_SPEC запрещает «управляющие символы», bidi формально Cf) | корпус N35, N49 | `BIDI_OR_LONE` вместе с `CTRL` → `bad_label`; эмодзи (пара суррогатов), казахский и HTML-текст по-прежнему принимаются |
| G4 | При точном равенстве JS (`a < b`, UTF-16) и Python-оракулы BUILD (`sorted`, кодовые точки) выбирают разные планы. Это касается ID, где сравниваются символы выше U+FFFF с символами U+E000–U+FFFF (`𝔸` и `ﬀ`): v2 mean, nominal и robust устойчивости, порядок `worst_case_ids` | расхождение тестовой инфраструктуры и неоднозначность CORE_SPEC («sorted IDs лексикографически» — по каким единицам?) | `id_order_probe.cjs` → `results/stage3_id_order_probe_33cc635.json`; `tests/test_id_order.py` | ключ `u16 = s.encode("utf-16-be")` в `tools/plan_oracle.py` и `tools/resilience_oracle.py`. Поведение продукта не меняется; `expected_*.json` остаются байт-в-байт (`--check` OK) |

- **Для координатора (G4):** стоит записать в CORE_SPEC порядок ID — UTF-16 code units, как в JS. Альтернатива —
  кодовые точки, но тогда менять `cmpStr` в двух JS-модулях.
- **Собственное ограничение K12 по G4:** мой v2-оракул r8 (`round-8-results/K12/oracle/plan_v2_oracle.py`) тоже
  сортирует кодовыми точками. Fuzz r8 генерировал только ASCII-ID, поэтому это не проявилось. Оракул устойчивости r9
  уже сравнивает в UTF-16.

## Проверка патча r9b на копии `33cc635`

| Проверка | Без патча | С патчем |
|---|---|---|
| `api_guard.cjs` | 33 PASS, 1 FAIL, 1 ADVISORY | **35 PASS** |
| `resilience_stress.cjs` (корпус) | 63 PASS, 2 ADVISORY | **65 PASS** |
| `resilience_fuzz.cjs`, seed 21, 300 случаев с оракулом | PASS | PASS |
| `id_order_probe.cjs`: JS = Python-оракул BUILD | 0 из 4 | **4 из 4** |
| `tests/resilience_k12_guard.cjs` (новый) | 7 FAIL | 11/11 |
| `tests/test_id_order.py` (новый) | 2 FAIL | 2/2 |
| BUILD `tools/check_all.py` | exit 0 | exit 0 (plan 164, resilience 111, unittest 52; `evidence.js` rebuild — SKIP) |
| Браузерные тесты BUILD | smoke 24/24, plan_smoke 52/52, whatif_smoke 32/32, plan_keyboard 14/14 | smoke 24/24, plan_smoke 52/52, whatif_smoke 32/32, plan_keyboard 14/14 |
