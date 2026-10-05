# K05 round 5 (REVIEW) — совместимость исправлений контрактов: STATUS

Роль: REVIEW, slot K05. Ветка `claude/optimistic-davinci-1oiqs9`. Статус: **done** для объёма задания (тест, матрица, patch-предложения, порядок применения). Patch-и — только предложения, к сборке не применены; FIXED не заявляется.
Задание: `research/round-5/review/K05.txt` @ codex/research-import-2026-10-05 (2883aeb).
Входы (манифест `inputs/MANIFEST.json`, git blob сверен):
- BUILD K04 `claude/beautiful-clarke-sbzomj` @ 0bf27deb8549b325b34a9610402613d745544edb, `prototypes/city-evidence/` (проверялся через `git archive` во временный каталог; в ветку не копировался);
- K12 `claude/save-work-handoff-xuav3q` @ 3e8403931f823eb6b688462fb46e91d520628c11: `patches/k05r3_contract_stress_fixes.patch`;
- свой v1.2 `k05r4_contract.py` @ 42051600fd2a7486be3d0e27a29e802a7bfad7aa.

## Сделано
- `k05r5_compat.py --app-root <копия city-evidence> | --url <адрес> --contract-root <k05_root>`: 8 проверок данных `web/evidence.js` (D01–D08) + 12 проверок матрицы контрактов (M01–M12). Вариант контракта определяется по sha256; ожидаемые падения baseline помечены EXPECTED_FAIL.
- `results/baseline_0bf27de.json`, `results/baseline_0bf27de_plus_K12.json`.

## Проверки (реально выполнены)
- K12 patch к копии в сборке: `patch -p2` в `inputs/k05_root` — применяется; sha256 результата b6856121… = `K12/patched/.../k05r3_contract.py`.
- `tools/build_evidence.py` (shapely 2.1.2, pyproj 3.7.2) на baseline и на baseline+K12: `evidence.js` побайтно = закоммиченному (sha256 7e905a3a…), 0 ошибок K05 в обоих.
- `k05r5_compat.py` на baseline: 0 неожиданных (8 EXPECTED_FAIL); на baseline+K12: 0 неожиданных (3 EXPECTED_FAIL: M09, M10, M12).

## Найдено (подтверждено воспроизведением)
- K12 + v1.2: две непересекающиеся bbox одного города → `BOUNDARY_MIX` (K12 считает слоем всё до `r<id>@<версия>`, у квадратов такого суффикса нет).
- v1.2 `aggregate_sum` не принимает `expected_units` (TypeError) — полнота географии K12 недоступна через v1.2.
- `COUNT_DOMAIN` K12 срабатывает только для `unit=count`; сборка и K05 r4 используют `records`/`segments` — -3 и 2.5 записей проходят.

## Сделано в checkpoint 2
- `patches/k05r3_count_units_after_k12.patch` (COUNT_DOMAIN для records/segments, только после K12), `patches/k05r4_contract_k12_compat.patch` (+ `proposed/k05r4_contract.py`), `patches/build_evidence_dataset_check.patch`.
- `repro_incompat.py` — воспроизведение BOUNDARY_MIX и TypeError expected_units.
- `REPORT.md` — матрица 4 вариантов × 20 проверок и точный порядок применения.

## Дополнительные проверки (реально выполнены)
- Полная цепочка (K12 → count units → v1.2 compat → build_evidence) на временной копии сборки: все 4 patch применились; `evidence.js` побайтно тот же (7e905a3a…); `k05r5_compat.py` 20 PASS через `--app-root` и через `--url` (локальный serve.py).
- Неизвестный вариант (копия baseline + одна строка): 8 FAIL, код 1 — ожидания не маскируют новую версию.
- K12 `stress_runner.py` на K12 и K12+count units: 57/57 в обоих, без построчных расхождений.
- Мои `test_k05r3.py`, `test_k05r4.py`, `test_k05_validator.py` при полной цепочке — OK; выходы `k05r4_adapter.py` побайтно те же.

## Ограничения
Матрица M — синтетические фикстуры; браузер не проверялся; переход сборки на v1.2 — решение сборщика.

## Следующий шаг
Сборщику: применить шаги 1, 2, 4 из REPORT §3 (шаг 3 — при переходе на квадраты v1.2), пересобрать и прогнать `k05r5_compat.py --app-root`; сообщить новый SHA для независимой проверки.
