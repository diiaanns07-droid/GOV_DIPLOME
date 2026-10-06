# STATUS — K08, раунд 9: экспорт устойчивого плана

**Статус:** этап 1 из 3 выполнен; этапы 2–3 в работе.

- Роль K08 (не BUILD), ветка `claude/dazzling-mayer-drhsxk`. Задание `research/round-9/tasks/K08.txt`, CORE_SPEC r9 @ codex/research-import-2026-10-05.
- **Проверенный BUILD:** `claude/beautiful-clarke-sbzomj` @ `d865dd4a124291e10dd0b7bb1d9eada20d34c268` (HEAD ветки на 2026-10-06; код = 3e1302a по `git diff`). Извлечён через `git archive`; sha256 файлов web — `run/build_manifest_d865dd4.sha256`. Прототип не менялся.
- Мои входы r8: `research/round-8-results/K08/` @ 7fb81b9 (planlib.py — независимый Python-оракул, fixtures).

## Этап 1 — reportHtml / exportPlanScenario BUILD против ожиданий r8
Инструменты:
- `build_adapter.cjs` — вызывает API `web/plan.js` сборки в Node так же, как `plan-ui.js`: validate → export → import → evaluate → optimize → sensitivity → reportHtml. Плюс подделка derived и чужой snapshot.
- `build_compat.py` — r8-оракул с формулой snapshot BUILD. Единственное отличие от моего r8: последним элементом идёт `METRIC "haversine-mm-v1"`, а не строка формулы.
- `check_stage1.py` — вердикты.

`python3 check_stage1.py --app-root <d865dd4> --json run/stage1_d865dd4.json` → **10 PASS, 1 FAIL**:

| Проверка | Вердикт |
|---|---|
| S0 API BUILD вызывается без исключений (7 заданий) | PASS |
| S1 source_snapshot BUILD = независимый пересчёт (оба города) | PASS |
| S2 export → import: тот же сценарий | PASS |
| S3 изменённые derived_results → `forged_derived` | PASS |
| S4 чужой snapshot → `foreign_snapshot` | PASS |
| S5 ручной план, строки, mean/minimax/coverage, Парето, feasible_count = r8-оракул (4 фикстуры, вкл. 16 кандидатов) | PASS |
| S6 без исходных записей (synthetic): before/delta = null в API, экспорте и отчёте, не 0 | PASS |
| S7 max-size (25 точек, 16 кандидатов, 64-символьные кириллические ID): экспорт 21 600 B ≤ 256 KiB, импорт ok | PASS |
| S8 reportHtml: белый список тегов/атрибутов, CSP `default-src 'none'`, нет внешних загрузок | PASS |
| S9 HTML в имени записи/городе/выпуске/атрибуции/объяснении → только текст | PASS |
| **S10** provenance ближайших записей в отчёте | **FAIL** |

**S10 (пробел продукта относительно r8/CORE_SPEC «видимые source/QA»):** в `reportHtml` (`web/plan.js:376–410`) есть source_snapshot, release, digests и общая строка атрибуции. Но нет:
- id ближайших исходных записей (в строках только имя через `m.names`);
- источника/лицензии каждой записи;
- QA-флагов;
- bbox среза;
- sha256 файла мест.

Repro: `reportHtml(m)` для `shymkent_school_demo` — этих полей в тексте нет. Это не ошибка адаптера: адаптер передаёт ровно то, что передаёт `plan-ui.js:reportText`.

## Следующий шаг
Этап 2: узкий адаптер отчёта устойчивости (`city-resilience-v1`): вход envelope без derived, пересчёт через API BUILD (evaluate/optimize v2 на отфильтрованных записях), per-case manual/nominal/robust, worst_case_ids, цена устойчивости или причина null, provenance исключённых записей, версии и digests, статический HTML.
