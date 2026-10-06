# K10, раунд 9 — передача

**Состояние:** этапы 1–2 из 3. Следующий шаг — этап 3: синтетические крайние случаи и итоговые проверки.

## Этап 1: регрессия одной командой

```bash
python3 research/round-9-results/K10/regress.py --sha <BUILD sha>          # из корня репозитория; нужен node
python3 -m unittest discover -s research/round-9-results/K10/tests -p "test_regress.py" -v
```

Шаги (итог в `results/<sha7>/summary.json`):

1. **EXTRACT** — `prototypes/city-evidence` копируется из git побайтно, с пересчётом git blob id. Манифест сохраняется в `extract_manifest.json`.
2. **FROZEN_PACKS** — пакеты r8 (`research/round-8-results/K10/packs`, 161 файл) побайтно равны `frozen/r8_packs.json`, снятому с коммита `c8df74b`. Ожидания из BUILD не пересоздаются: они посчитаны оракулом K10 в r8.
3. **SOURCE_HASHES** — sha256 двух файлов `inputs/k10/.../places_social.geojson` и `package_manifest.json` равны значениям в пакете K10 (git `602f0c0`, `frozen/sources.json`). sha256, указанный в `web/data.js`, тоже совпадает.
4. **SOURCE_IDS** — в `web/data.js` по каждому городу те же ID и группы, что в пакете K10. lon/lat равны значениям пакета, округлённым до 6 знаков: Шымкент 55 записей, Астана 65; школ 15/8, поликлиник 16/16.
5. **R8_SUITE** — `research/round-8-results/K10/tests/run_build_suite.py`: пакеты против данных, пересчёт оракулом, JS-геометрия, unit-тесты, verify-inputs, прогон через `web/plan.js`, круг экспорта, мутанты `plan.js`.

Результат на `d865dd4a124291e10dd0b7bb1d9eada20d34c268`: все 5 шагов PASS, внутри R8_SUITE все 6 подшагов PASS. Экспорт 30/30, мутанты 15/15.

`tests/test_regress.py` проверяет, что регрессия замечает изменения: байт в geojson, сдвиг, удаление и смену группы записи, правку пакета r8.

`freeze.py` пересоздаёт `frozen/` из git-объектов. Запускать не нужно, файлы уже в репозитории.

## Этап 2: конверты `city-resilience-v1` на реальных срезах

```bash
cd research/round-9-results/K10
python3 -m k10res.envelopes --app-root <d865dd4>/prototypes/city-evidence --commit d865dd4a124291e10dd0b7bb1d9eada20d34c268 --out envelopes
python3 tests/check_envelopes.py --app-root <d865dd4>/prototypes/city-evidence --json results/d865dd4/check_envelopes.json
```

### Модули

- **`k10res/oracle_res.py`** — независимый оракул устойчивости по `round-9/CORE_SPEC.txt`. Геометрия, строгий JSON и валидация плана берутся из оракула K10 r8. Слой устойчивости написан заново по спецификации, не переведён из кода BUILD.
  - `validate_resilience(obj, ctx)` проверяет конверт целиком и возвращает чистый конверт, где первым идёт автоматический случай `base`, остальные отсортированы по id.
  - Коды ошибок: `missing_field`, `unexpected_field`, `bad_schema_version`, `derived_not_allowed`, коды плана v2, `bad_id` (правило ID BUILD: NFC, буквы, цифры, `_ . -`), `too_many_candidates` (больше 12), `bad_case_count`, `reserved_case_id`, `duplicate_case_id`, `bad_label`, `bad_disabled`, `duplicate_id`, `unknown_source_id`, `candidate_id_not_source`.
  - `evaluate_resilience(ctx, env, ids)` по каждому случаю даёт метрики и строки: before/after/delta/nearest внутри случая. Плюс `worst_vector` и `worst_case_ids`.
  - `optimize_resilience(ctx, env)` возвращает: `status`; ручной (`manual`), обычный (`nominal`, оптимум mean на base) и устойчивый (`robust`, минимум `(W, L_base, cost, ids)`) планы; `price_of_robustness_m` и `price_reason`; `evaluated`, `feasible_count`; дайджесты `resilience_problem_digest`, `resilience_scenario_digest`, `exclusions_digest`; исходный `source_snapshot`.
