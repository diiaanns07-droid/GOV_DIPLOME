Задача / идентификатор: K02, проверка AST-A13 E5 (казахские числительные в фильтре советника)
Агент / город / сфера: K02 (Claude Code), shared, проверяемый AI
Обновлено: 2026-10-05, UTC
Статус: ready_for_review (проверка выполнена; перенос в продукт — отдельная задача)
Рабочая ветка: claude/clever-mccarthy-pywscu
Исходный коммит: 170f95bef5f7d6df11b0315b241e0c16e1ec900b (merge codex/research-import-2026-10-05 b87e5af в ветку сессии)
Назначенные пути: research/next-round/K02/, этот файл

Цель: независимо проверить утверждение AST-A13 о пропуске казахских числительных, воспроизвести на минимальном примере, дать прототип и ru/kk случаи с допустимыми ответами.

Что реально сделано:
- Прочитаны agent/evidence.py, вызов в agent/advisor.py:253, промпт agent/prompts.py, отчёт и скрипт AST-A13 E5.
- Скрипт AST-A13 прогнан без изменений против текущего кода: результат идентичен сохранённому (ru 1/4, kk 4/6 чисел прошли фильтр).
- Собственный набор 34 случаев: текущий фильтр пропускает ru 3/7, kk 13/15 числовых фраз; ложных удалений 0/12.
- Найдена доп. ошибка: проверка [А-Яа-яA-Za-z]{3} отвергает чисто казахский допустимый комментарий (EvidenceError на «Іс әлі ұзақ.»).
- Изолированный прототип qualitative_comment_v2: 0 утечек, 0 ложных удалений на тех же 34 случаях (внутренняя выборка, не оценка обобщения).

Файлы результата:
- research/next-round/K02/REPORT.md
- research/next-round/K02/cases.json
- research/next-round/K02/kk_numeral_guard.py
- research/next-round/K02/run_k02.py, results.json
- research/next-round/K02/limits_probe.py, limits_probe_result.json
- research/next-round/K02/test_k02.py
- research/next-round/K02/replication_ast_a13_e5.json

Проверки:
- PYTHONPATH=. python3 <AST-A13 kk_numeral_filter.py> → совпадает с kk_numeral_filter_result.json (True).
- python3 research/next-round/K02/run_k02.py → сводка выше.
- python3 -m unittest research/next-round/K02/test_k02.py → 3 tests OK.
- Python 3.11.15. Не запускалось: pytest и check.py продукта (код продукта не менялся).

Доказательства и ограничения:
- Все фразы синтетические; kk-формулировки K02 требуют проверки носителем.
- Реальные ответы LLM не собирались (нет ключа API/цели); частота проблемы в продукте не измерена.
- Не ловятся порядковые числительные (в обоих языках), латиница kk, «жүзі»; «бір»-артикль удаляется ложно.
- Сеть для этой задачи не требовалась и не использовалась.

Незавершённое:
- Ревизия cases.json носителем; перенос в agent/evidence.py и self_check.py.

Следующий конкретный шаг:
1. Носитель казахского проверяет и дополняет cases.json; затем отдельная задача на изменение agent/evidence.py с pytest и check.py.

Для воспроизведения (из корня репозитория):
- python3 research/next-round/K02/run_k02.py
- python3 research/next-round/K02/limits_probe.py
- python3 -m unittest research/next-round/K02/test_k02.py
- PYTHONPATH=. python3 research/astana-results/13_architecture_ai_thesis/extracted_files__34_/kk_numeral_filter.py

Конфликты и зависимости: K05 (контракт данных) не затронут; изменение agent/evidence.py должен интегрировать координатор.
