# K03 round 10 — «Пешеходные маршруты вместо неподписанной прямой»: STATUS

| Поле | Значение |
|---|---|
| Слот | K03 (`research/round-10/prompts/K03.txt`, пакет `origin/codex/govtech-main-interface` @ `7c6fb75ec66c50627af62b9d0d8e94c1f09bee16`) |
| Ветка | `claude/epic-curie-iitc43` (вход r10: `4b5d00c`) |
| Кодовая база | `d2ff344c5ec9b9a729ea59df50ec81f981e619de` (`web/govtech/core/data.js` = blob донора) |
| Донор входов сети | `d18847f9e7c18fcfae3349c0b223b023d359a838:prototypes/city-evidence/inputs/k10/data/` |
| Обновлено | 2026-10-06, этап 1 |
| Статус | этап 1 (аудит покрытия) **done**; этапы 2–3 — в работе |

## Этап 1 — аудит сети (done)

`python3 research/round-10-results/K03/audit_network.py` → `audit/<city>.json`, `audit/summary.json`, `inputs/INPUT_MANIFEST.json`. Выводы — `COVERAGE.md`.

- `data.js` для графа **недостаточно**: у сегмента нет ID и позиций соединителей.
- Сырой K10-пакет достаточен для графа по реальным узлам OSM. Его sha256 совпадает с `data.js.files`.
- Геометрия проверена на всех строках обоих городов: каждый соединитель лежит на вершине своей линии, порядок монотонный, концы на `at = 0` и `1`.
- 13 пересечений без общего соединителя (мосты, тоннели и 2 случая без флагов) — не узлы.
- Подтверждённого пешеходного доступа мало. Подробности — `COVERAGE.md`.
- Буфер в данных 0 м; новая выгрузка — NOT_FETCHED.

Окружение: Linux, Python 3.11.15, shapely 2.1.2 (только аудит), node v22.22.0.
