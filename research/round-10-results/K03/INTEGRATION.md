# K03 r10 → BUILD (K04): как подключить пешеходные расстояния

**Актуально для BUILD `c0b276e`** (r10 stage 1: `web/govtech/school/case.js`). Используйте раздел 0. Разделы 1–5 описывают тот же модуль для базы `d2ff344`, а также тексты и атрибуцию.

Общий сайт K03 не менял: всё проверено на **копиях** дерева.

## 0. BUILD `c0b276e`: школьный кейс + pedestrian-v1 (проверено на копии)

```bash
python3 research/round-10-results/K03/install_for_build.py --target .
git apply research/round-10-results/K03/patches/build_c0b276e_k03_pedestrian.patch
```

Патч (248 строк) собирается скриптом `make_build_patch.py` из распакованного `c0b276e`.

**`ui/web_server.py`, `web/index.html`** — файлы `k03/` в белом списке; `<script>` K03 перед `school/case.js`.

**`web/govtech/school/case.js`:**
- `distance_method: "pedestrian-v1"` допускается только с `routing_policy_id` (`pedestrian-v1-strict` | `pedestrian-v1-exploratory`) и `routing_snapshot {graph_sha256, policy_sha256, max_snap_m}`. Отпечаток лежит в `parameters`, поэтому входит в `case_digest`. Прямая остаётся как была.
- `checkMatrix`: матрица другого графа или политики → `matrix_snapshot`.
- Допущения фактов и `limitations` зависят от метода:
  - прямая → `straight_line_not_route`;
  - strict → `pedestrian_route_osm_not_field_checked`;
  - exploratory → `pedestrian_route_incomplete_data`;
  - для маршрута ещё `routing_slice_boundary_unverified`, `snap_model_connection`.
- Строка плана получает `unknown_targets` — число школ/мест без известного пути. Если такие есть, добавляется `targets_with_unknown_distance`. Минимум считается только по известным; неполнота видна.

**`tests/govtech/school_case.cjs`.** Одна устаревшая проверка «pedestrian не подключён» (код `method`) заменена: pedestrian без политики → `policy`, неизвестный метод → `method`. Это намеренное изменение поведения, решение за BUILD.

**Новые тесты:**
- `tests/govtech/school_pedestrian.cjs` — 622 проверки. `compareCase` сборки на матрице K03 сверяется с независимым перебором по строкам матрицы. Также проверяются: автовыбор, digest зависит от графа и политики, отказ при несовпадении, допущения — не «прямая».
- `tests/test_k03_routing_assets.py` — хэши файлов.

**Проверено на копии** (`runs/build_c0b276e_tests.json`, `runs/site_copy_check_c0b276e.json`):

| Проверка | Без патча | С патчем |
|---|---|---|
| `school_case.cjs` | 2311 | 2312 |
| `school_pedestrian.cjs` | — | 622 |
| `plan.cjs`, `resilience.cjs`, `whatif.cjs` | PASS | PASS |
| `ui.web_check` (`env -i`, без ключей) | OK | OK |
| Python-тесты провенанса | OK | OK |
| Chromium, главная страница | — | 9/9: модули загружены; `compareCase` сборки с pedestrian-v1 в странице = Node (digest, Сейчас/A/B/авто, метрики, ограничения); новых ошибок и внешних запросов нет |

**Не сделано — работа BUILD/K07:**
- переключатель метода в `school-ui.js` («По прямой / По проверенным пешеходным рёбрам / По неполным данным»);
- слой маршрутов (`routeLayers`) и подписи;
- `model_assumptions` кейса для маршрута: сейчас в `buildCase` текст про прямую — для pedestrian его нужно заменить.

**Что видно на настоящем кейсе BUILD** (25 точек сетки, школы по правилу BUILD, 12 мест; `runs/build_c0b276e_tests.json`):

| | Точек без известного пути в «Сейчас» | Автовыбор места |
|---|---|---|
| Шымкент, strict | 16 из 25 | `m3a` |
| Шымкент, exploratory | 0 | `m3b` |
| Астана, strict | 7 из 25 | `m3c` |
| Астана, exploratory | 0 | `m1c` |

Метод меняет вывод, поэтому выбранный метод и его подпись должны быть видны рядом с результатом.

## 1. Файлы

Из корня рабочего дерева BUILD:

```bash
python3 research/round-10-results/K03/install_for_build.py --target .
git apply research/round-10-results/K03/patches/build_d2ff344_k03_routing_assets.patch
```

