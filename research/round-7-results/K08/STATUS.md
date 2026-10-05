# STATUS — K08, раунд 7: источники в сценарном отчёте

**Статус:** partial — шаблон, реестр полей, эталонный модуль и фикстуры готовы; тесты — следующий этап.

- Роль: K08, не BUILD. Ветка `claude/dazzling-mayer-drhsxk`. Задание `research/round-7/tasks/K08.txt`, спецификация `research/round-7/FEATURE_SPEC.txt` (codex/research-import-2026-10-05).
- Закреплённый вход: BUILD `claude/beautiful-clarke-sbzomj` @ `c58a3b2b175cf978ad785fef7f88d8fd9b1338f2`, `prototypes/city-evidence/`. `git diff b3e4dc4 c58a3b2 -- prototypes/city-evidence` пуст. Получен через `git archive`. Прототип не менялся.
- Выходы: `research/round-7-results/K08/` — `TEMPLATE.md`, `provenance_fields.json`, `whatif_provenance.py`, `fixtures/`, `cards/`.

## Реально выполнено
- Прочитаны FEATURE_SPEC, структура `web/data.js` (places, sources, bbox, release) и `web/evidence.js` (qa: category_doubt, possible_duplicates, colocated).
- `whatif_provenance.py snapshot shymkent|astana` — отпечатки `sha256:c768bfc3…` и `sha256:1d4570de…`.
- `whatif_provenance.py card` на 3 фикстурах: ok. Шымкент cp1 → «Реклама 42» с QA `ad_or_business_page`; cp2 → проект (230 → 69 м). Астана cp2 → проект (497 → 89 м); без проекта delta = 0.

## Не выполнено / ограничения
- Автотесты модуля ещё не написаны и не запускались.
- Функция в прототипе не существует: интеграцию не заявляю.
- Случай «нет исходных записей» в реальном срезе не встречается (во всех категориях обоих городов записи есть). Он будет проверен только синтетической фикстурой с пометкой synthetic.

## Следующий шаг
`test_whatif_provenance.py --app-root`: snapshot меняется при изменении байта файла мест, импорт с поддельными distances пересчитывается, отклонения по контракту, ничья по ID, before = null, классы всех полей карточки, запрещённые формулировки.
