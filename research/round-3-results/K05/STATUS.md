# K05 round 3 — адаптер реальных данных: STATUS

Статус: **ready_for_review** (все пункты задания выполнены; интеграция в продукт — отдельный этап)
Обновлено: 2026-10-05 UTC. Ветка: `claude/optimistic-davinci-1oiqs9`.
Задание: `research/round-3/prompts/K05.txt` @ codex/research-import-2026-10-05 (6602bb8).
Предыдущий K05: 6d39cc5 (`research/next-round/K05/` не изменён; его валидатор импортируется).
Входы: K10 `claude/save-work-handoff-j7pc05` @ e91898d596164bcf6e853b921a49f82126074a35 → `inputs/k10/` (git blob каждого файла сверен, `inputs/MANIFEST.json`);
список выпусков Overture S3 `inputs/overture_release_index_2026-10-05.xml` (1 запрос, HTTP 200, 06:17Z).
Другие ветки не сливались.

## Сделано
- Адаптер `k05r3_adapter.py`: K10 E02 + образцы → k05-obs-v1.1, Шымкент (56+7+1) и Астана (84+7+1), показатель «число записей Overture places группы в районе» с охватом, методом, sha256/URL, версией границы.
- Схема `schema/k05-obs-v1.1.schema.json`, семантика `k05r3_contract.py` (агрегат, дубликаты, давность, границы).
- Все 8 случаев в `cases/cases.json`: настоящий 0 (Шымкент, Еңбекші, government_office ≥ 0.5), missing (официальный счёт, оба города, доступ закрыт), неполная выборка/охват, смешение городов/периодов, дубликаты (реальные в обоих городах + фикстура), synthetic (фикстура), устаревший/вытесненный снимок, несовпадение границы (Сарайшык @16 ≠ @17).
- Regression `regression/test_handle_failure.py` и patch `patches/fetch_real_context_null_on_failure.patch` (не применён).
- Новые находки: рамка выгрузки K10 покрывает Шымкент на 98,11% и Астану на 97,23% (Абай, Есиль, Байконур — нижние границы); реальные кандидаты в дубликаты и точка-заглушка; см. REPORT.md §2–3.

## Проверки (реально выполнены, Python 3.11.15)
- `python research/round-3-results/K05/tests/test_k05r3.py` → Ran 18 tests, OK (jsonschema 4.26.0 Draft 2020-12 + семантика).
- `python research/round-3-results/K05/regression/test_handle_failure.py` → Ran 6 tests, OK (expected failures=3: текущий продукт нарушает контракт; копия с patch проходит).
- `git apply --check` patch к HEAD — ok; sha256 `data/real_context*.json`, `fetch_real_context.py` до/после тестов совпадают.
- Повторный запуск адаптера — те же sha256 всех выходов. `python research/next-round/K05/test_k05_validator.py` — OK (9).
- `python -m json.tool` по всем новым JSON — ok.
- Не запускалось: тесты продукта (код продукта не менялся); пересчёт E02 по сырым строкам Overture (их нет в git).

## Ограничения
- Overture — вторичный источник, полнота неизвестна; официальные источники закрыты (K10 access_log, CONNECT 403), повторно не запрашивались.
- Счётчики районов взяты из K10 E02; независимо проверены площади, образцы и их согласованность с E02.
- Оценки пар-дубликатов — гипотезы; max_age_days=45 — параметр примера.

## Следующий шаг
Координатору: решить об интеграции (REPORT.md §6). K10 или следующему агенту: перевыгрузить places Overture с рамкой из полигона города и буфером, затем перезапустить адаптер — Абай/Есиль/Байконур получат complete=true.

## Воспроизведение
См. REPORT.md §7.
