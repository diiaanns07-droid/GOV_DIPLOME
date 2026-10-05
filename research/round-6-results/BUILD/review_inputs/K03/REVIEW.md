# K03, раунд 5 — REVIEW «Границы в демо»

Проверялась сборка BUILD `claude/beautiful-clarke-sbzomj` @ `0bf27de`, `prototypes/city-evidence/`. Отдельно исследовательский модуль я не перепроверял: проверялось его использование в демо. Предложения исправлений проверены **только во временной копии**. BUILD не изменён, статус FIXED не заявляется.

## 1. Итог по baseline 0bf27de

`test_boundaries_demo.py --app-root <извлечённая копия 0bf27de>` → **PASS 7, XFAIL 6, FAIL 0** (`baseline/baseline_0bf27de.json`).

| Проверка | Итог | Что показала |
|---|---|---|
| C1. Входы K03 | PASS | 11 файлов `inputs/k03_root` = K03 @ `44585de` (sha256 по `source_manifest.json` и побайтно с git) |
| C2. Модуль — тот, что в метке | PASS | **Да, v1.** Поведение на отпечатках D1/D2 — v1; `assign()['rule']`, `evidence.assign_rule`, `method.id` — все `k03_assign_v1` |
| C3-R1 (D1), C3-R2 (D2) | XFAIL | Известные дефекты правила v1: край города у AST-Z2 → `unmatched` вместо `ambiguous`; 0,58 м от границы Overture → `matched` |
| C3-R3/R4/R5 | PASS | Эксклав → `ambiguous`; порог допуска 0,99 м → `ambiguous`, 1,01 м → `matched` Есиль |
| C4. Фактический путь сборки | PASS | `tools/build_evidence.py` в копии воспроизводит `web/evidence.js` побайтно |
| C5. place_district | PASS | 120 мест `data.js`: у каждого есть запись, форма статуса верна, совпадает с `assign()` |
| C6. Привязка к версии | XFAIL | В `evidence.js` нет связи `place_district` с кодом, слоями или координатами; `boundary_version = null` |
| C7-S1. Реальная синхронизация слоёв | XFAIL | Геометрия Алматы/Сарайшыка в снимке ← версия Overture из того же пакета. Зона AST-Z3 пустеет, **K03 `assign()` падает** (`AttributeError`, дефект **D3**). Тесты приложения: `errors=2`, пересборка невозможна |
| C7-S2. K10 обновился, evidence.js — нет (синтетика) | XFAIL | Место перенесено, `data.js` пересобран. Тесты приложения OK, а демо молча показывает старый район. После пересборки меняется 1 место |
| C7-S3. Код K03 обновлён до v2 | XFAIL | До пересборки ничего не ловит. После пересборки `assign()` возвращает `k03_assign_v2`, а метка `evidence.js` — `k03_assign_v1`: **метка берётся из `boundary_registry.json`, а не из кода** |

`--url` (через `serve.py` на 127.0.0.1): только URL — PASS 2, XFAIL 1 (C6), SKIP 1; URL + `--app-root` — PASS 6, XFAIL 3.

## 2. Найденные проблемы

1. **D3 — модуль K03 (round 3 и patch v2), а не BUILD.** Если в новой версии слоёв зона неоднозначности пуста, `polygonal()` возвращает пустую GeometryCollection. Её `.boundary` равен `None`, и `assign()` падает на первой точке Астаны. Реалистичный путь: следующий выпуск Overture включит правку пути 903345831, слои совпадут, AST-Z3 исчезнет, и пересборка демо станет невозможной. Самопроверка K03 тоже падает: в ней есть случаи, построенные по зонам.
2. **P1-a. Нет привязки к версии.** `place_district` не хранит ни координаты, по которым сделана привязка, ни хеши кода и слоёв K03. Тесты BUILD сверяют только K10 с `package_manifest.json`; входы K03 и согласованность `evidence.js` с `data.js` не проверяются. Устаревшая привязка видна только после ручной пересборки.
3. **P1-b. Метка правила не связана с кодом.** `assign_rule` читается из реестра, а `method.id` и `source_id` захардкожены как `k03_assign_v1`. После обновления кода метка продолжает говорить v1.
4. **Наблюдение вне границ.** `tools/explain_ref.py` импортирует `agent/` из корня репозитория (`APP.parents[1]`). В извлечённой копии вне репозитория он падает и на baseline (`No module named 'agent'`). На тесты не влияет, но шаг пересборки не переносим.

