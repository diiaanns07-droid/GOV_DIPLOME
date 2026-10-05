Задача / идентификатор: K09 — научная основа диплома. Проверка библиографии A13/AST-A13; 2–3 узкие темы с вопросом, baseline, данными, метриками, протоколом.
Агент / город / сфера: K09 (Claude Code) / shared (Шымкент и Астана) / диплом и воспроизводимость.
Обновлено: 2026-10-05, ≈06:00 UTC.
Статус: ready_for_review по этапам 1–3 (проверка библиографии, воспроизведение пилотов, темы). Обзор литературы остаётся partial: работы GIS-MCDA/PSS не подтверждены (R0) из-за блокировки сети.
Рабочая ветка: claude/save-work-handoff-qho6eq.
Исходный коммит: b87e5af6eeb6a5bdc33037a9f16d4e3377166ee5 (codex/research-import-2026-10-05). Влит обычным merge 4161b40 в ветку сессии; та была создана от старого main 834a25f.
Назначенные пути: research/next-round/K09/ и research/handoffs/shared/K09/.

Цель и критерий готовности:
- для каждой работы указан уровень R0–R4 с файлом и строкой или причиной отсутствия;
- 2–3 темы описаны: вопрос, baseline, входы, метрики, протокол, требования к данным, что проверяемо на двух городах, что мешает переносу;
- результаты будущих экспериментов не выдуманы.

Что реально сделано:
1. Этап 1 — библиография (коммит ea37171).
   - Все научные и издательские хосты отклонены политикой сети.
   - Авторские файлы 10 GitHub-репозиториев получены на закреплённых коммитах; 13 общих с AST-A13 файлов совпали по SHA-256.
   - 27 работ получили уровни R0–R4. Полный текст прочитан: SALib JOSS (R4) и препринт ALCE (R4 частично).
   - Найдены 3 расхождения с отчётами A13/AST-A13.
2. Этап 2 — воспроизведение пилотов.
   - Код трёх присланных скриптов прочитан до запуска.
   - check.py: 12 из 12; pytest: 112 passed.
   - A13-E4 и AST-A13-E5 воспроизведены побайтно; AST-A13-E6 совпадает во всех полях, кроме времени.
   - Новый прогон E6b с n = 300 (seeds 101–103) согласуется с n = 60.
   - Новый E8: словарный парсер A13 распознаёт kk-названия районов Астаны из OSM в 1 из 5 случаев.
3. Этап 3 — темы.
   - Т1: поручение → ограничения ru/kk и топонимы двух городов.
   - Т2: устойчивость рекомендации портфеля мер.
   - Т3: перенос OSM-индикатора обеспеченности объектами с Астаны на Шымкент, оценка на уровне объектов.
   - Резервная Т4: проверяемые объяснения.
   - Добавлены матрица проверяемости на двух городах, препятствия переноса, требования к данным, критерии решения, заданные до эксперимента.

Файлы результата:
- research/next-round/K09/01_bibliography_verification.md
- research/next-round/K09/02_pilot_reproduction.md
- research/next-round/K09/03_thesis_topics.md
- research/next-round/K09/K09_evidence.json (40 sources, 17 facts, 3 opportunities)
- research/next-round/K09/sources/SHA256SUMS.txt
- research/next-round/K09/repro/: E4/E5/E6 stdout и run_meta, E6b_n60_seeds1-3_equivalence.json, E6b_n300_seeds101-103.json (с сырыми выборками), E8_toponym_stems.json
- research/next-round/K09/scripts/: fetch_bib_sources.sh, compare_with_ast_a13.py, build_evidence.py, run_pilots.py, e6b_rank_sensitivity.py, e8_toponym_stems.py
- research/handoffs/shared/K09/diploma-basis/STATUS.md (указатель на этот файл)

