# R09 round 14 — STATUS (жалоба жителя v2)

Роль: R09 · Ветка: claude/modest-shannon-0ki93p · База: claude/round-14-package @ c75a9ac
Восстановлено: ui/civic_feedback, web/civic/feedback из claude/focused-hypatia-z8h0no @ 933cd90 (побайтно; v1 не менялся).
Код: cca386e (= code_sha/tested_sha в DELIVERY.json). Статус: основной объём дня 1 готов; ждём соседей.

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
