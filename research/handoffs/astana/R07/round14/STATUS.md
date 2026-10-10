Задача: Раунд 14 · R07 · Тепловая карта объектов
Агент: Claude Code (облачная сессия) · Астана · Birge
Обновлено: 2026-10-10 13:35 UTC (checkpoint 1)
Статус: partial
Ветка: claude/upbeat-knuth-i0rqaa · основа af77b78 (claude/round-14-package)
Пути: ui/civic_heat/, web/civic/heat/, tests/civic/R07/, research/round-14-results/R07/

Примечание: в начале сессии по ошибке выполнялась роль R11. Её черновики сохранены в коммитах
9cf80fc (UX_SPEC.md) и 0cf32c5 (ui-kit, i18n.js) и удалены из головы ветки (bcb3b6b).
Сессия R11 может взять их: git checkout 0cf32c5 -- web/civic/ui-kit web/civic/i18n; git show 9cf80fc:research/round-14-results/R11/UX_SPEC.md

Сделано: ui/civic_heat/ — config (из categories_v2.json), geo, targets (форма цели), engine (вес/уровень/исправлено/районы), service (кэш, API-функции).
Дальше: demo_seed + фикстуры целей из графа OSM, api.py, тесты, web/civic/heat/, скриншоты, DELIVERY.
