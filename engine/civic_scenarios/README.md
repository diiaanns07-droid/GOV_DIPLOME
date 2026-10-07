# engine/civic_scenarios — симулятор последствий перекрытий (R07, civic-scenario-v1)

Сравнивает на **одном фиксированном графе** базовое состояние и два плана перекрытий (A/B)
в заданный момент. Показывает, какие пути изменились и на сколько метров, и где данных недостаточно.
Только стандартная библиотека Python 3.10+.

```python
from engine.civic_scenarios import compare, timeline
from engine.civic_scenarios.registry import load_graph
result = compare(payload, load_graph(payload["graph_id"]))
```

## Единицы и метрика
- Длина — **метры** по графу; внутри считается в **целых миллиметрах** (`round half up` от `length_m`),
  наружу `length_m = mm / 1000`. Это **не время в пути**.
- `delta_m` = длина в плане − длина в базе (только если обе `ok`).
- Stretch `timeline`: `extra_length_m_h` — интеграл добавочной длины по времени, **м·ч**;
  `pair_hours_lost_within_model` — **пара·ч**. Метры и часы не складываются в общий балл.
- Нет модели пробок, светофоров, поворотов, CO2, аварийности, экономического эффекта.

## Семантика
| Что | Правило |
|---|---|
| Доступ (strict) | `ok`-маршрут только по `access=allowed`; `unknown` не считается разрешённым; `denied` не используется никогда |
| `oneway=true` | движение только `from → to` |
| Перекрытие | блокирует ребро в обоих направлениях на `[start_at, end_at)` |
| Время | ISO 8601 **с явным смещением**; сравнение по абсолютному моменту (UTC). `12:00+05:00` = `07:00Z` |
| Пустой/обратный интервал | ошибка `invalid_payload` (не «никогда не активно») |
| Неизвестные edge/node | `unknown_edge` / `unknown_node` (422) |
| Иной город / режим / граф | `city_mismatch` / `mode_mismatch` / `graph_mismatch` (422); устаревший digest — 409 |
| Лишние ключи payload | отклоняются: клиент не передаёт метрики, пути к файлам, URL |
| Лимиты | ≤25 стартов, ≤100 целей, ≤1000 пар, ≤100 перекрытий и ≤2000 edge_ids на план |

Статусы пары:
- `ok` — путь найден, `length_m`, `edge_ids`, `node_ids`, `equal_cost_alternatives`;
- `unknown` — `path_only_via_unknown_access` (есть путь только через рёбра с неизвестным доступом;
  `length_if_unknown_allowed_m` — справочно) или `path_may_exist_outside_graph` (граф — срез,
  обе стороны достигают граничных узлов `boundary`);
- `unreachable` — `no_path_within_model`: пути нет **внутри модели**, это не доказанная недоступность.

Отсутствие пути никогда не равно 0 и не подменяется прямой. Средние/максимумы — только по парам `ok/ok`
(`comparable_pairs`). Изменения: `unchanged | longer | shorter | lost_within_model | became_uncertain | gained | not_comparable`.

**Равные пути.** Дейкстра с кучей `(мм, ID узла)`, смежность по ID ребра, предшественник меняется только при
строгом улучшении → выбор детерминирован; `equal_cost_alternatives=true` сообщает, что есть другой путь той же
длины. Тесты проверяют стоимость, а не конкретную ветку. (При рёбрах нулевой длины признак может недосчитать.)

**Воспроизводимость.** В результате: `payload_digest` (сырые байты входа), `scenario_digest`
(канонический сценарий: порядок перекрытий/edge_ids и запись смещения не влияют), `graph_digest`,
`result_digest`. Канонический JSON: `json.dumps(sort_keys=True, separators=(",",":"), ensure_ascii=False, allow_nan=False)`.

## Графы (`graphs/MANIFEST.json`)
| graph_id | Режим | Статус | Размер | Что это |
|---|---|---|---|---|
| `synthetic-tiny-v1` | walking | synthetic | 10/11 | эталон с ручными ожиданиями, не реальные улицы |
| `k03-astana-pedestrian-r10` | walking | derived | 2309/3269 | пешеходный граф K03 центра Астаны (~2×2 км), Overture/OSM, ODbL |

Адаптер K03 (`adapters/k03.py`) проверяет sha256 исходного файла и пересчитывает его `graph_sha256`.
Отображение доступа: `s=[ok,ok]→allowed`; `s=[unk,unk]→unknown`; `s=[unk,no],x=[ok,ok]→unknown`
(автомобильный oneway OSM не доказывает запрет для пешехода); `s=[no,no]→denied`; иное → `AdapterNotReady`.
`n.open → boundary`. Пересборка: `python3 -m engine.civic_scenarios.build_graphs [--check]`.

**driving — NOT_READY**: нет motor_vehicle-доступа по направлениям, отдельного автомобильного oneway,
запретов поворотов и покрытия города. Пешеходный граф не переименовывается в driving.

## HTTP (для R01) и демо
`http.handle(method, path, query, body)` — `/api/civic/v1/scenarios/{graphs,graphs/{id},cases,compare}`.
Интерфейс — в приложении (`app.py`, кнопка «Сравнить ограничения»); отдельного demo/devserver больше нет.

## Раунд 13: путь пользователя без node ID и объяснение своего расчёта (engine 1.1.0)

**Привязка места к сети** (`snap.py`, повтор в `web/civic/scenarios/scenarios.js` — паритет проверяется тестом
в Node). Кандидаты — только узлы на рёбрах `access=allowed`; ближайший по гаверсинусу, ничья по ID узла;
порог `SNAP_MAX_M = 150` м — дальше отказ `too_far` (точка не переносится); вне bbox — `outside_graph`.
Возвращаются исходная точка, узел, расстояние (подход к сети в длину пути не входит и не проверен как путь),
`nearer_unverified_m` (ближе есть линия с неизвестным доступом — не используется), размер компоненты и
`main_component`; для узла во фрагменте — `main_alternative` (узел основной сети в пределах порога) только как
явный выбор пользователя. Мосты/уровни: связность только через общие узлы OSM, поэтому экранное пересечение
линий не соединяет их; в UI при наложении линий участок выбирается из списка.

**Новые поля результата** (обратно совместимы): `plans[].closed_on_baseline_routes`, предупреждение
`closure_not_on_baseline_routes`; `a_vs_b.identical_active_closures` и `plans_identical_at_analysis_at`.

**Кэш объяснений R09.** `http.handle(..., on_result=cb)` вызывает `cb(payload, result)` только после
успешного compare (ошибка колбэка не ломает ответ); равнозначно — патч R09 для шлюза R01 вызывает
`ScenarioResultCache.remember` после ответа 200. Браузер передаёт помощнику только
`scenario_id = "result:" + result_digest`, цифр не передаёт.

**Производительность** (`python -m engine.civic_scenarios.bench`): смежность без перекрытий строится один раз
на граф (≤3 варианта), перекрытия пропускаются в Дейкстре, поиск останавливается после всех целей;
результаты побайтно совпадают с прежней реализацией. Справочные числа — в research/round-13-results/R07/bench_r13.json.

**Пример для проверки** — `python -m engine.civic_scenarios.example --check` (Байтерек → Хан Шатыр, ожидания в
`cases/astana-baiterek-khanshatyr-v1.case.json`).
