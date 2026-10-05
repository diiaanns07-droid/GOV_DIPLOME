# K06 round 7 — независимая проверка расстояний (what-if)

Роль: K06 (не BUILD). Ветка: claude/ecstatic-curie-hzfzn0 (начало раунда от 33bbfe71a0673c478ad7d56f5382a17692f39f65).
Задание: origin/codex/research-import-2026-10-05 @ 7927fa8, research/round-7/tasks/K06.txt, FEATURE_SPEC.txt.
Статус: done для оракула и fixture; интеграция в сборку не проверялась (в c58a3b2 функции what-if нет).

Входы: claude/beautiful-clarke-sbzomj @ c58a3b2b175cf978ad785fef7f88d8fd9b1338f2, prototypes/city-evidence/
(185 файлов, git blob id пересчитан; git diff с кандидатом b3e4dc4 по папке прототипа пуст).

Реально выполнено (Python 3.11.15):
- test_whatif_oracle.py --app-root <c58a3b2> → 19 OK; без --app-root → 13 OK, 1 SKIP (метаморфные).
- make_fixture.py → 12 реальных сценариев, 120 строк; оракул и независимая хорда ≤ 1,15e-9 м; повтор побайтно идентичен.
- Исправлено в собственном тесте: «ничья» ±Δφ не точна в плавающей точке → используются записи с одинаковыми координатами.

Не выполнялось: проверка реализации сборщика (её нет на зафиксированном SHA); импорт/экспорт JSON (вне задания K06).
Следующий шаг: после коммита сборщика с функцией — прогнать fixtures/whatif_fixture.json через его реализацию
(значения ±1e-6 м, must_reject) на конкретном SHA.
