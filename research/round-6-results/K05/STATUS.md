# K05 round 6 (REVIEW) — приёмка контракта новой сборки: STATUS

Роль: REVIEW, slot K05. Ветка `claude/optimistic-davinci-1oiqs9`. Статус: **done** (приёмочный прогон выполнен; вердикт — 3 FAIL, см. ACCEPTANCE.json).
Задание: `research/round-6/review/K05.txt` @ codex/research-import-2026-10-05 (edee718).
**Target: `064ed25368341edaa50289bc29e21dda7bdd9440`** (`claude/beautiful-clarke-sbzomj`, `prototypes/city-evidence/`), проверен в detached worktree. Старая 0bf27de не перепроверялась.
Test source: `k05r5_compat.py` @ fb2dea6 (фикстуры) + новый адаптер `k05r6_accept.py` (sha256 в ACCEPTANCE.json).

## Результат
- Контракт сборки `k05-obs-v1.2+k12r4` загружен через её `tools/contract.py`: k05r3 = K12-патч (b6856121…), k05r4 = исходный (423cdfee…). Предложения K05 r5 не применены.
- 15 PASS / 3 FAIL, одинаково через `--app-root` и `--url` (локальный serve.py):
  - FAIL I1 COUNT_DOMAIN для records/segments: −3 и 2.5 принимаются (`k05r3_contract.py:115`, только `unit == "count"`). Данные сборки корректны (D05 PASS) — это незакрытая защита, которую BUILD r5 ISSUE_MATRIX называет fixed.
  - FAIL I2 expected_units через v1.2: TypeError (`k05r4_contract.py:89/104`). Латентно: сборка не вызывает aggregate_sum.
  - FAIL I3 две непересекающиеся bbox → BOUNDARY_MIX (`k05r3_contract.py:211-213` + `k05r4_contract.py:34`). Латентно.
  - PASS: строгий JSON, уникальные obs_id, null⇔missing, честный 0 (8 reported_zero при полном охвате), целые счётчики, город, validate_all сборки 0 ошибок; NaN в записи и агрегате; bbox vs район; v1.1 vs v1.2; 0-сумма при partial → missing; 0/missing/partial; повтор obs_id; OVERLAP.
- Минимальный repro: `repro_r6.py` (вывод `runs/repro_r6_064ed25.txt`), на реальной записи сборки.
- Исправления уже есть (не применены): `research/round-5-results/K05/patches/k05r3_count_units_after_k12.patch`, `k05r4_contract_k12_compat.patch`.

## Проверки (реально выполнены)
- `tools/check_all.py` сборки в полном worktree 064ed25: 13 passed, 0 failed. При извлечении только `prototypes/` — 11/1 (facts: StopIteration, K02 ищет корень репозитория) — среда, не продукт.
- `k05r6_accept.py --app-root` и `--url`: 15/3, вердикты совпали.
- `k05r5_compat.py` без изменений на 064ed25: **TEST_INCOMPATIBLE** (читает `inputs/k05_root` вместо `inputs/contract`, v1.2 из своей папки, D08 v1.1-валидатором на v1.2-записях, старые EXPECTED_FAIL) — `runs/r5_harness_unmodified_on_064ed25.json`.
- Первый вариант адаптера засчитывал M03 PASS по BOUNDARY_MIX вместо VALUE_NOT_FINITE — исправлено (вторая bbox в том же слое), прогон повторён.

## Ограничения
Инварианты M/I — синтетические фикстуры и одна реальная запись; браузер не проверялся (smoke сборки не запускался).

## Следующий шаг
Сборщику: применить два patch-а K05 r5 к `inputs/contract/` через `tools/setup_contract.py`, обновить манифест, затем повторить `python research/round-6-results/K05/k05r6_accept.py --app-root <checkout>/prototypes/city-evidence` и сообщить новый SHA.
