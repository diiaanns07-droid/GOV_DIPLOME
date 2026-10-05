# K10, раунд 5 — STATUS (REVIEW: QA координат и состава выборки)

| Поле | Значение |
|---|---|
| Роль | REVIEW, слот K10 (`research/round-5/review/K10.txt`) |
| Ветка | `claude/save-work-handoff-j7pc05` |
| Задание и снимки | `origin/codex/research-import-2026-10-05` @ `2883aeb6eb68babc9b346b0aa927d4c633f5163d` |
| Проверяемый BUILD | `claude/beautiful-clarke-sbzomj` @ `0bf27deb8549b325b34a9610402613d745544edb`, `prototypes/city-evidence/` |
| Прочие входы | собственные файлы K10 этой ветки: `research/round-3-results/K10/selection/*_bbox_selection.json`, `research/next-round/K10/samples/*_districts_overture.geojson`, `research/next-round/K10/provenance/raw_extracts.sha256` |
| Статус | **done** для заданного объёма. Исправлений нет (не FIXED): только флаги, тесты и предложения |
| Пути | только `research/round-5-results/K10/` |

## Сделано

- `tools/extract_build.py` — извлечение сборки по SHA с проверкой id git-объектов.
- `tools/qa_flags.py --app-root | --url` → `results/qa_flags_0bf27de.json` (и `…_url_mode.json`), детерминированный.
- `tests/run_qa.py --app-root | --url` — проверки MUST и SHOULD, JSON-отчёт, код выхода 1 при падении MUST.
- `tests/ui_coord_group.cjs --app-root | --url` — Playwright-тест группы из 10 записей.
- `tools/selection_impact.py` — граничная проверка и точный пересчёт выбора квадрата при `--raw-dir`.
- `fixtures/ui_coord_group_shymkent.json` (реальная группа) и `fixtures/ui_coord_group_synthetic.json` (SYNTHETIC).
- `REVIEW.md` — находки, таблицы, предложения для BUILD, команды повтора.

## Реально выполненные проверки (на 0bf27de)

- **`extract_build.py`:** 57 файлов, id git-объектов совпали.
- **`qa_flags.py --app-root`:** два прогона дали побайтно одинаковый результат (sha256 `b32b06a1…`).
- **`qa_flags.py --url`** (локальный `serve.py` извлечённой копии): те же числа флагов.
- **`run_qa.py --app-root`:** 11 MUST PASS, `SHOULD_data_exposes_coord_group_flag` FAIL (ожидаемо).
- **`run_qa.py --url`:** 7 MUST PASS, 1 INFO, тот же SHOULD FAIL.
- **`ui_coord_group.cjs --app-root` и `--url`** (Node 22, Playwright Chromium): 4 MUST PASS, 2 SHOULD FAIL (ожидаемо): с карты достижима 1 из 10 записей группы, обозначения группы нет.
- **`selection_impact.py`:** граничная проверка выполнена. Точный пересчёт на сырых выгрузках раунда 2 тоже, их SHA совпали с закоммиченными:
  - Шымкент: V0–V3 — тот же квадрат, V4 — другой (33 против 34);
  - Астана: во всех вариантах тот же квадрат.

## Ограничения

- **Сырые выгрузки раунда 2 не закоммичены.** Точный пересчёт выбора повторяется только при их наличии; граничная проверка работает без них.
- **Гипотеза о точке-заглушке.** «101 запись любых категорий в точке 69.5958, 42.3167» подсказывает условное геокодирование, но источник Meta этого не подтверждает.
- **Шум правила адресов.** `GROUP_ADDRESS_DIVERGENT` считает русский и казахский варианты одного адреса разными.
- **Только Linux.** UI проверялся в headless Chromium. Карточку с e-mail в адресе я проверял по коду, без скриншота.

## Следующий шаг

1. BUILD при желании реализует предложения 1–3 из REVIEW.md.
2. Затем любой агент повторяет команды из раздела 6 REVIEW.md на новом SHA и сравнивает с `results/*_0bf27de*.json`.
