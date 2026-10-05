# K03 round 6 — REVIEW «Свежесть районов и пустая геометрия»: STATUS

| Поле | Значение |
|---|---|
| Роль / слот | REVIEW, K03 (`research/round-6/review/K03.txt` @ `edee718`) |
| Ветка | `claude/epic-curie-iitc43` |
| **Проверенная сборка (target)** | `claude/beautiful-clarke-sbzomj` @ **`064ed25368341edaa50289bc29e21dda7bdd9440`**, `prototypes/city-evidence/`; сборка использует K03 из `inputs/k03v2_root` |
| Источник теста | `0ff776d17aa2e723faabc1db83e9b423955874e8` — `accept_k03.py`, `repro_d3.py` |
| Обновлено | 2026-10-05, ~09:00 UTC |
| Статус | **done** для объёма задания. Итог приёмки: **FAIL** — I2 выполнен, I1 и I3 нет (`ACCEPTANCE.json`) |

Сборку 0bf27de я заново не проверял. Результаты раунда 5 к 064ed25 не переносились.

## Прогоны (реально выполнены на 064ed25)

1. **Тест раунда 5 без изменений** (`test_boundaries_demo.py` @ 5715a7f) → **TEST_INCOMPATIBLE**, лог `runs/r5_test_on_064ed25.txt`. Причины:
   - путь K03 жёстко `inputs/k03_root`, поэтому тест грузил исходный v1-модуль, которым сборка не пользуется. Отсюда ложный FAIL C2;
   - наблюдения переименованы в `k03_district_status.*`;
   - список XFAIL раунда 5 к новой сборке не применяется;
   - сценарии меняли неиспользуемую копию; S2 упал на новой проверке атрибуции K08 в `build_data.py`.

   Адаптер — `accept_k03.py`:
   - корень K03 берётся из `K03_DIR` в `tools/build_evidence.py`;
   - XFAIL нет;
   - устаревание проверяется собственным `tools/check_all.py` сборки во временных копиях с раскладкой репозитория (`agent/` из 064ed25).
2. **`accept_k03.py --app-root <копия 064ed25> --repo-sha 064ed25…`** → **PASS 7, FAIL 2, SKIP 0, INFO 1** (`runs/accept_064ed25.json`):
   - **I0** — исходная копия: `check_all.py` 13 passed / 0 skipped / 0 failed; 120 мест `data.js`, пересчитанные модулем `inputs/k03v2_root`, совпадают с `place_district`.
   - **I3** — правило: **FAIL**.
     - Поведение v2 подтверждено 5 ключевыми фикстурами (R1–R5), а не надписью.
     - Код, `evidence.assign_rule`, `method.id` и `source_id` восьми наблюдений — `k03_assign_v2`; `source.sha256` равен sha256 модуля.
     - Подмена кода на исходный v1 ловится `check_all`: падают manifest K03 v2, rebuild и unittest.
     - **Но в той же копии** `boundary_registry.json:assignment_rule.id` и `validator_selftest.json:rule` = `k03_assign_v1` (19 случаев; код даёт 21). Их не обновляет `tools/setup_k03_v2.py`.
   - **I1** — пустая AST-Z3 после реальной синхронизации слоёв: **FAIL**. `assign()` падает с `AttributeError` в `inputs/k03v2_root/research/round-3-results/K03/boundary_validator.py:113`, `build_evidence` — код 1. Это D3 из раунда 5; patch v2.1 в сборку не вошёл.
   - **I2** — устаревший `place_district`: **PASS**.
     - Перенос точки (синтетика; sha обновлён во всех 11 ссылающихся файлах, как при корректной выгрузке) и сдвиг слоя Сарыарки (синтетика) до пересборки ловятся шагом `check_all` «web/evidence.js == rebuild».
     - Пересборка меняет 1 и 5 привязок соответственно, после неё этот шаг проходит.
     - После сдвига слоя ожидаемо падают проверки эталона объяснений: его нужно пересоздать.
   - **INFO** — изменение файла слоя в `inputs/k03v2_root`, не меняющее привязок, `check_all` не замечает: файлы копии, кроме `boundary_validator.py`, не сверяются ни с каким манифестом. Это не блокирует приёмку.
3. **`repro_d3.py --app-root <копия 064ed25>`** → код 1, трассировка в `runs/repro_d3_064ed25.txt`.

## Ограничения

- Сценарии I1/I2 моделируют обновления данных:
  - I1 — реальные геометрии пакета, сама синхронизация смоделирована;
  - I2 — синтетические изменения, помечены.
- Обнаружение устаревания в I2 требует shapely и pyproj. Без них `check_all` пропускает пересборку (SKIP), и это не PASS. Само демо в браузере устаревание не обнаруживает.
- Окружение: Linux, Python 3.11.15, shapely 2.1.2, pyproj 3.7.2, Node v22.22.0. Smoke-тест Playwright не запускался: к инвариантам K03 он не относится.

## Следующий шаг

Сборщику:
1. Применить `research/round-5-results/K03/patches/k03_assign_v2_1.patch` @ 5715a7f к `inputs/k03v2_root` (через `setup_k03_v2.py`).
2. В `setup_k03_v2.py` перегенерировать `boundary_registry.json` и `validator_selftest.json` валидатором v2.
3. Повторить:
   ```bash
   python3 research/round-6-results/K03/accept_k03.py --app-root <копия нового SHA> --repo-sha <новый SHA>
   ```
   Ожидание: FAIL 0.

## Воспроизведение

```bash
git fetch origin claude/beautiful-clarke-sbzomj
python3 research/round-5-results/K03/extract_build.py --sha 064ed25368341edaa50289bc29e21dda7bdd9440 --out /tmp/app6
pip install shapely==2.1.2 pyproj          # и node для шага facts в check_all
python3 research/round-6-results/K03/accept_k03.py --app-root /tmp/app6 --repo-sha 064ed25368341edaa50289bc29e21dda7bdd9440 --json /tmp/acc.json
python3 research/round-6-results/K03/repro_d3.py --app-root /tmp/app6
```
