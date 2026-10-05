# STATUS — K08, раунд 8: экспорт отчёта и доказательства происхождения

**Статус:** этап 1 из 3 выполнен; этапы 2–3 в работе.

- Роль: K08, не BUILD. Ветка `claude/dazzling-mayer-drhsxk`. Задание `research/round-8/tasks/K08.txt`, спецификация `research/round-8/CORE_SPEC.txt` (codex/research-import-2026-10-05).
- База (только чтение): BUILD `claude/beautiful-clarke-sbzomj` @ `a5b5e2ddbe087c4eab8e947748cdf69dbae84a0d`, `prototypes/city-evidence/`. `git diff 4e93f30 a5b5e2d -- prototypes/city-evidence` пуст. В базе есть whatif v1, **city-plan-v2 в базе нет**. Интеграция отчёта не проверялась и не заявляется.

## Этап 1 — сделано
- `planlib.py` — Python-движок city-plan-v2 по CORE_SPEC:
  - strict JSON и валидация;
  - гаверсинус → мм (`haversine-mm-v1`);
  - evaluate, точный перебор ≤16 с тремя лексикографическими целями, Парето, чувствительность [0, B/2, B];
  - `problem_digest` и `scenario_digest`, независимые от порядка массивов;
  - provenance исходных записей и QA.
  Отпечаток `source_snapshot` повторяет формулу сборки (`web/whatif.js` + `facts.placesDigest`) со своей schema.
- `report.py` — генератор `report.json` (k08-plan-report/v1) и `report.html`:
  - в HTML: snapshot, bbox, release, пакет K10, sha256 файлов, digests, metric/formula, ввод (веса — приоритет, стоимости — условные единицы, радиус — параметр анализа), ручной план, исходные записи с источником/лицензией/QA, атрибуция, допущения, ограничения;
  - HTML без скриптов и внешних ресурсов, CSP `default-src 'none'`.
- `make_fixtures.py` и `fixtures/` — 3 сценария над реальными срезами a5b5e2d. Входы (места, стоимости, веса, бюджет) — synthetic demo, см. `fixtures/fixtures_manifest.json`.
- `reports/<fixture>/report.{json,html}` — сгенерированные отчёты.

## Реально выполненные проверки (этап 1)
`python3 test_report.py --app-root <a5b5e2d prototypes/city-evidence> -v` → **11 OK** (`runs_stage1.txt`):
- snapshot whatif-v1 в Python = `X.sourceSnapshot` JS сборки для обоих городов (через node);
- оптимум трёх целей = независимому перебору через `evaluate_plan` на двух фикстурах;
- infeasible с причиной;
- независимость от порядка массивов;
- мм-метрика, пустой план;
- Парето без доминируемых;
- бюджеты чувствительности;
- обязательные поля provenance в report.json;
- HTML без script/src/href/on*;
- нет запрещённых утверждений.

## Ограничения
- Ранжирующие ключи в переборе-проверке общие с движком (`P.KEYS`). Независим путь вычисления метрик, а не сами ключи.
- Схема snapshot для city-plan-v2 (`schema` = "city-plan-v2" в той же формуле) — предложение. BUILD может выбрать иначе, тогда нужна синхронизация.

## Следующий шаг
Этап 2: сравнение ручного плана и трёх стратегий в отчёте, таблица по точкам для каждого плана, свёртка одинаковых планов, бюджет как условность, Парето/чувствительность, источники/лицензии.
