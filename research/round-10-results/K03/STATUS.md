# K03 round 10 — «Пешеходные маршруты вместо неподписанной прямой»: STATUS

| Поле | Значение |
|---|---|
| Слот | K03 (`research/round-10/prompts/K03.txt`, пакет `origin/codex/govtech-main-interface` @ `7c6fb75ec66c50627af62b9d0d8e94c1f09bee16`) |
| Ветка | `claude/epic-curie-iitc43` (вход r10: `4b5d00c`) |
| Кодовая база | `d2ff344c5ec9b9a729ea59df50ec81f981e619de` (`web/govtech/core/data.js` = blob донора) |
| Донор входов сети | `d18847f9e7c18fcfae3349c0b223b023d359a838:prototypes/city-evidence/inputs/k10/data/` (Overture `2026-09-23.1`, OSM ODbL) |
| Обновлено | 2026-10-06, этапы 1–4 |
| Новый BUILD, проверенный явно | `c0b276e8a2d8d97a369252470f60e97bf1858f1d` (r10 stage 1, `school/case.js`) — только на копии с патчем K03 |
| Статус | **все этапы done** (модуль, граф, fixtures, adapter, проверки, патч к BUILD c0b276e). В общий сайт **не интегрировано** — это работа BUILD; патчи проверены только на копиях d2ff344 и c0b276e |

Обзор и выводы — `README.md`; подключение — `INTEGRATION.md`; данные — `COVERAGE.md`.

## Этап 1 — хватает ли сети (done)

`audit_network.py` → `audit/*.json`, `inputs/INPUT_MANIFEST.json`.

- `data.js` для графа недостаточно: нет ID соединителей. Сырой K10-пакет достаточен; его sha256 совпадает с `data.js.files`.
- На всех строках обоих городов соединители лежат на вершинах.
- 13 пересечений без соединителя — не узлы.
- Пешеходных классов: Шымкент 28,8 из 125,5 км, Астана 45,9 из 156,2 км.
- Буфер 0 м; новая выгрузка — NOT_FETCHED.

## Этап 2 — политика и граф (done)

- `policy/pedestrian-v1.json`: strict / exploratory, привязка 100 м, статусы, правило края.
- `build_graph.py` → `graph/<city>.graph.json`:
  - Шымкент: `graph_sha256 b4a59a4c…`, 1729 узлов, 2260 рёбер;
  - Астана: `799d26e5…`, 2309 узлов, 3269 рёбер;
  - `policy_sha256 ba8a525a…`;
  - лицензия ODbL с атрибуцией.
- `--check` пересобирает графы и сверяет с файлами: совпадают.

## Этап 3 — модуль, fixtures, adapter (done)

| Файл | Что |
|---|---|
| `routing.js` | модуль UMD (`K03_ROUTING`): `prepare` (проверка `graph_sha256`), `route`, `geodesic`, `matrix` |
| `routing_ref.py` | независимый Python-оракул |
| `school-access-routing.js` | адаптер CONTRACT (`K03_SCHOOL_ROUTING`): `distanceMatrix`, `routeLayers`, `explainRow`, `STATUS_RU`/`ASSUMPTION_RU` |
| `make_hand_graphs.py` → `fixtures/hand_graphs.json` | 17 ручных графов (synthetic), 22 запроса × 2 политики, ожидания по построению |
| `make_city_pairs.py` → `fixtures/city_pairs.json`, `city_pairs_summary.json` | 243 пары обоих городов: точки и кандидаты synthetic, школы observed_secondary |
| `adapter_demo.cjs` → `examples/<city>_case.json`, `examples/<city>_routes.geojson`, `runs/adapter_demo.json` | пример school-access-case-v1 и слоя маршрутов |
| `install_for_build.py`, `patches/build_d2ff344_k03_routing_assets.patch` | установка в дерево BUILD |

## Реально выполненные проверки

Окружение: Linux, Python 3.11.15, node v22.22.0, Chromium 141 (Playwright).

| Команда | Результат |
|---|---|
| `python3 run_tests.py` | **PASS 11, FAIL 0, INFO 1** (`runs/tests.json`) |
| `python3 negative_controls.py --work /tmp/x` | **6/6** испорченных копий `routing.js` пойманы (`runs/negative_controls.json`) |
| `node bench.cjs 5` | замер этого окружения (`runs/bench.json`) |
| `node browser_check.cjs` | **12/12** (`runs/browser_check.json`) |
| `node site_copy_check.cjs` (копия d2ff344 + патч K03, сервер `app.py` на 8599/8598) | **7/7** (`runs/site_copy_check.json`) |
| `build_graph.py --check` | графы совпадают с файлами |

