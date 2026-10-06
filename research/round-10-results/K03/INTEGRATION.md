# K03 r10 → BUILD (K04): как подключить пешеходные расстояния

Проверено на **копии** `d2ff344` (`runs/site_copy_check.json`). Общий сайт K03 не менял. Сюда не входят решения UI, compareCase и цифры для Score.

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
