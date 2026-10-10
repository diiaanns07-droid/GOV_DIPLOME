# R06 · раунд 14 · handoff

Задача: R06 — предложения, голоса жителей, этапы и отставание объектов (prompts/R06.txt).
Агент / город: Claude Code (облачная сессия), Астана, Birge.
Статус: partial (checkpoint 1)
Рабочая ветка: claude/round-14-r06 (отдельная ветка: claude/round-14-package уже ведёт сессия R11; разрешено пользователем)
Основа: origin/claude/round-14-package @ 608e367. Восстановлено: ui/civic_store/ из claude/elegant-franklin-jbhprq @ 26793c8.
Назначенные пути: ui/civic_store/, web/civic/proposals/, tests/civic/R06/, research/round-14-results/R06/, этот файл.

## Сделано
- [x] Восстановлен ui/civic_store (R02 раунда 13, 247 тестов) → регрессия перенесена в tests/civic/R06/store/.
- [x] Миграция 6: civic_object_stages, civic_stage_history (append-only), civic_proposals, civic_proposal_history,
      civic_votes (хэш device_id с солью), civic_v2_settings. Старые таблицы не меняются; этап выводится из status.
- [x] stages.py: delay_days, late, stale (>14 дней), район по полигонам OSM (districts.py), lagging() для R08.
- [x] proposals.py: создание (акимат), голос ±1 (один с устройства, повтор меняет голос), approve/reject/withdraw.
- [x] v2.py: CivicV2.handle() для /api/civic/v2/{objects,proposals,meta} + функции для R08.
- [x] tests/civic/R06/round14/test_r06r14_stages.py (27), весь tests/civic/R06: 406 passed, 1 skipped.
- [ ] Тесты голосов/предложений (следующий шаг)
- [ ] web/civic/proposals/ (карточки), INTEGRATION (patch редактора R12, маршруты R01), DELIVERY, скриншоты.
