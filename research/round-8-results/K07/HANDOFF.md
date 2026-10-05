# K07 · Раунд 8 · HANDOFF

Подробности — в `STATUS.md`. Ветка `claude/save-work-handoff-ku3ej3`; последний push указан в git log этой папки.

## Где что лежит

- `web/` — модули. Источник истины для `plan_calc.js`, `plan_runner.js`, `plan_demo.js` и `planner_ui.js`.
- `patch/city_evidence_planner.patch` — источник истины для правок `app.js` и `index.html` BUILD `a5b5e2d`.
- `tests/`, `fixtures/`, `scripts/`, `results/`.

## Как продолжить с чистого места

```bash
git fetch origin claude/beautiful-clarke-sbzomj
SP=$(mktemp -d)
python3 research/round-8-results/K07/scripts/extract_build.py "$SP/base"                 # a5b5e2d
mkdir -p "$SP/w/prototypes/city-evidence" && cp -r "$SP/base/web" "$SP/base/tests" "$SP/w/prototypes/city-evidence/"
(cd "$SP/w" && git apply -p1 "$OLDPWD/research/round-8-results/K07/patch/city_evidence_planner.patch")
# правки app.js / index.html делать в $SP/w/prototypes/city-evidence/web, модули — в research/round-8-results/K07/web/
cp research/round-8-results/K07/web/*.js "$SP/w/prototypes/city-evidence/web/"
python3 research/round-8-results/K07/scripts/make_patch.py "$SP/base" "$SP/w/prototypes/city-evidence"
NODE_PATH="$(npm root -g)" bash research/round-8-results/K07/scripts/run_planner.sh
```

## Состояние этапов

| Этап | Статус |
|---|---|
| 1. Редактор: места, стоимости, веса, required/excluded, бюджет, максимум, радиус, ручной план; адаптер расчёта | готово, проверено (calc 120/120, UI 22/22, тесты BUILD без регрессий) |
| 2. Три стратегии, «Применить», прогресс, отмена, устаревание, Парето, бюджеты, клавиатура, 390 px | готово, проверено (UI 41/41 вместе с этапом 1; мутации ловятся) |
| 3. Браузерные тесты пути и отказов, патч для BUILD, `API.md` | в работе |

## Для BUILD

- Патч не перезаписывает модули BUILD: добавляет 4 файла и точечные правки `app.js` и `index.html`. Все правки помечены `K07 r8`.
- v1 (`whatif.js`) не тронут.
- Если BUILD уже сделал свой редактор v2, брать стоит модули расчёта и тесты, а не UI. Тест UI на чужом API даст `TEST_INCOMPATIBLE P0`, а не PASS.
