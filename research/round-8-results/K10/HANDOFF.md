# K10, раунд 8: пакеты сценариев city-plan-v2 — передача

**Состояние:** этап 1 из 3 (см. `STATUS.md`). Следующий шаг: этап 2 — `python3 -m k10plan.packs ... --max-stage 2`.

## Что есть

- `k10plan/oracle.py` — независимый Python-оракул по `CORE_SPEC.txt` (stdlib): строгий JSON, валидация, `evaluate_plan`, точный перебор, три цели, Парето, чувствительность к бюджету.
- `k10plan/slice.py` — чтение реального среза из app root сборки (только чтение). `source_snapshot` совпадает с `web/whatif.js sourceSnapshot()` сборки a5b5e2d (проверено node).
- `k10plan/packs.py` — генератор пакетов по правилам `RULES`, заданным до расчёта.
- `packs/*.json` — пакеты; `packs/scenarios/*.json` — только вход `city-plan-v2` для импорта; `packs/INDEX.json` — список, sha256, правила.
- `tests/check_packs.py`, `tests/xcheck_build.cjs` — проверка.

## Команды

```bash
python3 research/round-5-results/K10/tools/extract_build.py --sha a5b5e2ddbe087c4eab8e947748cdf69dbae84a0d --out /tmp/b   # из корня репозитория
cd research/round-8-results/K10
python3 -m k10plan.packs --app-root /tmp/b/prototypes/city-evidence --commit a5b5e2ddbe087c4eab8e947748cdf69dbae84a0d --out packs --max-stage 1
python3 tests/check_packs.py --app-root /tmp/b/prototypes/city-evidence --json results/check_packs_stage1.json
```

## Синтетика и подлинные данные

Подлинные: город, bbox, release, ID и координаты записей (`web/data.js`), QA-флаги (`web/evidence.js`), sha256 файлов, `source_snapshot`.
SYNTHETIC: контрольные точки, веса, места кандидатов, стоимости (условные единицы, не тенге), бюджет, `max_selected`, радиус.
