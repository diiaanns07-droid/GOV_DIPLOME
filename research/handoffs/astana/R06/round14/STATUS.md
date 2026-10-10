# R06 · раунд 14 · handoff

Задача: R06 — предложения, голоса жителей, этапы и отставание объектов (prompts/R06.txt).
Агент / город: Claude Code (облачная сессия), Астана, Birge.
Статус: DONE по объёму роли (интеграция в общую сборку — за R01/R12/R11, см. INTEGRATION.txt)
Рабочая ветка: claude/round-14-r06 (разрешена пользователем; claude/round-14-package вела сессия R11). Координатору: внести в BRANCHES.md.
Основа: claude/round-14-package @ 608e367; ui/civic_store/ из claude/elegant-franklin-jbhprq @ 26793c8.
Код: 7031afa (проверен). Назначенные пути: ui/civic_store/, web/civic/proposals/, tests/civic/R06/, research/round-14-results/R06/.

## Сделано (по задачам промпта)
1. Этапы: миграция 6 (новые таблицы, старые объекты и история байт в байт; этап из status), stage/planned_end/forecast_end,
   delay_days и stale (>14 дней) считаются сами; тест миграции на данных «раунда 13». ✔
2. Предложения и голоса: civic_proposals (kind из 5 объектов R05), civic_votes (хэш device_id с солью, один голос с
   устройства, повтор меняет голос), approve/reject/withdraw; API CONTRACT §7 (CivicV2.handle + функции для шлюза R01). ✔
3. web/civic/proposals/: карточка проекта («Проект · 2027», крупные «За»/«Против» со счётчиками, «Один голос с устройства»,
   акимат «Одобрить»/«Отклонить»), карточка объекта (6 этапов, «Отстаёт на N дней», «Не обновлялось N дней»). 375/1366, ru/kk. ✔
4. Редактор R12: блок «Этап работ» (stage-editor.js) + patch r12_editor_stage.patch (накладывается на f48e578). ✔
5. «Картина дня» R08: lagging_objects(district), proposals_summary(since). ✔
+ Найдено и исправлено: cookie сессии был только на /api/civic/v1 → действия сотрудника в v2 давали 401.
+ Демо по реальным объектам OSM (LOCAL-1): прежние точки попадали на школу/рядом с существующими площадками.

## Проверки
tests/civic/R06: 445 passed, 5 skipped; через шлюз R01: 4/4; браузер: 48/48 (screens/); R12 с patch = R12 без patch (80/8/1).

## Следующий шаг (для того, кто продолжит R06)
- Ждать применения INTEGRATION §1 (R01) и patch (R12); после сборки прогнать browser_r14.cjs на общей сборке.
- Когда R11 добавит I18N-KEYS R06 — удалить совпавшие ключи из PENDING в proposals.js и stage-editor.js.
- Если R05 пришлёт свой формат placement — расширить proposals.create (поле rotation_deg уже есть).
