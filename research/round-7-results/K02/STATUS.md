# K02 r7 — адаптер фактов и объяснение сценария «Если добавить объект»

Роль: K02 (не BUILD). Ветка: claude/clever-mccarthy-pywscu.
Статус: ready_for_review. Модуль изолирован и в общий прототип не интегрирован; это делает сборщик.
Спецификация: research/round-7/FEATURE_SPEC.txt @ codex/research-import-2026-10-05 (7927fa8).
Проверено на: prototypes/city-evidence @ c58a3b2b175cf978ad785fef7f88d8fd9b1338f2 (claude/beautiful-clarke-sbzomj).
- Извлечены web/, tests/ и source_manifest.json: 17 файлов, git blob сверен.
- git diff с кандидатом b3e4dc4 по папке прототипа пуст.
- Используются data.js, evidence.js и facts.js сборки (sha256hex, PlanError, validatePlan, formatValue). Сам facts.js не менялся.

## Файлы
- whatif_calc.js — эталонный расчёт по спецификации:
  - гаверсинус, R = 6371008.8 м, вход [lon, lat], clamp в [0,1], без округления;
  - before = min до записей категории в bbox среза; ничья решается меньшим id;
  - after = min(before, до проекта); delta = before − after;
  - нет записей: before = null, delta = null, after = до проекта;
  - вход проверяется: 1..10 точек, id ≤ 64, конечные координаты в bbox, проект hypothetical той же категории;
  - source_snapshot = sha256 от города, release, bbox, категории, параметров и записей (id, lon, lat). Имя файла не используется;
  - импортированные distances/delta игнорируются, значения всегда считаются заново.
- whatif_facts.js — адаптер:
  - принимает только результат расчётного модуля и проверяет его инварианты, а не пересчитывает;
  - строит каталог в формате facts.js: whatif.source_records и whatif.cpN.before/after/delta, unit m, kind derived; null → unknown с причиной; 0 — значение, а не missing;
  - digest по source_snapshot, категории, точкам, проекту и вычисленным значениям;
  - план проверяется facts.validatePlan сборки (stale_catalog, duplicate_id, null_as_fact);
  - шаблонное объяснение ru/kk (kk — черновик). Точки в тексте обозначены A–J, цифры из пользовательских id в текст не попадают;
  - отдельный блок источников ближайших записей с QA-флагами, отсутствие флага не выдаётся за проверку;
  - блок ограничений из спецификации.
- demo.cjs → examples/shymkent_school.json и examples/astana_outpatient_clinic.json (сценарий, результат расчёта, digest, ru/kk).
- tests/whatif_facts_test.cjs (13 тестов, --app-root); результат runs_c58a3b2.json.

## Проверки (выполнены, Node v22.22.0)
- `node tests/whatif_facts_test.cjs --app-root <c58a3b2 prototypes/city-evidence>` → all 13 passed. Покрыто:
  - старый digest отклоняется (stale_catalog) после перемещения проекта, смены категории, смены города, удаления проекта;
  - after = before и delta = 0 без проекта;
  - нулевое расстояние — 0, а не missing;
  - нет записей категории → before = null, подпись спецификации;
  - ничья по id;
  - подделанный результат отклоняется адаптером;
  - импортированные значения пересчитываются;
  - отказ при вводе вне bbox, NaN, 1e999, дубликате id, >10 точек, чужой категории проекта, проекте в другом городе;
  - snapshot зависит от данных и стабилен;
  - числа в строках фактов ru/kk — округлённые значения каталога;
  - эталон гаверсинуса.
- Мутационная проверка чувствительности тестов, на временной копии:
  - постоянный digest → FAIL W01–W04;
  - отключённая проверка delta → FAIL W08;
  - вывод без округления → FAIL W12.
- `node tests/conformance.cjs` сборки c58a3b2 → all passed (сборка не менялась).
- `node demo.cjs --app-root … --out examples` → примеры обоих городов.

Не запускалось: UI в браузере (модуль не интегрирован), экспорт/импорт JSON-файла ≤256 KiB (это задача другого модуля), LLM (заглушка, не LLM).

## Ограничения
- Это расстояние по прямой до ближайшей записи Overture в сохранённом квадрате, а не время пешком, не доступность и не ближайшее учреждение города.
- Названия источников — данные Overture: они могут содержать цифры и рекламу (например, «Реклама 42» с флагом category_doubt). Они выводятся отдельным экранированным блоком данных, а не как факты.
- kk-формулировки — черновик для проверки носителем.

## HANDOFF сборщику (интеграция — не сделана)
1. Подключить whatif_calc.js (или свой совместимый модуль) и whatif_facts.js после facts.js. deps = {sha256hex, PlanError, validatePlan, formatValue} из CITY_FACTS.
2. При перемещении или удалении проекта, смене категории или города перестраивать каталог. Ответ по старому digest validatePlan отклонит кодом stale_catalog.
3. Повторить `node research/round-7-results/K02/tests/whatif_facts_test.cjs --app-root prototypes/city-evidence` на новом SHA.
