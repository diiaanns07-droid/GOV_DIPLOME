Задача / идентификатор: K09 — научная основа диплома: проверка библиографии A13/AST-A13; 2–3 узкие темы с вопросом, baseline, данными, метриками и протоколом.
Агент / город / сфера: K09 (Claude Code) / shared (Шымкент и Астана) / диплом и воспроизводимость.
Обновлено: 2026-10-05, ≈05:50 UTC.
Статус: partial (этап 1 из 3 завершён).
Рабочая ветка: claude/save-work-handoff-qho6eq.
Исходный коммит: b87e5af6eeb6a5bdc33037a9f16d4e3377166ee5 (codex/research-import-2026-10-05). Ветка влита обычным merge 4161b40 в мою ветку; та была создана от старого main 834a25f.
Назначенные пути: research/next-round/K09/ и research/handoffs/shared/K09/.

Цель и критерий готовности:
- для каждой работы из A13/AST-A13 указан уровень проверки R0–R4 с файлом и строкой либо причиной отсутствия;
- 2–3 темы описаны с исследовательским вопросом, baseline, входами, метриками, протоколом, требованиями к данным, проверкой на двух городах и препятствиями переноса;
- результаты будущих экспериментов не выдуманы.

Что реально сделано (этап 1):
- Merge исходной ветки импорта в рабочую ветку, без reset и force.
- Прочитаны CLAUDE.md, research/README.md, coordination/STATUS.txt, FIRST_REVIEW.txt, CLAUDE_CAPACITY_12.txt (K09), отчёты A13 и AST-A13 полностью, их evidence (sources).
- Проверка доступа: все научные и издательские хосты отклонены политикой сети (по одному запросу на хост, список в 01_bibliography_verification.md §0).
- Независимо получены авторские файлы 10 репозиториев GitHub на закреплённых коммитах. Хэши 13 общих с AST-A13 файлов совпали.
- Таблица 27 работ с уровнями R0–R4.
- Прочитан исходник статьи SALib JOSS (R4) и препринт ALCE (R4 частично: аннотация, §1–§4.3, фрагмент §6, §8).
- Найдены 3 расхождения с отчётами: название Greshake et al., arXiv-номер NL4Opt, авторы SALib JOSS в CITATION.cff.

Файлы результата:
- research/next-round/K09/01_bibliography_verification.md
- research/next-round/K09/K09_evidence.json
- research/next-round/K09/sources/SHA256SUMS.txt
- research/next-round/K09/scripts/fetch_bib_sources.sh
- research/next-round/K09/scripts/compare_with_ast_a13.py
- research/next-round/K09/scripts/build_evidence.py
- research/next-round/K09/STATUS.md (этот файл)
- research/handoffs/shared/K09/diploma-basis/STATUS.md (указатель на этот файл)

Проверки:
- `bash research/next-round/K09/scripts/fetch_bib_sources.sh <tmp>`, затем `sha256sum -c research/next-round/K09/sources/SHA256SUMS.txt` в <tmp> → 19/19 OK (повторное получение в чистую папку).
- `python3 research/next-round/K09/scripts/compare_with_ast_a13.py` → match=13 differ=0 only_ast=3.
- `python3 research/next-round/K09/scripts/build_evidence.py`, затем `python3 -m json.tool K09_evidence.json` → JSON валиден (38 sources, 10 facts).
- Не запускалось: тесты продукта (исходники приложения не менялись), скрипты A13/AST-A13 (запланированы на этап 2 после чтения кода).

Доказательства и ограничения:
- Проверено: файлы авторов на GitHub, доступ 2026-10-05. Город и период к литературе не относятся.
- Не открыто: doi.org, Crossref, arXiv, OpenAlex, Semantic Scholar, издатели; причина — политика сети (connect_rejected). WebSearch/WebFetch не использовались, чтобы не обходить эту политику.
- Обзор GIS-MCDA и PSS (Malczewski, Geertman, Vonk) остаётся R0, то есть не подтверждён.
- Копии авторских файлов в Git не добавлены (лицензии). Их можно воспроизвести скриптом и проверить по хэшам.

Незавершённое:
- Этап 2: прочитать и воспроизвести пилоты A13-E4 (поручение → ограничения), AST-A13-E5 (казахские числительные), AST-A13-E6 (устойчивость топ-1). На них опираются темы. Плюс проверка конфликтов топонимов двух городов.
- Этап 3: 02_thesis_topics.md — 2–3 темы, матрица «что проверяемо на обоих городах», препятствия переноса, требования к данным, команды.

Следующий конкретный шаг:
1. Прочитать rank_sensitivity.py, kk_numeral_filter.py, constraints_eval.py, затем запустить их на текущем коде и сравнить с заявленными числами.

Для воспроизведения:
- Python 3 (stdlib), git, pdftotext (poppler) для ALCE.pdf. Секретов нет. Сеть: только github.com.
- Команды: см. «Проверки».

Известные конфликты и зависимости:
- Реальные данные городов зависят от K10 и K08 (доступ к gov.kz, stat.gov.kz, data.egov.kz).
- Выбор MVP за координатором и агентом 14.
- Старая запись этой сессии research/handoffs/unassigned/claude-session-0163t6gUHrTgNUScZ2qEcMD5/... описывает состояние до назначения роли K09. Она сохранена без изменений.
