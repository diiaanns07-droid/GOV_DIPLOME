# K05 round 5 (REVIEW). Совместимость K12 patch, k05r4_contract v1.2 и BUILD

Дата: 2026-10-05. Ветка `claude/optimistic-davinci-1oiqs9`. Проверялась готовая сборка `prototypes/city-evidence` из K04 @ `0bf27de`; во временный каталог она извлекалась через `git archive`, в ветку не копировалась. Входы: patch K12 @ `3e84039`, мой v1.2 @ `4205160`; манифест — `inputs/MANIFEST.json`.

**Всё в `patches/` и `proposed/` — предложения. К сборке они не применялись; FIXED не заявляется.** Проверены они только на временных копиях сборки.

## 1. Вывод

1. **Patch K12 совместим со сборкой.** Копия `inputs/k05_root/.../k05r3_contract.py` в сборке побайтно совпадает с `d913554`. Patch применяется командой `patch -p2` в `inputs/k05_root`, результат совпадает с `K12/patched/` (sha256 `b6856121…`). После него `tools/build_evidence.py` даёт `web/evidence.js` **побайтно тот же**, что закоммичен (sha256 `7e905a3a…`): 0 ошибок K05, то же число предупреждений. На текущих данных сборки patch ничего не ломает.
2. **K12 и v1.2 (`k05r4_contract`, 4205160) несовместимы в двух местах.** Оба случая воспроизводятся `repro_incompat.py`:
   - **BOUNDARY_MIX.** K12 считает слоем границ всё до `r<id>@<версия>`. У квадратов v1.2 такого суффикса нет, а `boundary_version` у каждого своя (`k10_r3_square:r11_c12@…`). Поэтому сумма двух непересекающихся квадратов одного города отклоняется ошибкой `BOUNDARY_MIX`.
   - **expected_units.** `aggregate_sum` в v1.2 не принимает этот аргумент (`TypeError`), поэтому полнота географии из K12 через v1.2 недоступна.
3. **`COUNT_DOMAIN` из K12 не защищает реальные данные.** Правило срабатывает только при `unit == "count"`, а сборка и K05 r3/r4 используют `records` и `segments`. Значения −3 и 2,5 записи проходят.
4. **В сборке нет проверки набора записей.** `build_evidence.py` не вызывает `validate_dataset`: до K12 такой функции и не было. Кроме того, JSON пишется без `allow_nan=False`. Сейчас данные чистые (проверки D01–D06), но защиты нет.

Решение: три минимальных patch-предложения. v1.3 не создаётся, схема не меняется.

## 2. Матрица совместимости (фактические прогоны `k05r5_compat.py`)

Обозначения: ✓ — PASS, ✗ — ожидаемое падение (EXPECTED_FAIL).

| Проверка | baseline 0bf27de | +K12 | +K12, v1.2 compat | полная цепочка |
|---|---|---|---|---|
| D01 evidence.js — строгий JSON | ✓ | ✓ | ✓ | ✓ |
| D02 уникальные obs_id в сборке | ✓ | ✓ | ✓ | ✓ |
| D03 null ⇔ missing | ✓ | ✓ | ✓ | ✓ |
| D04 честный 0 (reported_zero только при полном охвате) | ✓ | ✓ | ✓ | ✓ |
| D05 конечные целые счётчики records/segments | ✓ | ✓ | ✓ | ✓ |
| D06 город раздела = city_id | ✓ | ✓ | ✓ | ✓ |
| D07 validate_dataset сборки | ✗ нет функции | ✓ | ✓ | ✓ |
| D08 validate на всех записях | ✓ | ✓ | ✓ | ✓ |
| M01 NaN в v1.1 | ✗ принят | ✓ | ✓ | ✓ |
| M02 Infinity в v1.2 (поверх v1.1) | ✗ принят | ✓ | ✓ | ✓ |
| M03 NaN в aggregate_sum | ✗ принят | ✓ | ✓ | ✓ |
| M04 bbox + район → SPATIAL_MIX | ✓ | ✓ | ✓ | ✓ |
| M05 v1.1 (E02/BUILD) + v1.2 → LEGACY_UNIT | ✓ | ✓ | ✓ | ✓ |
| M06 сумма 0 при неполном охвате → missing | ✗ reported_zero | ✓ | ✓ | ✓ |
| M07 честный 0 / 0 при missing / 0 при partial | ✓ | ✓ | ✓ | ✓ |
| M08 повтор obs_id → DUPLICATE_OBS_ID | ✗ нет функции | ✓ | ✓ | ✓ |
| M09 два непересекающихся квадрата суммируются | ✓ | **✗ BOUNDARY_MIX** | ✓ | ✓ |
| M10 expected_units через v1.2 | ✗ TypeError | **✗ TypeError** | ✓ | ✓ |
| M11 пересекающиеся bbox → OVERLAP | ✓ | ✓ | ✓ | ✓ |
| M12 COUNT_DOMAIN для records | ✗ | ✗ | ✗ | ✓ |
| **Итог** | 12 ✓, 8 ✗ | 17 ✓, 3 ✗ | 19 ✓, 1 ✗ | **20 ✓** |