Что проверяет `run_tests.py`:
- 17 ручных графов, JS и Python: статус, причина, мм, рёбра, допущения;
- правила графа: запрет на части сегмента, мост без узла;
- 729 строк городов = ожиданиям;
- полное совпадение JS и Python (773 строки);
- геометрия и длина, направления, инварианты;
- детерминизм при перестановке входов;
- hash: подмена ребра отклоняется.

Отрицательный контроль ловит такие поломки:
- игнор направления;
- тихая прямая вместо отсутствующего пути;
- нет допуска привязки;
- strict использует неизвестный доступ;
- нет проверки края;
- `access_unknown` выдаётся как `disconnected`.

Замер `bench.cjs` — 25 × (школы + 16) пар:
- strict — 120 мс (Шымкент) / 354 мс (Астана);
- exploratory — 491 / 619 мс;
- самый долгий маршрут — ≤ 24 мс.

Что проверяет `browser_check.cjs`: модуль в Chromium, `graph_sha256` проверяется `CITY_FACTS.sha256hex` базы, подмена отклоняется, строки равны Node.

Что проверяет `site_copy_check.cjs`:
- модули на главной странице;
- матрица в странице = Node;
- новых ошибок и внешних запросов нет;
- файлы `k03/` отдаются с правильным MIME и sha256;
- тест K03 и `test_integrated_govtech_assets_match_provenance` проходят (вызов функций напрямую; pytest не установлен).

**NOT_RUN / не проверено:**
- подложка и 3D: OpenFreeMap заблокирован в этой среде (`ERR_TUNNEL_CONNECTION_FAILED`, одинаково без патча и с ним);
- интегрированный общий сайт: BUILD ещё не интегрировал;
- Windows;
- проверка людьми;
- проверка маршрутов на месте.

## Этап 4 — подключение к BUILD `c0b276e` (проверено на копии)

После этапа 3 BUILD опубликовал `c0b276e` (`web/govtech/school/case.js`: кейс, прямая, `compareCase`). В нём pedestrian-v1 явно отключён.

- `make_build_patch.py` → `patches/build_c0b276e_k03_pedestrian.patch`, тесты — `build_tests/`. Что меняет патч — `INTEGRATION.md`, раздел 0.
- Результаты на копии `c0b276e` с патчем и установкой:

| Проверка | Без патча | С патчем |
|---|---|---|
| `school_case.cjs` | 2311 | 2312 |
| `school_pedestrian.cjs` (новый) | — | 622 |
| `plan`/`resilience`/`whatif` | PASS | PASS |
| `ui.web_check` | OK | OK |
| Провенанс | OK | OK |
| Chromium | — | 9/9 (`runs/site_copy_check_c0b276e.json`) |

- На настоящем кейсе BUILD strict оставляет без известного пути 16 из 25 точек в Шымкенте и 7 из 25 в Астане. Автовыбор места зависит от политики.
- Честно о ходе работы: первый прогон `ui.web_check` упал одинаково на обеих копиях, потому что я распаковал дерево без `agent/`. С `agent/` и в окружении без ключей (`env -i`) — OK. Живой AI не вызывался.

## Находки по ходу (честно)

1. **Инвариант «exploratory не длиннее strict» неверен для правила привязки «ближайшее ребро политики»: 26 из 98 пар.** Первый прогон дал FAIL. Это следствие правила, а не Дейкстры. Требование теперь — равенство рёбер привязки; отличие показано как INFO, и в документации сказано: не смешивать политики.
2. **Валидатор `run_tests.py` падал на испорченном результате.** Мутант `silent-geodesic` выдавал строку без частей, и валидатор не справлялся. Исправлено: неправильная форма = FAIL.
3. **Точка ровно в узле односторонного ребра теряла узел** (кусок 0 мм «запрещён» в обратную сторону). Правило: кусок нулевой длины от направления не зависит и в рёбра маршрута не входит. Покрыто ручным графом `h3-oneway-foot`.
4. **Проверка края была O(B²) на каждый маршрут.** Пересчитана через f(b′) на точку. Решение то же, ответы не изменились, exploratory быстрее примерно в 2,5 раза.

## Что осталось

- BUILD:
  - установить файлы и патч для `c0b276e` (`INTEGRATION.md`, раздел 0);
  - UI: переключатель «По прямой / По проверенным пешеходным рёбрам / По неполным данным», слой маршрутов, карточка;
  - compareCase в одной политике;
  - `case_digest` с `graph_sha256`/`policy_sha256`;
  - перепроверить на точном новом SHA.
- Данные: выгрузка Overture с буфером ≈ T·1,3 вокруг квадрата (NOT_FETCHED), проверка пешеходного доступа на месте.
