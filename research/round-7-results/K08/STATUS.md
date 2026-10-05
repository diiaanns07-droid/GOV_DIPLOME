# STATUS — K08, раунд 7: источники в сценарном отчёте

**Статус:** done в объёме K08: шаблон, реестр полей, эталонный модуль, фикстуры и тесты. Функция «Если добавить объект» в c58a3b2 отсутствует; интеграция не заявляется.

- Роль: K08, не BUILD. Ветка `claude/dazzling-mayer-drhsxk`. Задание `research/round-7/tasks/K08.txt`, спецификация `research/round-7/FEATURE_SPEC.txt` (codex/research-import-2026-10-05).
- Закреплённый вход: BUILD `claude/beautiful-clarke-sbzomj` @ `c58a3b2b175cf978ad785fef7f88d8fd9b1338f2`, `prototypes/city-evidence/`. `git diff b3e4dc4 c58a3b2 -- prototypes/city-evidence` пуст. Получен через `git archive`. Прототип не менялся.
- Выходы: `research/round-7-results/K08/` — `TEMPLATE.md`, `provenance_fields.json`, `whatif_provenance.py`, `fixtures/`, `cards/`, `test_whatif_provenance.py`, `test_run_c58a3b2.txt`.

## Реально выполнено
- Прочитаны FEATURE_SPEC, структура `web/data.js` (places, sources, bbox, release) и `web/evidence.js` (qa: category_doubt, possible_duplicates, colocated).
- `whatif_provenance.py snapshot shymkent|astana` — отпечатки `sha256:c768bfc3…` и `sha256:1d4570de…`.
- `whatif_provenance.py card` на 3 фикстурах: ok. Шымкент cp1 → «Реклама 42» с QA `ad_or_business_page`; cp2 → проект (230 → 69 м). Астана cp2 → проект (497 → 89 м); без проекта delta = 0.

- `python3 test_whatif_provenance.py --app-root <c58a3b2 prototypes/city-evidence> -v`: **20 OK** (`test_run_c58a3b2.txt`). Покрыто:
  - snapshot из байтов файла (изменённый байт → отказ), города различаются;
  - отказы контракта: чужой snapshot, версия, город, категория, вне bbox, 0 и 11 точек, дубликаты id, 2 проекта, kind/category проекта, NaN, 1e999, дубликат ключа, больше 256 KiB;
  - импортированные distances/delta игнорируются и пересчитываются;
  - без проекта delta = 0; after ≤ before; одна и та же точка даёт 0; эталон гаверсинуса (1° широты = R·π/180); ничья по ID;
  - у ближайшей записи есть источник, лицензия и QA; QA-флаг сохраняется;
  - нет запрещённых формулировок; поля реестра присутствуют;
  - synthetic: без исходных записей before = null, delta = null, есть подпись.
- `grep whatif|hypothetical|если добавить` по web/tools/tests c58a3b2 — совпадений нет: функция не интегрирована.

## Ограничения
- Модуль — эталон для сборщика, а не код прототипа. UI-карточка не реализована и в браузере не проверялась.
- Случай «нет исходных записей» в реальном срезе не встречается, проверен только на synthetic-копии data.js.
- Отпечаток — предложение по составу (city, release, bbox, sha256/bytes файла мест, K10 SHA, параметры). Если сборщик выберет другой канонический состав, нужно согласовать, а не держать два формата.
- QA — метки сборки (`evidence.js`), а не проверка записей.

## Следующий шаг
Сборщику: взять поля карточки и правило snapshot из `TEMPLATE.md` / `provenance_fields.json`. После интеграции прогнать `test_whatif_provenance.py --app-root <новый SHA>` (данные) и сверить карточку UI с `cards/*.card.json` на тех же фикстурах. Интеграцию можно заявлять только после проверки конкретного SHA.
