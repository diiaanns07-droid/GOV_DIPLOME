# R01 — раунд 14 (Birge): интегратор

Роль: R01 Интегратор. Аккаунт b1 (s10), продолжение — b12 (s4).
Ветка: `claude/sharp-dijkstra-0t87gl` (ветка сессии). База: `claude/round-14-package` @ af77b78.
Свои пути: web/index.html, web/style.css, web/map.js, web/interface.js, web/civic/shell/, ui/web_server.py,
tests/civic/R01/; результаты research/round-14-results/R01/; этот файл.

## Checkpoint 1 — PARTIAL: перенос модулей раунда 13 (без патчей)
- DONE: перенесены пути с закреплённых SHA CONTRACT §1 (path-scoped `git checkout <sha> -- <пути>`, без merge).
  Таблица — research/round-14-results/R01/BUILD_LOG.md.
- Проверено: у R06/R07/R09 (ветки от старого main) пути побитно равны `56538a3 + их *_vs_56538a3.patch`.

## Checkpoint 2 — DONE: база I0
- **I0 = `3adabe3`** (push OK). Другие роли могут сверяться с ним.
- Патчи раунда 13 перенесены (2 как есть, 5 вручную, 4 устарели) — BUILD_LOG.md, раздел «шаг 2».
- Проверки на I0: pytest 1384 passed / 12 skipped / 0 failed; браузер P0 59/0/2 NOT_RUN, сценарии 16/0,
  город 81/0, пустой реестр 15/0; node-наборы PASS.
- Договор функций API v2 для ролей — research/round-14-results/R01/INTEGRATION.txt (§1).

## Важно про ветку
Сессия R01 запущена до правила «claude/r14-<роль>» (пакет 7ff639a). Инструкция этой сессии — работать и пушить
только в `claude/sharp-dijkstra-0t87gl`. Поэтому ветка R01 сейчас — `claude/sharp-dijkstra-0t87gl`; зеркало в
`claude/r14-R01` — только по разрешению владельца.


## Checkpoint 3 — DONE: каркас API v2
- Влита обновлённая база пакета 7ff639a (правила веток, ui-kit/i18n R11 v1 608e367).
- ui/web_server.py: все 14 маршрутов /api/civic/v2/* (CONTRACT §7) + GET /api/civic/v2/modules. Нет модуля/функции —
  503 {"error":"module_not_ready","module","role"}; приложение и v1 работают. Параметры проверяются до вызова
  (координаты в Астане, категория из categories_v2.json, голос ±1…). PUT — только в v2. Маршруты сотрудника — сессия R02.
- tests/civic/R01/test_r01_api_v2.py — 61 проверка (без модулей, с подставными модулями, ошибки модулей, staff, HTTP).
- Живой запуск app.py :8611 — v2 отвечает 503 с ролью; главная 200.
- pytest на caf2cff: 1446 passed / 11 skipped / 0 failed.

## Checkpoint 4 — DONE: оболочка Birge
- web/civic/shell/birge.js + birge.css: шапка Birge, «Карта | Картина дня», «Акимат | Житель», «ҚАЗ | РУС».
  Язык — BirgeI18n R11 (ключи common.nav.*, common.role.*, common.lang.*); ключей shell.* у R11 ещё нет —
  запасной текст в birge.js, ключи переданы R11 (INTEGRATION.txt §5). Выбор языка и вида запоминается.
- Телефон: [логотип] [≡ Меню] [ҚАЗ|РУС]; разделы и вид — в выпадающем меню (UX_SPEC §1).
- «Картина дня» (#day): модуль R08 (window.BirgeAkim.mount) или понятное «скоро появится» с кнопкой «Вернуться к карте».
- Вид «Житель» скрывает инструменты акимата («Сравнить ограничения», «Сообщения жителей»), вход сотрудника остаётся.
- «Школы» и «Учебная модель» убраны из меню карты (код цел, открываются ссылкой #school / #training; «Город» возвращает).
  Сохранённый старый режим больше не открывается при запуске.
- ui-kit R11 (tokens.css, components.css, icons.svg) и i18n (i18n.js, ru/kk.json) подключены в index.html и белом списке сервера.
- tests/civic/R01/browser/r14_shell.cjs — 28 PASS / 0 FAIL (1366 и 375, ru и kk); добавлен в run_checks.sh;
  p0_flow и r12_city переведены на ссылки #training/#school.
