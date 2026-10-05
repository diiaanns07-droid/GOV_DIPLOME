Задача: K09 round-3 — воспроизводимый эксперимент T1 «поручение ru/kk → структурированные ограничения» (prompt research/round-3/prompts/K09.txt @ codex/research-import-2026-10-05 6602bb8).
Агент / город / сфера: K09 (Claude Code) / Астана и Шымкент раздельно / диплом.
Обновлено: 2026-10-05.
Статус: partial — этап A (набор данных и правила зафиксированы до реализации B2).
Рабочая ветка: claude/save-work-handoff-qho6eq. Предыдущий результат (snapshot): 9cc36c3; до начала раунда в ветке также 11bd74a (исправления K09 next-round).
Назначенный путь: research/round-3-results/K09/.

Сделано (этап A):
- Входы: K03 @ a8f1e17 (claude/epic-curie-iitc43) territory_registry.json; K10 @ e91898d (claude/save-work-handoff-j7pc05) Overture-районы обоих городов.
  - Скопированы байт в байт через `git show sha:path > file`; git blob копий совпадает с источником (inputs/MANIFEST.json).
  - Ветки не сливались. Используется K03 из epic-curie, а не из clever-mccarthy.
- gazetteer.json: Астана — 6 районов (OSM/Overture, не официально; Сарайшык нет в учебной модели); Шымкент — 4 района county из Overture (K10, не официально); Тұран — unconfirmed.
- measure_catalog.json: M1–M14 учебной модели (synthetic); kk-названия — перевод K09 (synthetic).
- t1_dataset.jsonl: 54 синтетических примера (ru 27, kk 27); dev 20, held-out 34; разбиение по шаблонам и вариантам сущностей. Эталон по ANNOTATION_RULES.md до любого запуска парсеров.
- DATASET_SHA256.txt: хэши набора, каталога, справочника и правил.

Проверки: make_dataset.py — уникальность id, отсутствие пересечения template_id dev/held-out (assert). Парсеры на наборе ещё НЕ запускались.

Ограничения: тексты написаны моделью и не проверены носителем (kk обязательно). Названия районов официально не подтверждены. Held-out написан тем же автором, что и B2, поэтому разбиение не слепое (см. ANNOTATION_RULES.md).

Следующий шаг: evaluator + B1 (A13 baseline_parse) → B2 на dev → заморозка → один прогон held-out → EXPERIMENT.md.
