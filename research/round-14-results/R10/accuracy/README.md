# R10 · точность карты (CONTRACT §8) по веткам ролей, 10 окт (до B1)

Команда: `python3 tests/civic/R10/accuracy.py --root <worktree ветки> --json <роль>.json`. Эталон — граф OSM `osm-astana-walking-20260506`, граница — полигоны районов `data/civic/astana/geofence.json`. NOT_RUN (набора нет в ветке) в таблицу не включены — см. JSON.

| Ветка | Проверка | Итог |
|---|---|---|
| claude/r14-R05 @ e533e67 | граница Астаны · R05 proposals.fixture.json | **PASS** |
| claude/r14-R05 @ e533e67 | граница Астаны · R05 nura-streets.json | **PASS** |
| claude/r14-R05 @ e533e67 | граница Астаны · R05 astana-existing.json | **FAIL** |
| claude/r14-R05 @ e533e67 | улицы Нуры R05 = рёбра OSM | **PASS** |
| claude/r14-R05 @ e533e67 | линии R05 proposals.fixture на улице | **PASS** |
| claude/r14-R05 @ e533e67 | остановки — не ж/д платформы · R05 | **FAIL** |
| claude/r14-R05 @ e533e67 | остановки ≤ 60 м от улицы · R05 | **FAIL** |
| claude/r14-R05 @ e533e67 | объекты R05 = точки OSM | **PASS** |
| claude/round-14-r06 @ 3d10f7d | граница Астаны · R06 demo_r14.py | **PASS** |
| claude/round-14-r06 @ 3d10f7d | линии R06 demo_r14 на улице | **PASS** |
| claude/upbeat-knuth-i0rqaa @ 3eb3f9d | граница Астаны · R07 targets_demo.json | **PASS** |
| claude/upbeat-knuth-i0rqaa @ 3eb3f9d | участки = рёбра OSM · R07 targets | **PASS** |
| claude/upbeat-knuth-i0rqaa @ 3eb3f9d | остановки — не ж/д платформы · R07 | **PASS** |
| claude/upbeat-knuth-i0rqaa @ 3eb3f9d | остановки ≤ 60 м от улицы · R07 | **PASS** |
| claude/upbeat-knuth-i0rqaa @ 3eb3f9d | объекты R07 = точки OSM | **PASS** |
| claude/upbeat-knuth-i0rqaa @ 3eb3f9d | id целей R07 по контракту §4 | **PASS** |
| claude/tender-brahmagupta-ef5ztl @ 8bb7bf8 | граница Астаны · R12 geo/objects.json | **PASS** |
| claude/tender-brahmagupta-ef5ztl @ 8bb7bf8 | граница Астаны · R12 geo/yards.json | **FAIL** |
| claude/tender-brahmagupta-ef5ztl @ 8bb7bf8 | граница Астаны · R12 geo/demo_snapped.json | **PASS** |
| claude/tender-brahmagupta-ef5ztl @ 8bb7bf8 | граница Астаны · R12 map/demo_snapped.json | **PASS** |
| claude/tender-brahmagupta-ef5ztl @ 8bb7bf8 | нет линий «от руки» · R12 geo/demo_snapped.json | **PASS** |
| claude/tender-brahmagupta-ef5ztl @ 8bb7bf8 | нет линий «от руки» · R12 map/demo_snapped.json | **PASS** |
| claude/tender-brahmagupta-ef5ztl @ 8bb7bf8 | остановки — не ж/д платформы · R12 | **PASS** |
| claude/tender-brahmagupta-ef5ztl @ 8bb7bf8 | остановки ≤ 60 м от улицы · R12 | **PASS** |
| claude/tender-brahmagupta-ef5ztl @ 8bb7bf8 | объекты R12 = точки OSM | **PASS** |
| claude/r14-R13 @ 754de0c | граница Астаны · R13 forecast targets.json | **PASS** |
| claude/r14-R13 @ 754de0c | остановки — не ж/д платформы · R13 | **PASS** |
| claude/r14-R13 @ 754de0c | остановки ≤ 60 м от улицы · R13 | **PASS** |
| claude/sharp-dijkstra-0t87gl @ bc7c961 | граница Астаны · R07 targets_demo.json | **PASS** |
| claude/sharp-dijkstra-0t87gl @ bc7c961 | участки = рёбра OSM · R07 targets | **PASS** |
| claude/sharp-dijkstra-0t87gl @ bc7c961 | остановки — не ж/д платформы · R07 | **PASS** |
| claude/sharp-dijkstra-0t87gl @ bc7c961 | остановки ≤ 60 м от улицы · R07 | **PASS** |
| claude/sharp-dijkstra-0t87gl @ bc7c961 | объекты R07 = точки OSM | **PASS** |
| claude/sharp-dijkstra-0t87gl @ bc7c961 | id целей R07 по контракту §4 | **PASS** |

Дефекты: B-007…B-010 в `../BUGS.md`.
