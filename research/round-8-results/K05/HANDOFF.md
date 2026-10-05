# HANDOFF — K05 round 8 (plan.js, city-plan-v2)

Для сборщика (BUILD) и следующего агента.
1. Модуль: `research/round-8-results/K05/plan.js` (UMD, без зависимостей). Скопировать в `prototypes/city-evidence/web/plan.js`, подключить после `data.js`, `facts.js`, `whatif.js`.
2. Контекст: `CITY_PLAN.contextFromCityData(city, CITY_EVIDENCE.cities[city], CITY_WHATIF.sourceSnapshot(CITY_EVIDENCE, city, CITY_FACTS))`.
3. Поиск без блокировки интерфейса: `optimizePlansAsync(ctx, scenario, {signal, request_id, onProgress})`. Применять ответ только если `isCurrent(result, problemDigest(текущий сценарий), текущий request_id)`. Результат — предложение; план меняется только после «Применить».
4. Показывать `status`. При `incomplete` не называть результат оптимумом: `objectives = null`, есть только `best_so_far`. `same_plan_as` — чтобы одинаковые планы не выглядели тремя разными решениями.
5. Проверка после интеграции (обязательно на новом SHA):
   `node research/round-8-results/K05/tests/test_stage{1,2,3}.cjs --app-root <SHA>/prototypes/city-evidence`,
   `node research/round-8-results/K05/tests/dump_cases.cjs --app-root … --out /tmp/c.json && python3 research/round-8-results/K05/oracle/oracle.py --cases /tmp/c.json`.
   Тесты читают `web/data.js` и `web/whatif.js` сборки. Если меняется формат `places` или `sourceSnapshot`, нужно поправить `tests/helpers.cjs`.
6. Не обещать в интерфейсе: время пути, население, вместимость, реальные цены, «лучший план города».
Подробности — README.md, состояние — STATUS.md.
