# Интеграция K05 → BUILD (K04): сравнение школьного кейса

Проверено на копиях: d2ff344c5ec9b9a729ea59df50ec81f981e619de и BUILD r10 0b2910ecd4c182c5036437670fbb393f513e0f35
(plan.js в обоих одинаков; patch ложится без смещений). В сам сайт 8501 не встроено — интеграцию делает BUILD.

## Шаги
1. `patch -p1 < research/round-10-results/K05/patch/plan_matrix.patch` (из корня): `web/govtech/core/plan.js`
   получает `precomputeFromMatrix` + пропуск неизвестного пути. Это изменение pinned core: по CONTRACT сохранить старый
   source hash в `SOURCE_MANIFEST.json`, записать новый integrated hash и ссылку на этот patch; `tests/test_govtech_integration.py`
   (2 разрешённые UI-адаптации) обновляет только BUILD с обоснованием.
2. Скопировать `module/school-compare.js` в `web/govtech/school-compare.js`; в браузере подключать после
   `core/facts.js`, `core/whatif.js`, `core/plan.js` (глобал `window.CITY_SCHOOL_COMPARE`). `ui/web_server.py` раздаёт
   только явно перечисленные файлы — добавить путь.
3. Вызов: `CITY_SCHOOL_COMPARE.compareCase(case, matrix)`; при ошибке `CompareError {code, detail}` — ничего не применять
   (атомарный отказ). Матрица geodesic может строиться в браузере так же, как в `cases/make_city_cases.cjs`
   (`whatif.haversine` + `plan.mmOf`); pedestrian-v1 — только готовой матрицей от K03 со статусами, без подстановки прямой.
4. UI «Сейчас / A / B»: слой берёт `plans[].rows` (`nearest_target_id`, `after_mm`, `delta_mm`, `status`); разница —
   `delta_mm < 0` ближе, `0` без изменений, `null` неизвестно. Показатели: `mean_distance_mm`, `max_distance_mm`,
   `within_threshold_count` / `total_origins`, `unknown_count`. Предложение — `auto:contract-lex`; `auto:minimax`
   подписывать как другую цель. Тексты/AI берут только `facts` (id, value, unit, source_ids, assumptions).
5. Тесты в CI сборки: `python3 research/round-10-results/K05/run_tests.py --app-root .` (не меняет дерево; копирует во
   временный каталог) — после интеграции можно перенести `tests/test_school_compare.cjs` в `tests/govtech/`.

## Решения K05, которые BUILD/координатор могут пересмотреть
- `access_eligibility=unknown` → школа считается целью, строка помечается; `known_restricted` → не цель (`ELIGIBILITY_POLICY`).
- `selected_candidate_ids` трактуется как список отдельно сравниваемых вариантов (A, B), каждый — набор из одного места.
- Порог в целых мм: `round(threshold_m * 1000)`; доля — от всех точек.
- Строка `partial`: путь известен, но хотя бы до одной используемой цели статус ≠ ok (минимум может быть неполным).
- Буфер школ за краем участка в кейсах K05 отсутствует (данных нет) — это видно в `model_assumptions`.
- Стоимость: null у любого кандидата → `no_cost_data`; однородные единицы → справочная сумма; бюджетной оптимизации в
  основном кейсе нет. Подтверждённые данные K11 подаются как `{value, currency, period, kind, source_ids}`.
