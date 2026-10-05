# STATUS — K08, раунд 5, REVIEW: атрибуция конечного демо

**Статус:** partial — checker и baseline готовы; patch-предложение и положительный контроль — следующий этап.

- Роль: REVIEW. Ветка `claude/dazzling-mayer-drhsxk`, slot K08 (`research/round-5/snapshots.json` @ codex/research-import-2026-10-05). Задание `research/round-5/review/K08.txt`.
- База: BUILD K04 `claude/beautiful-clarke-sbzomj` @ `0bf27deb8549b325b34a9610402613d745544edb`, `prototypes/city-evidence/` (получено через `git archive`, без merge).
- Сравнение с: K08 R4 @ `182cb1b52233baafecc1970fdfd4cb53bc8b8fad`, `research/round-4-results/K08/`.
- Для A9 подгружены (fetch, без merge) коммиты входов: ea703f1, 6778ded, 44585de, 24c1750, d913554, e1e3c71, 7fb8bb8.

## Выходы (`research/round-5-results/K08/`)
- `REVIEW.md` — что есть и чего не хватает в поставляемом демо.
- `check_demo_attribution.py` — checker (`--app-root` / `--url`, `--repo`, `--json`).
- `baseline/app_root_0bf27de.json`, `baseline/url_0bf27de.json` — результаты на 0bf27de.

## Реально выполненные проверки
- Прочитаны `tools/copy_inputs.py`, `tools/build_data.py` (place_rec/seg_rec), `web/app.js` (атрибуция, карточки), `web/index.html`, `serve.py`.
- `check_demo_attribution.py --app-root … --repo …`: inputs 40/40 совпадают с manifest и upstream; FAIL A2×3, A3, A4×2 (meta, Foursquare), A6, A7.
- `serve.py 8791` запущен локально, затем `check_demo_attribution.py --url http://127.0.0.1:8791/`: FAIL A2×3, A3, A4×2; WARN A5, A6, A7. Сервер остановлен.

## Ограничения
Юридической проверки нет. Тексты эталона — SPDX @31ba1a50 (R4). Страницы атрибуции Overture и OSM не открывались. Исправление не предложено и не проверено: ни один пункт не FIXED.

## Следующий шаг
Подготовить patch-предложение для `tools/build_data.py`, `web/app.js` и копирования LICENSES/ATTRIBUTION в `web/`, применить его к копии сборки в scratch и показать, что checker даёт PASS (положительный контроль). Сборщику — повторить:
`python3 research/round-5-results/K08/check_demo_attribution.py --app-root <новая prototypes/city-evidence> --repo .` или `--url http://127.0.0.1:8765/`.