- **`k10res/envelopes.py`** — генератор по правилам `RULES`, заданным до расчёта.

### Файлы

- `envelopes/*.json` — пакет: конверт, копия среза, исключённые записи с именами и QA-флагами, ожидаемое от оракула, наблюдения.
- `envelopes/inputs/*.json` — чистый конверт для импорта.
- `envelopes/INDEX.json` — манифест происхождения: сборка, sha256 файлов, правила, `not_built`.

### Правила исключения

Исключение условное: «считаем, как если бы этих записей не было в срезе». Это не утверждение о закрытии.

- **`relied`** — записи, ближайшие к наибольшему суммарному весу точек: случаи top1, top2, second.
- **`seeded`** — 1, 2 или 3 записи по LCG. Seed 20261006 + индекс, плюс 1000·K для случая sK.
- **`qa`** — только Шымкент. Случай qa_all — все записи категории с QA-флагом; случай colocated — крупнейшая группа с одинаковыми координатами.

Для Астаны QA-конвертов нет: у её школ и поликлиник нет QA-флагов (`not_built`).

### Результаты (оракул; обычный и устойчивый план совпали или нет — как вышло)

| Конверт | Случаи (сколько записей исключено) | Обычный | Устойчивый | Совпали | Цена, м | Худшие случаи (robust) |
|---|---|---|---|---|---|---|
| `astana-outpatient_clinic-relied` | top1(1), top2(2), second(1) | c03+c10+c12 | c07+c09+c12 | нет | 10.585 | top2 |
| `astana-outpatient_clinic-seeded` | s1(1), s2(2), s3(3) | c03+c10+c12 | c07+c10+c12 | нет | 9.264 | s3 |
| `astana-school-relied` | top1, top2, second | c03+c07+c12 | = | да | 0.000 | top2 |
| `astana-school-seeded` | s1, s2, s3 | c03+c07+c12 | = | да | 0.000 | s2 |
| `shymkent-outpatient_clinic-qa` | qa_all(7), colocated(4) | c02+c03+c12 | = | да | 0.000 | colocated, qa_all (ничья) |
| `shymkent-outpatient_clinic-relied` | top1, top2, second | c02+c03+c12 | = | да | 0.000 | second, top2 (ничья) |
| `shymkent-outpatient_clinic-seeded` | s1, s2, s3 | c02+c03+c12 | = | да | 0.000 | s1, s3 (ничья) |
| `shymkent-school-qa` | qa_all(7), colocated(3) | c01+c03+c07 | = | да | 0.000 | qa_all |
| `shymkent-school-relied` | top1, top2, second | c01+c03+c07 | = | да | 0.000 | top2 |
| `shymkent-school-seeded` | s1, s2, s3 | c01+c03+c07 | = | да | 0.000 | s3 |

Цена устойчивости = base `weighted_mean_mm` устойчивого минус обычного, в метрах. Это расстояние по прямой, не тенге и не время.

### Проверки (`check_envelopes.py`)

- **SOURCE** — копия среза и snapshot совпадают со сборкой; все исключённые ID — настоящие записи категории.
- **VALID** — конверт проходит валидацию.
- **RECOMPUTE** — пересчёт оракулом из собственной копии пакета даёт то же ожидаемое.
- **ORDER** — перевёрнутые массивы случаев, ID, точек и кандидатов дают тот же результат и те же дайджесты.
- **CROSS_R8** — независимый путь. По каждому случаю считается оракул r8 v2 на копии среза без исключённых записей. Обычный план = mean оракула r8. Устойчивый план = перебор всех допустимых наборов через r8.
- **INDEX**, **IMMUTABLE**.

Результат на d865dd4: 10/10 PASS.

**Интеграция с BUILD: NOT_RUN** — на момент проверки в BUILD нет `resilience.js` / city-resilience-v1, ветка стоит на `d865dd4`.
