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
Демо: `python3 -m engine.civic_scenarios.devserver` → `http://127.0.0.1:8517/civic/scenarios/demo.html`
(`?basemap=none` — без внешней подложки).
