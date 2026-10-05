# K07 · Раунд 8 · HANDOFF

Ветка `claude/save-work-handoff-ku3ej3`; последний push — в `git log` этой папки. Подробности: `STATUS.md` (этапы и проверки), `REVIEW_BUILD.md` (дефекты BUILD), `API.md` (интерфейсы).

## Состояние

| Этап | Статус |
|---|---|
| 1. Редактор: места, стоимости, веса, required/excluded, бюджет, максимум, радиус, ручной план; адаптер расчёта | готово: calc 144/144, UI U1–U23 |
| 2. Три стратегии, «Применить», прогресс, отмена, устаревание, Парето, бюджеты, клавиатура, 390 px | готово: UI S1–S17c, всего 41/41; мутации ловятся |
| 3. Браузерные тесты пути и отказов, патч для BUILD | готово: проверен BUILD `d865dd4` — движок 211/211, UI 26/31 (5 дефектов); с патчем K07 — 31/31, тесты BUILD без регрессий |

## Что лежит где

- **Модули** — `web/`: `plan_calc.js`, `plan_runner.js`, `plan_demo.js`, `planner_ui.js` (источник истины). Предложение UI для `a5b5e2d` — `patch/city_evidence_planner.patch`, в нём и правки `app.js` / `index.html`.
- **Исправления для BUILD `d865dd4`** — `patch/build_d865dd4_planner_keyboard_390.patch`: только правки строк `app.js`, `plan-ui.js` и `index.html`.
- **Тесты** — `tests/`:
  - `plan_calc.test.cjs` и `oracle_plan.py` — расчёт K07;
  - `plan_cases.cjs` — общие случаи;
  - `build_engine_crosscheck.cjs` — движок BUILD;
  - `k07r8_planner_ui.cjs` — UI K07;
  - `k07r8_build_planner.cjs` — UI BUILD.
- **Данные и результаты** — `fixtures/`: SYNTHETIC-сценарии и `MANIFEST.json`; `results/`: прогоны, каждый с SHA.

## Команды

```bash
git fetch origin claude/beautiful-clarke-sbzomj
export NODE_PATH="$(npm root -g)"
bash research/round-8-results/K07/scripts/run_build_review.sh             # BUILD d865dd4 и d865dd4 + патч K07
bash research/round-8-results/K07/scripts/run_build_review.sh <NEW_SHA>   # новая сборка BUILD как есть
bash research/round-8-results/K07/scripts/run_planner.sh                  # предложение K07 на a5b5e2d
```

## Как продолжить правку предложения K07 (a5b5e2d)

```bash
SP=$(mktemp -d)
python3 research/round-8-results/K07/scripts/extract_build.py "$SP/base"
mkdir -p "$SP/w/prototypes/city-evidence" && cp -r "$SP/base/web" "$SP/base/tests" "$SP/w/prototypes/city-evidence/"
(cd "$SP/w" && git apply -p1 "$OLDPWD/research/round-8-results/K07/patch/city_evidence_planner.patch")
# app.js / index.html правятся в $SP/w/prototypes/city-evidence/web, модули — в research/round-8-results/K07/web/
cp research/round-8-results/K07/web/*.js "$SP/w/prototypes/city-evidence/web/"
python3 research/round-8-results/K07/scripts/make_patch.py "$SP/base" "$SP/w/prototypes/city-evidence"
```

## Для BUILD

- Патч `build_d865dd4_planner_keyboard_390.patch` правит строки и не заменяет `plan.js` / `plan-ui.js`.
- Все правки помечены `K07 r8` с ID дефекта (K2–K5, N2).
- После интеграции нужен прогон `run_build_review.sh <NEW_SHA>`: без него исправления не считаются принятыми.
- Не применять `city_evidence_planner.patch` к `d865dd4`: это альтернативный UI для `a5b5e2d` с тем же глобальным именем `window.CITY_PLAN_UI`; `git apply --check` его отвергает.
