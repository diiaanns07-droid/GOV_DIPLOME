# R09 round 14 — STATUS (жалоба жителя v2)

Роль: R09 · Ветка: claude/modest-shannon-0ki93p · База: claude/round-14-package @ c75a9ac
Восстановлено: ui/civic_feedback, web/civic/feedback из claude/focused-hypatia-z8h0no @ 933cd90 (побайтно; v1 не менялся).
Код (до перехода на OSM): cca386e (= code_sha/tested_sha в DELIVERY.json). Статус: основной объём дня 1 готов; ждём соседей.

## Сделано и проверено
- Бэкенд ui/civic_feedback/v2: запись §5 (+ code B-0001, due_at), цель всегда есть (иначе ячейка «примерное место»),
  язык ru/kk/mixed, «Я тоже» одно на устройство (никогда не создаёт запись; на дубль — засчитывается исходной),
  статусы с историей и защитой от одновременной правки, duplicate_of с переносом людей без двойного счёта,
  сроки ответа по 12 категориям, просрочки, события created/metoo/status/duplicate, metoo_times для веса R07,
  миграция v1 -> v2 без потерь (legacy целиком, идемпотентно), HTTP /api/civic/v2 (11 маршрутов), CLI.
- Фронтенд web/civic/feedback: complaint.js (мастер 5 шагов + «Мои обращения» + адаптер MapLibre),
  complaint.css, kit-fallback.css (временно до ui-kit R11), complaint-strings.js (81 ключ ru/kk),
  categories_v2.js (генерируется из categories_v2.json).
- Тесты: pytest R09 v2 — 72 PASS; tests/civic/R09 — 194 PASS; Chromium-путь — 66/66 (трижды подряд + на cca386e).
- tests/civic целиком: 802 PASS, 3 FAIL — устаревшие тесты v1 раунда 12 в tests/civic/R06 (их версии 933cd90: 210 PASS).

## Для соседей — research/round-14-results/R09/INTEGRATION.txt
R01 — маршруты и подключение фронтенда; R07 — событие birge:complaint и /complaints/events; R08 — overdue();
R12 — формат /targets и находка про соседние рёбра; R04 — /classify, /similar; R11 — I18N_KEYS.md, UX-замечание к §6.4.

## Дальше (следующей сессии R09)
1. Когда появятся R12 /targets, R04 /classify,/similar — прогнать стенд без FIXTURE (флаги serve_r09.py) и пару тестов.
2. Когда R11 выложит ui-kit и i18n — убрать kit-fallback.css из стенда, сверить классы/иконки, принять правки kk.
3. По патчу R01 — проверить путь в настоящем приложении (index.html), скриншоты 375/1366.
4. Если владелец утвердит сроки ответа — обновить RESPONSE_DAYS и пересобрать categories_v2.js.

## Обновление: реальные объекты OSM (LOCAL-1)
- data/civic/astana/osm-objects взят из claude/round-14-package @ bdf12c8 без изменений (только чтение).
- Стенд: /targets предлагает реальные остановки, площадки, спортплощадки, парки, скверы, дворы (yard-<id>), школы,
  детсады, мусорные площадки + участки улиц; демо-цель «7 человек» — реальная остановка («Бухар жырау»).
- Модуль: при одинаковых подписях кандидатов всегда показывается расстояние.
- Код: da295be; pytest R09 v2 77 PASS, tests/civic/R09 199 PASS, Chromium 69/69.

## Обновление: ранний UX-разбор R11 (день 2), строки 1–6 — исправлено
Код a4ab5a4. Отчёт: research/round-14-results/R09/R11_REVIEW_FIXES.md (что было → исправление → проверка).
- 1 слой пунктира отдельно; 2 цель 11 px / нажатие 6 px (coalesce); 3 «Отправить» активна после /classify;
  4 «Это здесь?» без названия в вопросе; 5 сетка .bk-catgrid ui-kit (2 колонки на 375, слова не рвутся); 6 одна галочка.
- Проверки: pytest test_r11_1…6 (падают на 32566a0, на 4021818 — ровно 2/5/6); Chromium [R11-1…6].
- Стенд --r11 <папка>: настоящий ui-kit и i18n R11 (cc77761) — 105/105, как и без него.
- pytest R09 v2 83 PASS, tests/civic/R09 205 PASS. Скриншоты: screens/ и screens-r11ui/ (375/1366, ru/kk).
Дальше: строки 7–12 разбора R11 и точки прогресса .bk-wizard с ui-kit.