## 3. Предложение (patch-файлы в этой папке, не применены)

**P2 — `patches/k03_assign_v2_1.patch`.** Это кумулятивный patch к `research/round-3-results/K03/boundary_validator.py` @ `44585de`: правило v2 из round 4 (D1, D2) плюс защита от пустых зон (D3).
- В `assign()` пустая зона пропускается.
- В `selftest()` случаи, построенные по зонам, включаются, только если зона есть.
- В `build_registry()` для пустой зоны `rep_point` равен `None`.

Правило остаётся `k03_assign_v2`: где v2 не падал, исход не меняется. Применение:
- в BUILD: `git apply --directory=prototypes/city-evidence/inputs/k03_root <patch>` из корня репозитория;
- в K03: `git apply <patch>`.

После применения нужно обновить `source_manifest.json` (так делает `copy_inputs.py` из нового коммита K03) и перегенерировать `boundary_registry.json` валидатором. Иначе в реестре останется метка v1; сборка с P1 об этом предупреждает.

**P1 — `patches/build_p1_binding.patch`** (к `prototypes/city-evidence` @ `0bf27de`):
- новый `tools/check_evidence_fresh.py` (только stdlib). В нём единственное описание формата `k03-binding-v1`: хеши кода и слоёв K03, дайджест мест `data.js` по городам, `digest`, а также `lonlat` в каждой записи `place_district`. Скрипт возвращает код 1, если что-то изменилось после сборки;
- `tools/build_evidence.py`:
  - проверяет входы K03 по `source_manifest.json`;
  - требует актуальный `data.js` и записывает `lonlat`;
  - берёт метку правила из `assign()['rule']`; правило реестра пишется отдельно в `registry_rule`, а при расхождении выводится предупреждение;
  - заполняет `boundary_version = k03-binding:<digest16>` в наблюдениях `district_status`;
  - записывает `boundary_binding`;
- `tests/test_inputs.py` — класс `EvidenceFresh` (без shapely):
  - закоммиченный `evidence.js` актуален;
  - изменение слоя K03 ловится;
  - перенос места в `data.js` ловится.

**Проверка предложения** (`verify_proposal.py` → `proposal_check/patched_0bf27de_p1_p2.json`). Во временной копии с раскладкой репозитория: P2 + P1 → обновлён `source_manifest` → `build_data` → `build_evidence` → `explain_ref` → тесты.

- Все шаги прошли с кодом 0:
  - `unittest`: 10 из 10 (7 исходных + 3 новых);
  - `node tests/conformance.cjs`: all passed;
  - `check_evidence_fresh`: актуален;
  - `expected_explanations.json` после `explain_ref` не изменился.
- `test_boundaries_demo.py` на этой копии: **PASS 13, XFAIL 0, FAIL 0**:
  - C2 — поведение, `assign()`, `evidence.js` и `method.id` согласованно указывают v2;
  - C3 — все 5 фикстур проходят;
  - C6 — привязка совпадает;
  - C7-S1/S2/S3 — устаревание ловится **до пересборки** тремя способами (тест приложения `failures=1`, binding, `check_evidence_fresh`); S1 пересобирается без исключения; после пересборки метка равна правилу кода.
- Playwright `smoke.cjs` в копии не запускался.

## 4. Как сборщику повторить на исправленной версии

```bash
git fetch origin <ветка BUILD>
python3 research/round-5-results/K03/extract_build.py --sha <новый SHA> --out /tmp/app
python3 research/round-5-results/K03/test_boundaries_demo.py --app-root /tmp/app --json /tmp/k03.json
# или по запущенному демо: --url http://127.0.0.1:8765/ [--app-root /tmp/app]
```

На исправленной версии XFAIL должны стать PASS. Если какой-то из них станет FAIL, это дефект новой версии. На baseline 0bf27de все 6 XFAIL — известные дефекты, не регрессии.
