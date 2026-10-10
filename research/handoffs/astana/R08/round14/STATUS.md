Задача: Раунд 14 · R08 · «Картина дня» для акима
Агент: Claude Code (облачная сессия) · Астана · Birge
Обновлено: 2026-10-10 (поставка 1)
Статус: done (поставка 1) — ждёт подключения у R01 и функций R06
Ветка: claude/r14-R08 · основа claude/round-14-package @ 2131c15 · код 9f1d9c0
Пути: ui/civic_akim/, web/civic/akim/, tests/civic/R08/, research/round-14-results/R08/

Сделано (все 4 задачи prompt R08):
1. ui/civic_akim/ — summary(date, district): новые за день (сравнение с тем же отрезком неделю назад) и за 7 дней,
   в работе + ждут ответа, просрочено (deadlines.py: снег 2 дня, ямы 7 дней… — демо-норматив), исправлено за неделю;
   статус «на момент» восстанавливается по status_history (прошлые даты честные). Горячие места (топ-10), темы,
   районы, главная проблема — ровно HeatService R07 за 7 дней; «неделю назад» — расчёт R07 по снимку записей.
   Объекты с отставанием/устаревшие и предложения — функции R06 (ищутся по именам) или фикстуры (demo).
   API: api.handle_get → GET /api/civic/v2/akim/summary. CLI: python -m ui.civic_akim [--district nura --lang kk].
2. text.py — сводка ru/kk по шаблону, без LLM: склонения, «1 666», «40 %», «в 2,5 раза»; главная фраза — role "main".
3. web/civic/akim/ — страница: 4 числа со стрелкой и словом, сводка (главная проблема жирным), горячие места
   (клик → birge:open-target / ссылка /#target=<kind>:<id>&days=7), темы и районы полосами (клик по району —
   фильтр), объекты, предложения; дата и район в адресе; ҚАЗ/РУС; печать — 2 листа A4.
4. Состояния: загрузка (скелетон), пусто, нет связи → «Повторить», ошибка 500, дата в будущем, карта не отвечает,
   жалобы не подключены (вместо выдуманных нулей).

Проверки (среда: облако, Python 3.13, Node 22, Playwright 1.56 + Chromium):
- pytest tests/civic/R08: 112 PASS (summary 38, text 58, api 5, heat_match 11 — с копией R07 @ c3c9777);
  без ui/civic_heat: 100 PASS + 1 SKIP с причиной.
- node tests/civic/R08/ui_check.cjs: 77/77 PASS, скриншоты research/round-14-results/R08/screens/
  (1366 и 375, ru и kk, состояния, печать PDF).
- NOT_RUN: подключение в ui/web_server.py (делает R01), открытие цели картой (R01/R07).

Важно для следующей сессии:
- ui/civic_heat в рабочей папке — ВРЕМЕННАЯ копия R07 (в git не добавлена, .git/info/exclude). Получить заново:
    git fetch origin claude/upbeat-knuth-i0rqaa && git archive origin/claude/upbeat-knuth-i0rqaa ui/civic_heat | tar -x
- Демо-сервер: python tests/civic/R08/demo_server.py → http://127.0.0.1:8508/civic/akim/
- Как подключить и что просим у соседей — research/round-14-results/R08/INTEGRATION.txt (R01 маршрут и файлы,
  R07 публичные records()/generation, R06 akim_objects/akim_proposals, R11 31 новый ключ + kk на проверку).

Следующий шаг:
- Когда R06 отдаст функции — убрать фикстуры из показа (подхватятся сами), прогнать tests/civic/R08.
- Когда R01 соберёт B1 — прогнать ui_check.cjs на общем сервере: node tests/civic/R08/ui_check.cjs http://127.0.0.1:8501
  (адрес страницы /civic/akim/), проверить переход «горячее место → карточка цели» вживую.
- Если R07 изменит heat() — test_r08_heat_match.py покажет расхождение; чинить в ui/civic_akim/summary.py (_heat_part).
