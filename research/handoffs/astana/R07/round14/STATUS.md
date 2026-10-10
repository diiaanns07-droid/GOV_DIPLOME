Задача: Раунд 14 · R07 · Тепловая карта объектов — главный экран акимата
Агент: Claude Code (облачная сессия) · Астана · Birge
Обновлено: 2026-10-10 (день 3: исправления по UX_REVIEW R11 и запросы соседей, для сборки B2)
Статус: ready_for_review (замечания R11 дня 3 для R07 исправлены и проверены; ждёт сборки B2 у R01)
Ветка: claude/upbeat-knuth-i0rqaa · основа af77b78 (claude/round-14-package) · код 9bc25e6 (сервер) + 306074b (интерфейс)
Входные данные: data/civic/astana/osm-objects/ (LOCAL-1) из claude/round-14-package @ bdf12c8, без изменений
Пути: ui/civic_heat/, web/civic/heat/, tests/civic/R07/, research/round-14-results/R07/

Примечание: в начале сессии по ошибке выполнялась роль R11. Её черновики сохранены в коммитах
9cf80fc (UX_SPEC.md) и 0cf32c5 (ui-kit, i18n.js) и удалены из головы ветки (bcb3b6b).
Сессия R11 может взять их: git checkout 0cf32c5 -- web/civic/ui-kit web/civic/i18n; git show 9cf80fc:research/round-14-results/R11/UX_SPEC.md

Цель и критерий: акимат видит, ЧТО краснеет (объект / участок улицы / квартал), с числом людей; пульс и плавный цвет при
новой жалобе, остывание со временем, зелёное «исправлено» 7 дней; фильтры, легенда, карточка цели; 1366 и 375 px, ru и kk.

Что сделано:
- ui/civic_heat/: config (всё из categories_v2.json), engine (вес 0.5^(дни/14) × (1+metoo), уровни, «исправлено», районы),
  service (кэш с invalidate, top/districts/target для R08), api.handle_get (CONTRACT §7: /heat, /heat/meta, /heat/target),
  targets (форма цели: реестр → R12 → реальные объекты LOCAL-1 → ребро графа OSM → ячейка 150 м → «примерное место»),
  osm_objects (3463 реальные цели, из них 974 остановки: остановки, площадки, дворы ЖК, мусор…; id osm-node-…/osm-way-…/yard-…),
  build_fixtures (цели демо из OSM + подписи безымянных объектов), demo_seed (483 синтетические жалобы, 54 цели), devserver (только демо).
- Демо-цели теперь реальные объекты Нуры: остановки «Хан Шатыр», «Центр материнства и детства» и др., дворы ЖК «Evolution»,
  «Алматау», «Zam-Zam» и др., 2 детские и 2 контейнерные площадки; участки улиц — рёбра графа OSM.
- Исправлено: центр многоугольника считался с потерей точности — значок уезжал на 60–100 м от мелких площадок (тест добавлен).
- web/civic/heat/: heat.js (window.CivicHeat.mount; контуры площадок, подписи типов объектов), heat.css, demo.html.
- Проверки дня 2 (5a97636): pytest R07 97 PASS; весь tests/civic 780 PASS; браузер 16 PASS; патч ui/web_server.py проверен на настоящем сервере (откат сделан).
- Скриншоты: research/round-14-results/R07/screens/.

День 3 (UX_REVIEW R11, claude/r14-R11 @ f025241) — подробно в research/round-14-results/R07/UX_FIXES_DAY3.md:
- № 1 белый текст главных кнопок (6,5:1); № 2 на масштабе 12–15 нет точек без числа; № 3 легенда на карте;
  № 4 «Что пишут жители» — группы текстов, настоящие только сотруднику (staff=True от шлюза), жителю раздела нет;
  № 5 телефон: карта один раз подгоняется под горячие места с отступами шапки/шторки; № 6 нажатие ≥ 48 px;
  № 7 «Пример жалобы» вместо «(демо)»; № 8 честный пустой фильтр; № 9 правдоподобный демо-поток (seed 20261014,
  числа R08 в норме); № 12 #target=kind:id&days=N и focusTarget(…, {days}).
- Запросы соседей закрыты: R08 records()/generation; R01/R09 ячейки по точке жалобы; ключ birge.device + X-Birge-Device;
  birge:lang на document; R09 metoo_times и duplicate_of; R12 point/polygon; R10 B-007 (ж/д платформы не остановки);
  словарь heat.* сверен с R11.
- Проверки на 306074b: pytest R07 108 passed / 3 skipped; tests/civic 791 passed / 6 skipped; браузер 29/29 PASS
  (screens/CHECKS.json); настоящий ui/web_server.py с временным патчем — PASS (откат сделан).
- Не закрыто (не в путях R07): переключение вкладки «Картина дня» → карта в оболочке R01; «түзетілді» / «жөнделді».

Файлы передачи: research/round-14-results/R07/DELIVERY.json, RUN.txt, INTEGRATION.txt, UX_FIXES_DAY3.md.

Не запускалось: настоящая подложка OpenFreeMap (403 в облаке → LOCAL-7); живые данные R09 v2 и цели R12 (модулей нет в ветке);
проверка чисел кодом R08 в pytest пропускается (R08 нет в ветке) — сделана отдельно tune_demo_seed.py с копией R08 @ a4189ba.

Следующий шаг:
1. R01 (B2) — взять эту ветку; INTEGRATION §1: маршрут /heat* (staff=True только после проверки входа), configure(source,
   metoo_times) от R09, mount с fitPadding/avoidRects/hash/handleOpenTarget, вкладка карты по birge:open-target.
   Адаптеры сетки ячеек, ключа устройства и birge:lang больше не нужны.
2. R08 — svc.records() / generation. 3. R12 — те же id целей (osm-node-…, yard-…). 4. LOCAL-7 — скриншоты с настоящей подложкой.
5. Владелец — 83 казахских ключа (таблица I18N в INTEGRATION.txt) и выбор «түзетілді» / «жөнделді».
Если сессию продолжит другой аккаунт: базовая ветка claude/upbeat-knuth-i0rqaa, всё описано в DELIVERY.json и INTEGRATION.txt.