Неожиданных результатов (FAIL или XPASS) нет ни в одном варианте. Результаты лежат в `results/*.json`. Полная цепочка проверена дважды: через `--app-root` и через `--url` на локальном `serve.py`.

## 3. Порядок применения и переноса

Пути даны относительно корня репозитория с `prototypes/city-evidence`.

1. **K12 patch → копия v1.1 в сборке:**
   `patch -p2 -d prototypes/city-evidence/inputs/k05_root < research/round-4-results/K12/patches/k05r3_contract_stress_fixes.patch`
   Затем обновить sha256 этого файла в `source_manifest.json` (`b6856121…`).
2. **Домен счётчика (только после шага 1, без K12 не применяется):**
   `patch -p2 -d prototypes/city-evidence/inputs/k05_root < research/round-5-results/K05/patches/k05r3_count_units_after_k12.patch`
   Итоговый sha256 файла — `7f5f76a8…`.
3. **Перенос v1.2 нужен, только если сборка переходит на квадраты с `spatial_unit`.** Скопировать `research/round-4-results/K05/k05r4_contract.py` @ 42051600 в `inputs/k05_root/round-4-results/K05/`, затем:
   `patch -p2 -d prototypes/city-evidence/inputs/k05_root < research/round-5-results/K05/patches/k05r4_contract_k12_compat.patch`
   Итог равен `proposed/k05r4_contract.py` (sha256 `acd75a17…`). Импорт v1.1 в v1.2 работает в раскладке `k05_root` без правок. Этот же patch применяется и к моей ветке (`git apply --check` ok). Без K12 он безвреден: на baseline M09 проходит, а M10 ожидаемо падает.
4. **Сборка:**
   `patch -p1 < research/round-5-results/K05/patches/build_evidence_dataset_check.patch`
   Добавляет `validate_dataset`, если функция есть в контракте, и `allow_nan=False`.
5. **Пересборка:** `python tools/build_evidence.py`. На временной копии после шагов 1–4 `evidence.js` побайтно не изменился (`7e905a3a…`).
6. **Проверка:** `python research/round-5-results/K05/k05r5_compat.py --app-root prototypes/city-evidence --k05r4 prototypes/city-evidence/inputs/k05_root/round-4-results/K05/k05r4_contract.py`. Ожидается 20 PASS и код выхода 0.

Шаги 1 → 2 строго последовательны. Шаги 3 и 4 от них не зависят, но M10 проходит только вместе с шагом 1.

## 4. Регрессия предложений

| Набор | Результат |
|---|---|
| K12 `stress_runner.py` (57 фикстур) на `patched` и на `patched` + домен счётчика | 34/34, 6/6, 13/13, 4/4 в обоих; построчно без расхождений. Контроль R32 (`count_change` −5 допустим) не задет |
| Мои `test_k05r3.py`, `test_k05r4.py`, `test_k05_validator.py` при K12 + домен счётчика + v1.2 compat | OK, OK, OK |
| `k05r4_adapter.py` при той же цепочке | `examples/` и `cases/` побайтно те же |
| `build_evidence.py` на baseline, +K12 и полной цепочке | `evidence.js` побайтно равен закоммиченному во всех трёх |

## 5. Тест для сборщика

`k05r5_compat.py` принимает `--app-root <копия city-evidence>` или `--url <адрес web/> --contract-root <inputs/k05_root>`.

- Вариант контракта определяется по sha256 файла `k05r3_contract.py`. Ожидаемые падения заданы **только** для известных вариантов: baseline, +K12, +K12 + домен счётчика.
- Исправленная версия с другим sha получает статус `unknown:<sha>`. Каждое падение тогда показывается как FAIL, код выхода 1. Пример — копия baseline с одной добавленной строкой комментария: 8 FAIL.
- Перед тем как считать исправленную версию проверенной, её нужно прогнать через этот тест и указать её SHA. Падения baseline не являются дефектами новой версии.

## 6. Ограничения

- Все M-проверки идут на синтетических фикстурах (`FIXTURE.*`); D-проверки — на реальном `evidence.js` сборки.
- Браузерная часть сборки (`app.js` и чтение `evidence.js` страницей) не проверялась; проверен только файл данных и сервер `serve.py`.
- Интерфейс сборки после шага 3 не менялся: `build_evidence.py` по-прежнему пишет v1.1. Переход сборки на v1.2 — отдельное решение сборщика.
- `--url` проверялся только на локальном сервере.

## 7. Воспроизведение

```bash
pip install shapely==2.1.2 pyproj==3.7.2        # только для build_evidence.py
git archive 0bf27deb8549b325b34a9610402613d745544edb prototypes/city-evidence | tar -x -C /tmp/b
python research/round-5-results/K05/k05r5_compat.py --app-root /tmp/b/prototypes/city-evidence --json /tmp/r.json
python research/round-5-results/K05/repro_incompat.py --k05-root /tmp/b/prototypes/city-evidence/inputs/k05_root
# затем шаги §3 на /tmp/b и повтор проверки
```
