# Городские данные: Шымкент / Астана (демо BUILD, раунд 4)

Демо открытых вторичных данных (Overture Maps 2026-09-23.1) для двух небольших квадратов ~2×2 км — по одному в Шымкенте и Астане. Не целые города, не официальный реестр, не учебная модель STUPITS. Основной сайт (корневые `web/`, `agent/`, `engine/`, `data/`, `run.bat`) не меняется.

## Запуск с чистого checkout

Нужен только Python 3 (стандартная библиотека). Сеть, API-ключ и сборка не нужны: `web/data.js` и `web/evidence.js` закоммичены.

```bash
cd prototypes/city-evidence
python3 serve.py            # → http://127.0.0.1:8765/
# или открыть web/index.html в браузере (file:// тоже работает)
```

## Что на экране

- переключатель Шымкент / Астана; при смене сбрасываются выбранный объект, точка, подсказка, отложенное объяснение;
- слои «Объекты» и «Дороги», фильтр 7 категорий, раскраска дорог по данным о проходе пешком (с легендой);
- карточка объекта: источник, лицензия, дата, confidence, **район по правилу K03** (ru / kk) или «не присвоен» с кандидатами; «мощность — нет данных»;
- карточка дороги (класс, длина, проход пешком, мост/тоннель, источник OSM); расстояние от точки только **по прямой**;
- таблица записей среза; раскрываемая карточка источников (SHA256, K03, K05, K08);
- «Объяснение по фактам»: каталог фактов текущего города/фильтра/среза и кнопка «Объяснить срез» —
  **шаблонное объяснение** (детерминированная заглушка, не LLM), текст собирается кодом из ID фактов по правилам K02.

## Откуда что

| Часть | Вход (ветка @ SHA, см. `source_manifest.json`) | Как использовано |
|---|---|---|
| Viewer | K07 `save-work-handoff-ku3ej3` @ 6778ded | `web/app.js`, `web/index.html` — перенесены и адаптированы |
| Данные | K10 `save-work-handoff-j7pc05` @ ea703f1 (данные 602f0c0) | `inputs/k10/` побайтно; `tools/build_data.py` → `web/data.js` (проверка SHA256 по манифесту) |
| Районы | K03 `epic-curie-iitc43` @ 44585de | `assign()` (k03_assign_v1) без изменений из `inputs/k03_root/`; результат в `web/evidence.js` |
| Unknown ≠ 0 | K05 `optimistic-davinci-1oiqs9` @ d913554 | наблюдения k05-obs-v1.1, `validate()`; ошибка → сборка останавливается |
| Объяснение | K02 `clever-mccarthy-pywscu` @ 24c1750 | `web/facts.js` — порт `validate_plan`/`render`; равенство текста с Python-оригиналом проверяется |
| Ограничения | K08 @ e1e3c71, K04 @ 7fb8bb8 | районные суммы E02/E03 не переносятся (двойной счёт границ) |

## Пересборка (не нужна для запуска)

```bash
cd prototypes/city-evidence
python3 tools/copy_inputs.py                  # из корня репозитория нужен git fetch веток из source_manifest.json
python3 inputs/k10/scripts/offline_check.py   # пакет K10: "ok": true
python3 tools/build_data.py                   # → web/data.js
pip install -r requirements-build.txt         # shapely, pyproj — только для K03
python3 tools/build_evidence.py               # → web/evidence.js (K03 assign + K05 validate)
python3 tools/explain_ref.py                  # → tests/expected_explanations.json (K02 Python)
```

## Тесты

```bash
python3 -m unittest discover -s tests -v                   # входы: битый/отсутствующий файл, манифест; K05 ZERO_ON_PARTIAL; K03 (если есть shapely)
node tests/conformance.cjs                                 # JS = K02 Python (6 случаев); unknown ID, чужой город, устаревший срез, null vs 0
NODE_PATH=$(npm root -g) node tests/smoke.cjs              # Playwright Chromium, file://; скриншоты → research/round-4-results/BUILD/smoke/
```

Проверено только на Linux (контейнер Claude Code: Python 3.11, Node 22, Playwright 1.56 Chromium). Windows/macOS не проверялись.

## Ограничения

- Число строк = число записей Overture в квадрате, не число объектов города, не мощность и не обеспеченность. Пустая категория → «нет данных» (`missing / zero_in_partial_coverage`), не 0.
- У большинства сегментов права прохода пешком неизвестны: время пешком, изохроны и «недостижимо» не показываются; маршрутного режима нет.
- Районы — OSM/Overture через K03, юридически не проверены. В этих двух квадратах все записи получили `matched`; `ambiguous/unmatched` проверены тестами K03, на реальных записях не встретились.
- Объяснение — шаблон по правилам K02 (лимит 6 фактов в секции: в «Итог» входят первые 5 категорий, остальные — в каталоге). LLM не подключён. Казахские подписи — черновик для проверки носителем.
