# R02 раунд 13 — импорт, источники и сохранность истории

Статус: PARTIAL (checkpoint 3)
Ветка: claude/elegant-franklin-jbhprq, продолжение поставки 9366217 (код раунда 12 bd7a911).
База сравнения: 56538a3. Поставка R05: ca0f06f8245e24adcae751acea321d19d9366576.

Сделано:
- Старые исправления воспроизведены: tests/civic/R02 — 233 passed, 1 skipped до изменений раунда 13.
- Настоящий пакет R05 (копии без изменений в tests/civic/R02/fixtures/r05_ca0f06f/, sha256 в PROVENANCE.txt):
  package и historical — 0 записей; dry-run, импорт и повтор дают 0 объектов, summary.note «Пакет пуст».
  candidates.json не импортируется (не формат civic-v1).
  Настоящих подтверждённых записей проверено: 0. Это НЕ загрузка городского реестра.
- Отчёт импорта: summary (items/valid/invalid/new_drafts/.../published_by_import=0/evidence_types),
  предупреждения по записи: end_date_passed, end_date_unknown, field_has_several_sources,
  observed_source_not_fetched. Ничего не исправляется автоматически.
- Synthetic fixture (demo-срез, 2 записи) — отдельно: только черновики, остаются synthetic.

- Миграция 5: след решения по кандидату (resolution_reason, resolution_fields_json, resolved_revision).
- GET /staff/objects/{id}/import-candidates: прежние ключи сохранены; добавлены review.fields
  (current/proposed/previous_import, changed_by_source/editor, conflict, proposed_sources/current_sources),
  review.locked_fields, decision{by,reason,accepted_fields,resulting_revision}, pending.
- POST .../apply принимает необязательный fields — частичное принятие (partially_applied);
  отклонённые поля не предлагаются повторно тем же пакетом. Неверный список/недопустимый результат — 422 без записи.
- Новая версия источника заменяет нерассмотренную (superseded) -> форма на старой версии получает 409;
  возврат источника к заменённой версии снова делает её актуальной.
- Два редактора на одном кандидате: один 200, второй 409; история непрерывна.
- Приёмка create draft -> publish -> changed source -> review -> accepted update -> publish -> 409,
  проверено после перезапуска сервиса на том же файле (test_r02_round13_review.py).
Проверки: tests/civic — 769 passed, 2 skipped.

- Полный служебный backup отдельно от публичной выгрузки: новая команда verify-backup SRC (только чтение:
  integrity, миграции, счётчики; рабочая база не трогается). backup -> verify -> restore в новое место сохраняет
  служебную историю и кандидатов; export-public того же состояния не содержит служебного.
- /staff/meta (meta_version 2): каталог всех кодов ошибок (тест сверяет с исходником), правила причин,
  locked_after_first_publication, контракт кандидатов, предупреждения импорта.
- 409 кандидата различимы: candidate_superseded / candidate_resolved (статус 409 как раньше).
- research/round-13-results/R02/fixtures-r04/: настоящие ответы сервиса (временная БД, тестовое содержимое),
  генератор tools/make_r04_fixtures.py. Без cookie/CSRF/паролей.
Проверки: tests/civic/R02 — 247 passed, 1 skipped.

Следующий шаг: patch маршрутов шлюза для R01 с проверкой в отдельном worktree, передача.
