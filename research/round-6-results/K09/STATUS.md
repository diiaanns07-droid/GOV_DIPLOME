Задача: K09 round-6 REVIEW — воспроизводимость результата диплома (T1) на новой сборке.
Источник задания: origin/codex/research-import-2026-10-05:research/round-6/review/K09.txt @ edee718.
Обновлено: 2026-10-05.
Статус: ready_for_review.
Ветка: claude/save-work-handoff-qho6eq.

Проверено:
- target_sha: 064ed25368341edaa50289bc29e21dda7bdd9440 (claude/beautiful-clarke-sbzomj, prototypes/city-evidence/).
- test_source_sha: e4ac24fcdca2701f6fd674e59cbd485f0de42ece (research/round-3-results/K09 этой ветки).
- Старый 0bf27de не проверялся.

Сделано:
- Дерево TARGET собрано через git archive; поверх наложены замороженные инструменты K09 из SOURCE (git archive). Репозиторий не менялся, B2 и evaluator не переписывались.
- Инварианты (подробности в ACCEPTANCE.json):
  - I1 PASS: код, от которого зависит inference, в TARGET идентичен SOURCE.
  - I2 PASS: все замороженные хэши (FREEZE 6/6, DATASET 4/4, external 2/2).
  - I3 PASS: независимый пересчёт по сохранённым predictions — held-out B2 34/34, B1 2/34; external B2 24/32, B1 1/32; dev 20/20 и 5/20; 0 расхождений.
  - I4 PASS: повтор замороженного inference в дереве TARGET — 15/15 файлов побайтно идентичны.
  - I5 PASS_WITH_CORRECTION: 8 внешних ошибок — все ошибки парсера, все эталоны верны. Два независимых агента-проверяющих и собственная трассировка K09 согласны. Поправка: у x-ru-03 первичная причина F3, а не F1.
  - I6 PASS: парсер не подключён к действиям сайта TARGET (статический git grep).
  - I7 SKIP_BY_DESIGN: регрет.
  - I8 SKIP: LLM (ключа нет).
- Новые находки по исследовательскому парсеру (не по сборке), с минимальным repro:
  - N1 (b2_parser.py:161): «ЛРТ из плана уберите» → include M3, инверсия смысла.
  - N2 (:212, :245): район найден, мера не найдена → ok с пустыми ограничениями.
  - Оба repro в evidence/repro_new_findings.txt.

Реально выполненные проверки (команда — scripts/run_acceptance.sh, выходы — evidence/):
- sha256sum -c FREEZE и DATASET_SHA256; хэши external по agreement.json → OK.
- recompute_metrics.py (без импорта t1_eval) → 7/7 совпадений с сохранёнными metrics.
- t1_eval.py ×3, ingest_external.py, t1_eval_external.py в дереве TARGET; cmp с выходами SOURCE → 15/15 IDENTICAL.
- git grep TARGET на код K09, ввод поручений, optimize и сеть в прототипе → ничего.
- Workflow wf_53097b5d-f9b: независимые линзы «разметка» (без кода парсера) и «трассировка парсера» → evidence/errors_8_attribution.json.
- Не запускалось: браузер и сервер прототипа (I6 — только статическая проверка), LLM, тесты продукта (в зоне K09 не требуются).

Ограничения:
- Все фразы синтетические, kk не проверен носителем.
- Независимость модельных агентов — не человеческая проверка.
- 8/32 уверенных ошибок исключают автоматические действия по выводу B2.
- n мал; названия районов не подтверждены официально.
- TEST_INCOMPATIBLE не обнаружено: адаптер не потребовался.

Следующий шаг: набор поручений от людей с двойной разметкой и проверкой kk носителем; затем B2.1 (N1, N2, F1–F5) на новом внешнем наборе. В сборку парсер не подключать.
