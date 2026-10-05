# K12, раунд 5, REVIEW: негативные входы на пути сборки `prototypes/city-evidence`

Слот K12, роль REVIEW. Ветка `claude/save-work-handoff-xuav3q`. Задание:
`research/round-5/review/K12.txt` @ `2883aeb`.
Проверяемый BUILD: `claude/beautiful-clarke-sbzomj` @ `0bf27deb8549b325b34a9610402613d745544edb`.

> Все мутированные значения синтетические. Они создаются во временных копиях и в репозиторий не
> попадают. Реальные данные K10 и `prototypes/city-evidence/` не менялись.

## Что проверяется и как

Путь пересборки по README BUILD:

1. `tools/build_data.py` → `web/data.js`;
2. `tools/build_evidence.py` (K03 `assign()` + K05 `validate()`) → `web/evidence.js`.

Оба шага читают K10 через общий `load_layer()`: sha256, размер и число объектов против
`package_manifest.json`, затем `json.loads`.

`k12r5_negative_build.py --app-root <копия>`:

- для каждого случая создаётся временная копия приложения и меняется один вход;
- для семантических случаев пересчитываются `package_manifest.json` (sha256, bytes, features) **и**
  `source_manifest.json`. Отказ по hash не может скрыть отсутствие семантической проверки;
- оба шага запускаются как subprocess, `offline_check.py` K10 — справочно.

**Требование:** оба шага отказывают с диагностикой (код ≠ 0, без traceback), а
`web/data.js` и `web/evidence.js` остаются побайтно прежними.
**Класс отказа:** «целостность», если сообщение содержит `INTEGRITY`, `sha256`, «размер не совпад…»
или «нет файла»; иначе «семантика». Префикс `SEMANTIC` имеет приоритет.

`--url <адрес>` проверяет то, что видит браузер: строгий разбор `data.js` и `evidence.js`, уникальность
id, точки в bbox города, конечность чисел, согласованность выпуска, `places.total` против числа id,
`city_mismatch`.

## Результат на BUILD `0bf27de` (baseline)

Извлечённая копия проходит собственные проверки BUILD: unittest 7 OK, `conformance.cjs` — all passed.
Чистая пересборка побайтно равна закоммиченным `data.js` и `evidence.js`.

| Случай | Шаги сборки | Выход перезаписан | След в доставленных файлах (`--url`) | `offline_check` |
|---|---|---|---|---|
| C01 чистая копия | приняты | нет (побайтно равен) | — | ok |
| C02 байт без hash | отказ целостности ×2 | нет | — | ловит |
| I01 данные + package_manifest согласованы, source_manifest нет | **приняты** | **да** | нет | не ловит |
| N01 `NaN` в confidence | **приняты** | **да**, в data.js `NaN` | `JSON_NONFINITE`, `NONFINITE_CONFIDENCE` | **не ловит** |
| N02 `NaN` в координате | **приняты** | **да** | `NONFINITE_COORD` | ловит (как «вне bbox») |
| N03 `Infinity` в длине | **приняты** | **да**, `Infinity` | `NONFINITE_LENGTH` | ловит |
| N04 `1e999` в длине (строгий JSON) | **приняты** | **да**, `Infinity` | `NONFINITE_LENGTH` | ловит |
| N05 повтор ключа `k10_group` | **приняты** | **да**: школа стала аптекой | **нет** | **не ловит** |
| N06 конфликт id | **приняты** | **да**: `places.total` 56 при 55 id | `DUPLICATE_PLACE_ID`, `PLACES_TOTAL` | ловит |
| N07 точка в квадрате другого города | **приняты** | **да** | `PLACE_OUTSIDE_BBOX`, `CITY_MISMATCH` | ловит |
| N08 bbox заголовка ≠ манифест | **приняты** | **да** | **нет** | ловит |
| N09 выпуск слоя 2026-08-20.0 ≠ 2026-09-23.1 | **приняты** | **да** | **нет** | ловит |

**Выводы:**

1. Путь сборки отклоняет только нарушения hash, размера, числа объектов и отсутствие файла.
   Ни одна семантическая проверка (конечность, повтор ключа, уникальность id, bbox, выпуск) на пути
   нет, и при каждом таком входе оба выходных файла перезаписываются заражёнными данными.
2. `source_manifest.json` хранит хэши копий, но сборка его не сверяет. Согласованная подмена
   данных и `package_manifest.json` проходит (I01).
3. `offline_check.py` K10 указан в README отдельным шагом, но сборка от него не зависит. Даже он не
   ловит NaN в `confidence` (N01) и повтор ключа (N05).
4. **`--url` неполон по природе.** N05, N08, N09 и I01 не оставляют следа в доставленных файлах:
   выход выглядит чистым, а собран из неверных входов. Решает только проверка на пути сборки.
   Проверка `--url` на `serve.py`: чистый baseline — clean; та же копия после принятия N01 —
   `JSON_NONFINITE`, `NONFINITE_CONFIDENCE` (`results/url_*.json`).

Это **ожидаемые падения baseline** (`BASELINE_0bf27de_EXPECTED.json`), а не дефекты новой версии:
новая версия не проверялась.

## Patch-предложение (не применено, не FIXED)

`patches/build_path_strict_inputs.patch`: меняет `tools/build_data.py` и `tools/build_evidence.py`.
Копии файлов — `patched/tools/`.

- `strict_loads`: NaN, Infinity и переполнение до inf (`1e999`) → отказ; повтор ключа → отказ.
- `check_anchor`: `package_manifest.json` и каждый файл K10 сверяются с `source_manifest.json` (INTEGRITY).
- `load_layer` после hash проверяет:
  - заголовок `release/city/bbox` равен манифесту;
  - `id` уникален, `id == overture_id`;
  - объекты лежат внутри bbox города;
  - `k10_group` известен.

  Отказы помечены `SEMANTIC:`. Проверки в общем `load_layer`, поэтому `build_evidence` отказывает так же.
- `write_atomic`: запись во временный файл и `os.replace`. `json.dumps(..., allow_nan=False)`.

**Проверено на `0bf27de` + patch:**

- `git apply --check` на чистом `0bf27de` — ok.
- `k12r5_negative_build.py` — 12 из 12 OK (`results/proposal_patch_on_0bf27de.json`): I01 и C02 — отказ
  целостности, N01–N09 — отказ семантики, выходы не меняются.
- C01: пересборка побайтно равна закоммиченной.
- Собственные тесты BUILD: unittest 7 OK, `conformance.cjs` — all passed.

**Не проверено:** `smoke.cjs` (Playwright) с patch. Устойчивость `write_atomic` к обрыву записи (kill
посреди записи) тестом не воспроизводилась, это свойство `os.replace`. Windows.

## Повтор на исправленной версии BUILD

```bash
git fetch origin claude/beautiful-clarke-sbzomj
python research/round-5-results/K12/extract_build.py <НОВЫЙ_SHA> /tmp/ce_new
python research/round-5-results/K12/k12r5_negative_build.py --app-root /tmp/ce_new \
       --python <python с shapely==2.1.2 pyproj==3.7.2> --out new.json   # требование: 12/12 OK, exit 0
cd /tmp/ce_new && python serve.py 8765 &
python research/round-5-results/K12/k12r5_negative_build.py --url http://127.0.0.1:8765/
```

Регрессия baseline: тот же запуск с `--expect-file research/round-5-results/K12/BASELINE_0bf27de_EXPECTED.json`
на `0bf27de` даёт exit 0 (XFAIL ×10). Самопроверка инструмента:
`python -m unittest discover -s research/round-5-results/K12/tests` — 6 OK.
