Задача: Раунд 14 · R07 · Тепловая карта объектов — главный экран акимата
Агент: Claude Code (облачная сессия) · Астана · Birge
Обновлено: 2026-10-10 13:20 UTC
Статус: ready_for_review (модуль готов на демо-данных; ждёт подключения R01 и живых данных R09/R12)
Ветка: claude/upbeat-knuth-i0rqaa · основа af77b78 (claude/round-14-package) · код 7d500b5
Пути: ui/civic_heat/, web/civic/heat/, tests/civic/R07/, research/round-14-results/R07/

Примечание: в начале сессии по ошибке выполнялась роль R11. Её черновики сохранены в коммитах
9cf80fc (UX_SPEC.md) и 0cf32c5 (ui-kit, i18n.js) и удалены из головы ветки (bcb3b6b).
Сессия R11 может взять их: git checkout 0cf32c5 -- web/civic/ui-kit web/civic/i18n; git show 9cf80fc:research/round-14-results/R11/UX_SPEC.md

Цель и критерий: акимат видит, ЧТО краснеет (объект / участок улицы / квартал), с числом людей; пульс и плавный цвет при
новой жалобе, остывание со временем, зелёное «исправлено» 7 дней; фильтры, легенда, карточка цели; 1366 и 375 px, ru и kk.

Что сделано:
- ui/civic_heat/: config (всё из categories_v2.json), engine (вес 0.5^(дни/14) × (1+metoo), уровни, «исправлено», районы),
  service (кэш с invalidate, top/districts/target для R08), api.handle_get (CONTRACT §7: /heat, /heat/meta, /heat/target),
  targets (форма цели: реестр → R12 → ребро графа OSM → ячейка 150 м → «примерное место»), build_fixtures (цели из OSM),
  demo_seed (125 синтетических жалоб, детерминированно), devserver (только демо).
- web/civic/heat/: heat.js (window.CivicHeat.mount), heat.css, demo.html (офлайн-подложка из улиц OSM).
- Проверки: pytest R07 94 PASS; весь tests/civic 683 PASS; браузер 15 PASS; патч для ui/web_server.py проверен на настоящем сервере.
- Скриншоты: research/round-14-results/R07/screens/.

Файлы передачи: research/round-14-results/R07/DELIVERY.json, RUN.txt, INTEGRATION.txt.

Не запускалось: настоящая подложка OpenFreeMap (403 в облаке → LOCAL-7); живые данные R09 v2 и цели R12 (ещё не поставлены).

Следующий шаг:
1. R01 — INTEGRATION §1 (CIVIC_ASSETS, маршрут, mount в оболочке). 2. R09 — invalidate() + событие birge:complaint (§2).
3. После LOCAL-1 / R12 — python -m ui.civic_heat.build_fixtures (остановки и дворы Нуры), повтор тестов и скриншотов.
4. Владелец — проверить 66 казахских строк (INTEGRATION §6) и выбрать «түзетілді» / «жөнделді».
Если сессию продолжит другой аккаунт: базовая ветка claude/upbeat-knuth-i0rqaa, всё описано в DELIVERY.json и INTEGRATION.txt.
