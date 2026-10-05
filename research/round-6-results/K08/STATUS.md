# STATUS — K08, раунд 6, REVIEW: атрибуция и модифицированные копии

**Статус:** done — приёмка выполнена. Вердикт **NOT_ACCEPTED**: 1 дефект, 7 из 8 инвариантов PASS.

- Цель: BUILD `claude/beautiful-clarke-sbzomj` @ **`064ed25368341edaa50289bc29e21dda7bdd9440`**, `prototypes/city-evidence/`. Получен через `git archive`, без merge. Старая сборка 0bf27de повторно не проверялась.
- Тест-источник: `research/round-5-results/K08/check_demo_attribution.py` @ `cdcfd20` (sha256 c450abd8…), без изменений. Baseline и ожидаемые FAIL раунда 5 не применялись.
- Новое (`research/round-6-results/K08/`):
  - `check_r6_acceptance.py` — инварианты I1–I8;
  - `repro_road_card_label.cjs` — минимальный repro;
  - `ACCEPTANCE.json`, `run/`;
  - `proposal/road_card_label.patch`.
- Для I1/I2 подгружены (fetch, без merge) коммиты всех входов из `source_manifest.json` и `inputs/r4/MANIFEST.json`.

## Вердикты на 064ed25
| Инвариант | Вердикт |
|---|---|
| I1 архивные копии source_manifest 40/40 = manifest = upstream | PASS |
| I2 архивные копии inputs/r4/MANIFEST 82/82 = manifest = upstream | PASS |
| I3 K03 v2: original ≠ patched, hash раздельны, патч = архивная копия r4, прочие файлы = k03_root, повторный setup воспроизводит hash | PASS |
| I4 контракт k05-obs-v1.2+k12r4: 1 из 4 файлов modified, hash раздельны, флаги согласованы, воспроизводимо | PASS |
| I5 K02 v4: original/adapted hash раздельны, воспроизводимо | PASS |
| I6 используются модифицированные копии; архивные не импортируются | PASS |
| I7 routes: значений нет, пробел задокументирован (README:55, app.js:468) | PASS |
| I8 атрибуция web (checker R5): A2–A6, A8, A9 PASS; **A7 FAIL** | FAIL |

**Дефект R6-K08-D1** (`web/app.js:389`): заголовок карточки дороги жёстко «Дорога (OSM через Overture)». Для 9 сегментов TomTom это противоречит строке «Источник» той же карточки (`app.js:397`).
- Repro: `repro_road_card_label.cjs --app-root …` даёт 9/9 mislabeled, exit 1.
- Предложение: `proposal/road_card_label.patch` (1 строка, `git apply --check` на 064ed25 проходит). На копии с patch: repro 0/9, приёмка 8/8. Это **не FIXED**: в BUILD не внесено.

## Реально выполненные проверки
- `check_r6_acceptance.py --app-root <064ed25> --repo .`: PASS 7, FAIL 1. Повторный запуск setup_k03_v2/setup_contract/setup_k02 шёл в копии.
- Checker R5 `--app-root --repo`: PASS 12, FAIL 1. `--url` (serve.py 8795): PASS 10, FAIL 1. Сервер остановлен.
- Repro в Chromium (Playwright, file://): 9/9; ошибок страницы нет.
- Проверка адаптера: мутация k03v2 boundary_validator.py даёт I3 FAIL. Копия с patch даёт 8/8 PASS.
- TEST_INCOMPATIBLE не обнаружено: checker R5 нашёл `web/attribution/` по уже предусмотренным путям.

## Пропущено (не PASS)
Тесты BUILD (smoke, conformance, unittest) не перезапускались — вне задания K08. Юридической проверки нет.

## Следующий шаг
Сборщику: исправить `web/app.js:389` (например, `proposal/road_card_label.patch`) и повторить команды из `ACCEPTANCE.json` на новом SHA. Приёмку можно считать выполненной только при 8/8 на этом SHA.
