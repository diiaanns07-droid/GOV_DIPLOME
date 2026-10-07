# R02 раунд 13 — импорт, источники и сохранность истории

Статус: PARTIAL (checkpoint 1)
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

Следующий шаг: контракт diff для проверки кандидата (поля, источники, частичное принятие) и устаревание кандидатов.