Проверки (фактически выполнены):
- fetch_bib_sources.sh в чистую папку, затем sha256sum -c → 19 из 19 OK.
- compare_with_ast_a13.py → match=13, differ=0, only_ast=3.
- check.py → «все 12 проверок пройдены», exit 0.
- pytest -q → 112 passed in 13.44 s (Python 3.12.3, numpy 2.4.4).
- run_pilots.py E4 E5 E6 → returncode 0. E4 и E5 побайтно равны оригиналам; E6 равен, кроме поля seconds.
- e6b_rank_sensitivity.py --n 60 --seeds 1 2 3 → агрегаты равны AST-A13-E6.
- e6b --n 300 --seeds 101 102 103 → 513.9 с, результат в repro.
- e8_toponym_stems.py → ru 4 из 5, kk(name) 1 из 5, kk(name:kk) 0 из 3.
- json.tool для K09_evidence.json и всех repro/*.json → валидны.
- Не запускалось: A13-E2 (масштаб), A13-E3 (API-сервер), AST-A13-E7 (конфигурации). Харнесс LLM не запускался, LLM-ключи не использовались.

Доказательства и ограничения:
- Литература подтверждена только авторскими файлами на GitHub. doi.org, Crossref, arXiv, издатели отклонены политикой (connect_rejected), обход не делался; WebSearch/WebFetch не использовались.
- Все эксперименты относятся к учебной (synthetic) модели или к синтетическим тестовым фразам. О реальных Астане и Шымкенте они ничего не говорят.
- Названия районов Шымкента есть только как гипотезы A04, A11 и A12. В E8 Шымкент не проверялся.
- Копии авторских файлов (README, CITATION, ALCE.pdf) в Git не добавлены. Их можно воспроизвести скриптом и проверить по хэшам.

Незавершённое:
- R0-работы GIS-MCDA/PSS (Malczewski 2006, Malczewski & Rinner 2015, Geertman & Stillwell 2004, Vonk et al. 2005) и Lempert et al. 2003; название и версия Greshake et al. (arXiv 2302.12173).
- Для Т1 не реализованы: baseline B2, метрика регрета, харнесс LLM, набор поручений.
- Для Т2 не реализованы: разбиение design/held-out, правила выбора, SALib/Sobol.
- Для Т3 нет данных и кода.

Следующий конкретный шаг:
1. Владельцу: открыть в настройках окружения доступ к doi.org, api.crossref.org и arxiv.org (или прислать PDF) для проверки R0-работ. Затем реализовать B2 и метрику регрета в отдельном скрипте research/next-round/K09/ на основе харнесса A13-E4. Исходники продукта не трогать.

Для воспроизведения:
- `python3.12 -m venv venv && venv/bin/pip install numpy==2.4.4 jsonschema==4.26.0 pytest`. Секретов нет.
- Из корня репозитория:
  - `venv/bin/python check.py`
  - `venv/bin/python -m pytest -q`
  - `venv/bin/python research/next-round/K09/scripts/run_pilots.py E4 E5 E6`
  - `venv/bin/python research/next-round/K09/scripts/e6b_rank_sensitivity.py --n 300 --seeds 101 102 103 --out /tmp/e6b.json`
  - `python3 research/next-round/K09/scripts/e8_toponym_stems.py`
  - `bash research/next-round/K09/scripts/fetch_bib_sources.sh /tmp/bib && (cd /tmp/bib && sha256sum -c <repo>/research/next-round/K09/sources/SHA256SUMS.txt)`
  - `python3 research/next-round/K09/scripts/compare_with_ast_a13.py`
  - `python3 research/next-round/K09/scripts/build_evidence.py`

Известные конфликты и зависимости:
- Официальные перечни районов, доли населения и перечни объектов: K10/K08 (доступ к gov.kz, stat.gov.kz, data.egov.kz).
- Выбор MVP: координатор или агент 14.
- Старая запись этой сессии research/handoffs/unassigned/claude-session-0163t6gUHrTgNUScZ2qEcMD5/... описывает состояние до назначения роли K09. Сохранена без изменений.
