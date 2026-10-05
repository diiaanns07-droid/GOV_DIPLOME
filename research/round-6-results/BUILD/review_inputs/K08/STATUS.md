# STATUS — K08, раунд 5, REVIEW: атрибуция конечного демо

**Статус:** done в объёме REVIEW: checker, baseline, patch-предложение и положительный контроль готовы. Исправление в BUILD не внесено, поэтому ни один пункт не FIXED.

- Роль: REVIEW. Ветка `claude/dazzling-mayer-drhsxk`, slot K08 (`research/round-5/snapshots.json` @ codex/research-import-2026-10-05). Задание `research/round-5/review/K08.txt`.
- База: BUILD K04 `claude/beautiful-clarke-sbzomj` @ `0bf27deb8549b325b34a9610402613d745544edb`, `prototypes/city-evidence/` (получено через `git archive`, без merge).
- Сравнение с: K08 R4 @ `182cb1b52233baafecc1970fdfd4cb53bc8b8fad`, `research/round-4-results/K08/`.
- Для A9 подгружены (fetch, без merge) коммиты входов: ea703f1, 6778ded, 44585de, 24c1750, d913554, e1e3c71, 7fb8bb8.

## Выходы (`research/round-5-results/K08/`)
- `REVIEW.md` — что есть и чего не хватает в поставляемом демо.
- `check_demo_attribution.py` — checker (`--app-root` / `--url`, `--repo`, `--json`).
- `baseline/app_root_0bf27de.json` (FAIL 8), `baseline/url_0bf27de.json` (FAIL 6), `baseline/smoke_0bf27de.txt` (16/16) — результаты на 0bf27de.
- `test_checker.py` — самопроверка checker на 6 мутациях проходящей сборки.
- `proposal/attribution_demo.patch` — предложение для tools/copy_inputs.py, tools/build_data.py, web/app.js, tests/smoke.cjs.
- `positive_control/` — checker app-root/url (0 FAIL), мутации 6/6, smoke 16/16 и sha256 web-выходов на копии 0bf27de с применённым предложением.

## Реально выполненные проверки
- Прочитаны `tools/copy_inputs.py`, `tools/build_data.py` (place_rec/seg_rec), `web/app.js` (атрибуция, карточки), `web/index.html`, `serve.py`.
- `check_demo_attribution.py --app-root … --repo …`: inputs 40/40 совпадают с manifest и upstream; FAIL A2×3, A3, A4×2 (meta, Foursquare), A6, A7.
- Положительный контроль в отдельном git worktree 0bf27de (scratch): patch применён, `copy_inputs.py` → 45 файлов, `build_data.py` ok; checker app-root 14 PASS / 0 FAIL, url 12 PASS / 0 FAIL; `test_checker.py` 6/6; `unittest` 7 OK; `conformance.cjs` all passed; `smoke.cjs` 16/16. Первый прогон smoke с patch упал (EISDIR в tests/smoke.cjs:89) — это учтено в предложении.
- Мутационный тест выявил пробел в checker A7 (жёсткая подпись OSM не ловилась при наличии dataset); исправлено, baseline и контроль перезапущены, итоги прежние.
- `serve.py 8791` запущен локально, затем `check_demo_attribution.py --url http://127.0.0.1:8791/`: FAIL A2×3, A3, A4×2; WARN A5, A6, A7. Сервер остановлен.

## Ограничения
Юридической проверки нет. Тексты эталона — SPDX @31ba1a50 (R4). Страницы атрибуции Overture и OSM не открывались. Исправление не предложено и не проверено: ни один пункт не FIXED.

## Следующий шаг
Сборщику: применить `proposal/attribution_demo.patch` или собственное исправление, пересобрать (`copy_inputs.py`, `build_data.py`) и выполнить команды из REVIEW.md («Повтор для сборщика»). FIXED можно заявлять только после прогона checker на новом SHA BUILD с 0 FAIL. Схему `source_manifest.json` стоит дополнить полем для изменённых файлов (A10), если такие появятся.
