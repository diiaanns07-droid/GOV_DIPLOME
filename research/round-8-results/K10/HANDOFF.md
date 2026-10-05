# K10, раунд 8: пакеты сценариев city-plan-v2 — передача

**Состояние:** этапы 1–2 из 3 (см. `STATUS.md`). Следующий шаг — этап 3: CLI-предпросмотр `k10plan/cli.py` и итоговый HANDOFF.

## Что есть

- `k10plan/oracle.py` — независимый Python-оракул по `CORE_SPEC.txt` (stdlib): строгий JSON, валидация, `evaluate_plan`, точный перебор, три цели, Парето, чувствительность к бюджету.
- `k10plan/slice.py` — чтение реального среза из app root сборки (только чтение). `source_snapshot` совпадает с `web/whatif.js sourceSnapshot()` сборки a5b5e2d (проверено node).
- `k10plan/packs.py` — генератор пакетов по правилам `RULES`, заданным до расчёта.
- `packs/*.json` — 31 пакет; `packs/scenarios/*.json` — только вход `city-plan-v2` для импорта; `packs/scenarios/invalid/<pack>/<case>.json` — неверные файлы; `packs/INDEX.json` — список, sha256, правила, `not_built`.
- `tests/check_packs.py`, `tests/xcheck_build.cjs`, `tests/test_oracle.py`, `tests/run_mutants.py`.

## Пакеты и что получилось (ожидаемое посчитано только оракулом)

Перебрано / допустимо — число подмножеств с учётом `max_selected`, required и excluded / из них в бюджете.

| Пакет | Статус | Перебрано / допустимо | Победители | Цели совпали | Точек Парето |
|---|---|---|---|---|---|
| `shymkent-school-base` | optimal | 299/143 | все три: c01+c03+c07 | да | 7 |
| `shymkent-school-tight-budget` | optimal | 299/2 | c07 | да | 2 |
| `shymkent-school-required-excluded` | optimal | 37/12 | mean, minimax c02+c10+c12; coverage c04+c12 | нет | 4 |
| `shymkent-school-qa-nearest` | optimal | 299/143 | c01+c03+c07 | да | 7 |
| `shymkent-school-seeded` | optimal | 1471/371 | r09+r12+r14 | да | 7 |
| `shymkent-outpatient_clinic-base` | optimal | 299/143 | mean, minimax c02+c03+c12; coverage c01+c12 | нет | 10 |
| `shymkent-outpatient_clinic-tight-budget` | optimal | 299/2 | пустой план: единственный доступный c07 нигде не ближе существующих | да | 1 |
| `shymkent-outpatient_clinic-required-excluded` | optimal | 46/16 | c01+c12 | да | 4 |
| `shymkent-outpatient_clinic-qa-nearest` | optimal | 299/143 | как base | нет | 10 |
| `shymkent-outpatient_clinic-seeded` | optimal | 1471/682 | r04+r06+r11+r14 | да | 13 |
| `astana-school-base` | optimal | 299/143 | mean c03+c07+c12; minimax c11+c12; coverage c02+c07+c12 | нет, три разных | 6 |
| `astana-school-tight-budget` | optimal | 299/2 | c07 | да | 2 |
| `astana-school-required-excluded` | optimal | 46/13 | mean, minimax c11+c12; coverage c08+c12 | нет | 5 |
| `astana-school-seeded` | optimal | 1471/537 | три разных | нет | 14 |
| `astana-outpatient_clinic-base` | optimal | 299/143 | mean c03+c10+c12; minimax, coverage c08+c12 | нет | 9 |
| `astana-outpatient_clinic-tight-budget` | optimal | 299/2 | c07 | да | 2 |
| `astana-outpatient_clinic-required-excluded` | optimal | 46/14 | mean c01+c12; minimax, coverage c08+c12 | нет | 5 |
| `astana-outpatient_clinic-seeded` | optimal | 1471/259 | mean, minimax r03+r04+r08+r11; coverage r01+r04+r11 | нет | 13 |
| `*-conflict-budget` (4 шт.) | infeasible | 11/0 | `required_cost_exceeds_budget` | — | 0 |
| `*-conflict-count` (4 шт.) | infeasible | 0/0 | `required_count_exceeds_max_selected` | — | 0 |
| `shymkent-school-invalid-inputs`, `astana-school-invalid-inputs` | 45 случаев | — | 43 отказа до расчёта, 2 принять | — | — |
| `synthetic-objectives-differ` | optimal | 5/5 | mean e, minimax c, coverage b (задумано вручную) | нет | 4 |
| `synthetic-empty-baseline` | optimal | 37/36 | before = null, delta = null; пустой план не на Парето | нет | 8 |
| `synthetic-ties` | optimal | 4/4 | t1; источник выигрывает ничью у кандидата | да | 2 |

Совпадение или расхождение целей получилось само; seed и правила не подбирались. Для Астаны QA-пакеты **не построены**: в `web/evidence.js` нет групп `colocated` со школами или поликлиниками (`INDEX.json → not_built`).

## Команды

```bash
python3 research/round-5-results/K10/tools/extract_build.py --sha a5b5e2ddbe087c4eab8e947748cdf69dbae84a0d --out /tmp/b   # из корня репозитория
cd research/round-8-results/K10
python3 -m k10plan.packs --app-root /tmp/b/prototypes/city-evidence --commit a5b5e2ddbe087c4eab8e947748cdf69dbae84a0d --out packs
python3 tests/check_packs.py --app-root /tmp/b/prototypes/city-evidence --json results/check_packs_stage2.json
python3 -m unittest discover -s tests -p "test_*.py" -v
python3 tests/run_mutants.py --json results/mutants.json
```

## Синтетика и подлинные данные

Подлинные: город, bbox, release, ID и координаты записей (`web/data.js`), QA-флаги (`web/evidence.js`), sha256 файлов, `source_snapshot`.
SYNTHETIC: контрольные точки, веса, места кандидатов, стоимости (условные единицы, не тенге), бюджет, `max_selected`, радиус. Пакеты `synthetic-*` — геометрия на экваторе, не данные городов.
