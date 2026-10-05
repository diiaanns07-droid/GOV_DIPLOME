# HANDOFF — K08 R8: экспорт отчёта и доказательства происхождения

Состояние: этапы 1–3 выполнены в `research/round-8-results/K08/`. **В BUILD не интегрировано**: в `a5b5e2d` нет city-plan-v2.

## Входы
- BUILD `claude/beautiful-clarke-sbzomj` @ `a5b5e2ddbe087c4eab8e947748cdf69dbae84a0d` (= код 4e93f30 по `git diff`), `prototypes/city-evidence/`. Только чтение, через `git archive`.
- Спецификация: `research/round-8/CORE_SPEC.txt`, задание `research/round-8/tasks/K08.txt` @ codex/research-import-2026-10-05.

## Команды
```bash
mkdir -p /tmp/r8 && git archive a5b5e2ddbe087c4eab8e947748cdf69dbae84a0d prototypes/city-evidence | tar -x -C /tmp/r8
APP=/tmp/r8/prototypes/city-evidence; K=research/round-8-results/K08
python3 $K/make_fixtures.py --app-root $APP --out $K/fixtures
python3 $K/report.py --app-root $APP build $K/fixtures/shymkent_school_demo.json --out-dir /tmp/rep --generated-utc 2026-10-05T00:00:00Z
python3 $K/verify_report.py --app-root $APP /tmp/rep/report.json
python3 $K/test_report.py --app-root $APP -v          # 27 тестов
```

## Для интеграции сборщиком
- Отчёт (`report.py`) не зависит от JS: при интеграции JS-оптимизатора сравнивать его `optimizePlans` с `planlib.optimize_plans` на `fixtures/` (objectives, pareto, problem_digest) и строить отчёт из того же `plan_result`.
- Отпечаток city-plan-v2: предложено `schema="city-plan-v2"` в формуле `sourceSnapshot`. Если BUILD выберет иное, обновить `planlib.source_snapshot`, а не держать два варианта.
- Наблюдение: snapshot сборки (и мой, совместимый) покрывает id/координаты записей и sha256 файла мест из `data.js`, но **не** sources/лицензии в `data.js`. `verify_report` закрывает это сверкой с исходным GeoJSON пакета K10.

## Ограничения
- Python-оракул написан независимо от JS сборки (JS city-plan-v2 ещё нет). Проверка оптимума в тестах — второй путь через `evaluate_plan`; ключи ранжирования (`P.KEYS`) общие.
- Фикстуры: реальные записи Overture среза, но места кандидатов, стоимости, веса, бюджет и радиус — synthetic demo, не городская статистика и не цены.
- HTML проверен разбором (белый список тегов/атрибутов), в браузере не открывался.
