# BUILD раунд 6 — STATUS

- owner_branch: `claude/beautiful-clarke-sbzomj`; база: `064ed25368341edaa50289bc29e21dda7bdd9440`
- Задание: `research/round-6/BUILD.txt` @ `codex/research-import-2026-10-05` `edee718366ee4f085ea540c4e53a8dabf3c93fce`
- **Проверенный candidate (код): `b3e4dc413d5354652e3207d4eb56f921b108669e`**. Коммит с этим STATUS содержит только доказательства (`research/`), код не меняет.
- Статус: **candidate_ready_for_owner_demo** (не production-ready). Критических и высоких открытых находок нет; 1 FAIL низкой важности (K10 SHOULD), Windows не проверялся.

## Входы
87 файлов REVIEW раунда 5 → `review_inputs/` (MANIFEST.json). Применяемые сборкой патчи K05 и K03 r5 → `prototypes/city-evidence/inputs/r5/` (MANIFEST.json).

## Сделано
| Находка (тест) | Исправление в продукте |
|---|---|
| check_all падает на извлечённой папке (найдено на baseline) | побайтная копия `agent/evidence.py` → `inputs/product_agent`; эталон K02 больше не выходит за пределы папки |
| K12: NaN/Inf/1e999, повтор ключа, чужой bbox/выпуск/город, якорь | `build_data`/`build_evidence`: `INTEGRITY:` (хэши, якорь source_manifest, атрибуция, K05) и `SEMANTIC:` (строгий JSON, заголовок, id, диапазоны, bbox) до записи файлов |
| K05: BOUNDARY_MIX на раздельных bbox, expected_units, COUNT_DOMAIN для records | патчи K05 r5 поверх K12 → контракт `k05-obs-v1.2+k12r4+k05r5` (хэши = опубликованным K05) |
| K03: нет привязки к версии, устаревший район не виден; D3 пустые зоны | копия `k03v21_root` (патч v2.1) со сверкой MANIFEST_K03; `boundary_binding` k03-binding-v1; правило из кода; `tools/check_evidence_fresh.py`; шаг в check_all |
| K02 T7: наблюдения другого города принимались | `buildCatalog` отклоняет (`foreign_city`); SHA-256 без глобального TextEncoder |
| K07 R11/R12/R13 | статус внутри карты; карточки помещаются в 390 px; evidence.js другой версии → предупреждение, районы и каталог не используются |
| K10 SHOULD (выбор всех записей группы с карты) | список группы с `data-coord-group-item`, отметка группы |
| K08 A7 | карточка дороги называет фактический источник (OSM/TomTom) |
| K06 N6 | подпись длины: гаверсинус по сфере (не «геодезическая») |
| K11 S8 | вывод smoke по умолчанию в `tests/out/` внутри приложения |
| (найдено на скриншоте маршрута) | подпись происхождения районов в карточке источников: v2.1 r5 вместо «патч r4» |

## Проверки (реально выполнены на чистом извлечении `git archive b3e4dc4`)
См. `ACCEPTANCE.json` и `results/candidate_b3e4dc4/`. Кратко:
- K03 (адаптер) PASS 13;
- K05 (адаптер) 20/20, 0 неожиданных;
- K12 12/12;
- K11 19 pass, W1 not_run;
- K08 PASS 13, FAIL 0;
- K01 (адаптер N1) OVERALL PASS;
- K06 (адаптер) PASS 14, WARN 2;
- K10 ui: 0 MUST/SHOULD failures; K10 run_qa: MUST 0, SHOULD 1 FAIL;
- K02 (адаптер) 11/11;
- K07 (адаптер R16) 19/19;
- BUILD smoke 24/24;
- check_all: 14/0/0 с shapely, 13/1 SKIP/0 без.

Оригиналы K01, K02, K03, K05, K06 и K07 запущены рядом. Их провалы — TEST_INCOMPATIBLE: старые имена, API, пути или архивный `offline_check`. Причины и diff адаптеров — в `adapters/*/*.diff` и в ACCEPTANCE. Baseline 064ed25 — `results/baseline_064ed25/`. Маршрут демо в браузере: `demo_route/` (`tools/demo_route.cjs`).

## Ограничения
- Только Linux; `run-demo.bat` и Windows не запускались (K11 W1 not_run).
- Открыто (low): K10 SHOULD — флаг группы координат в `data.js`; сейчас он в `evidence.js`, и UI его показывает.
- K06 N5 WARN: сумма км дорог есть в `data.js`, в UI не показывается.
- Обновление данных K10 требует полного цикла (copy_inputs → K05 наблюдения → атрибуция K08 → сборка); прямые правки входов отклоняются — это намеренно.
- `routes` (K08 F5) остаётся deferred: колонки нет в сохранённом пакете.
- Два квадрата ~2×2 км; районы юридически не проверены; нет LLM и маршрутов.

## Следующий шаг
Показ владельцу по `DEMO_GUIDE.txt`; запуск `run-demo.bat` на Windows и запись результата.