**`install_for_build.py`** создаёт `web/govtech/k03/`:
- `routing.js`, `school-access-routing.js`;
- `shymkent.graph.json`, `astana.graph.json`;
- `K03_MANIFEST.json` — sha256 каждого файла, `graph_sha256`, `policy_sha256`, ODbL, коммит-источник.

Пинованный `core/` и его `SOURCE_MANIFEST.json` не трогаются, поэтому `tests/test_govtech_integration.py` (2 адаптации UI) не меняется.

**Патч (44 строки):**
- `ui/web_server.py` — 5 файлов `k03/` в явном белом списке ASSETS, MIME по суффиксу;
- `web/index.html` — `<script defer>` для `k03/routing.js` и `k03/school-access-routing.js` после `core/resilience.js`;
- новый `tests/test_k03_routing_assets.py` — хэши `k03/` = `K03_MANIFEST.json`, лицензия ODbL.

**Проверено на копии:**
- патч применяется (`patch -p1`);
- сервер отдаёт все 5 файлов с правильным MIME и тем же sha256, неизвестный файл — 404;
- новый тест и `test_integrated_govtech_assets_match_provenance` проходят — вызваны напрямую: pytest в этой среде не установлен.

## 2. В коде режима «Доступность школ»

```js
const g = await (await fetch("/govtech/k03/" + city + ".graph.json")).json();
const G = K03_ROUTING.prepare(g, { sha256hex: CITY_FACTS.sha256hex }); // отклоняет подменённый граф (graph_hash_mismatch)
const m = K03_SCHOOL_ROUTING.distanceMatrix(caseObj, G);                 // caseObj = school-access-case-v1
// caseObj.parameters: distance_method "pedestrian-v1" + routing_policy_id "pedestrian-v1-strict" | "pedestrian-v1-exploratory",
// либо distance_method "geodesic" + routing_policy_id null
map.getSource("k03-routes").setData(K03_SCHOOL_ROUTING.routeLayers(m, { origin_id }));  // линии только из строк ok
```

### Слой MapLibre — один источник

- `part = "network"` — сплошная линия;
- `part = "snap"` — пунктир: «модельный отрезок до сети»;
- `part = "geodesic"` — тонкий пунктир: «прямая, не маршрут»;
- `incomplete = true` — другой цвет или подпись «по неполным данным».

### Карточка строки

`K03_SCHOOL_ROUTING.explainRow(row)` строит текст только из полей строки: статус, метры, метка, допущения.

### compareCase (BUILD/K05)

- Минимум считать только по строкам `ok` одной политики.
- `status ≠ ok` → unknown, **не 0**.
- Strict и exploratory не смешивать: из-за правила привязки exploratory может быть длиннее strict.
- Сравнение A/B — в одной политике.

### case_digest

Включить `graph_sha256`, `policy_sha256`, `routing_policy_id`, `distance_method`, `max_snap_m` из матрицы. Любое изменение — новый digest.

### Лимиты

25 точек и 16 кандидатов. Иначе `too_many_points` до вычислений.

### Время на этом окружении (Linux)

Exploratory 25 × 31 занимает до ~0,6 с и выполняется синхронно. В UI считать по одной точке за шаг (≤ 24 мс на маршрут) с уступкой event loop, как поиск в `plan-ui.js`.

## 3. Тексты, которые нельзя менять на более сильные

- strict: «маршрут по пешеходным рёбрам OSM/Overture (не проверено на месте)»;
- exploratory: «маршрут по неполным данным (не гарантированно доступный пешеходный путь)»;
- `disconnected`: «в модельной сети среза пути нет (не доказательство физической недоступности)»;
- `outside_coverage`: «путь вне среза не проверен».

## 4. Перепроверка после интеграции (на точном новом SHA)

```bash
python3 research/round-10-results/K03/run_tests.py --js <дерево>/web/govtech/k03/routing.js
NODE_PATH="$(npm root -g)" node research/round-10-results/K03/site_copy_check.cjs http://127.0.0.1:8501/ <url без K03> out.json
```

Если граф пересобран из других данных, сначала выполнить `build_graph.py`, затем `make_city_pairs.py`. Ожидания пересоздаются только из новых входов, не по ответу сайта.

## 5. Атрибуция

В подвал или в «Данные» добавить: «Пешеходный граф: © OpenStreetMap contributors (ODbL-1.0) через Overture Maps Foundation, выпуск 2026-09-23.1; производная база данных K03».

Юридическая проверка не проводилась.
