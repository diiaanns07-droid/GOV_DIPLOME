Задача: Раунд 14 · R08 · «Картина дня» для акима
Агент: Claude Code (облачная сессия) · Астана · Birge
Обновлено: 2026-10-10 (checkpoint 2)
Статус: partial
Ветка: claude/r14-R08 · основа claude/round-14-package @ 2131c15
Пути: ui/civic_akim/, web/civic/akim/, tests/civic/R08/, research/round-14-results/R08/

Сделано:
- ui/civic_akim/: summary(date, district) — KPI (новые за день/7 дней с изменением, в работе, ждут ответа,
  просрочено по таблице сроков deadlines.py, исправлено за неделю), топ-10 горячих мест, темы, районы и
  главная проблема — из HeatService R07 (ровно ответ /heat за 7 дней), «неделю назад» — расчёт R07 по снимку
  записей на тот момент; объекты и предложения — функция R06 или фикстуры fixtures/*.json (demo).
- text.py: сводка ru/kk по шаблону (склонения, «1 666», «40 %»), api.py: GET /api/civic/v2/akim/summary.
- tests/civic/R08: summary 37, text 47, api 5, heat_match 11 — все PASS (heat_match с копией R07).
- web/civic/akim/: страница «Картина дня» (index.html, akim.js, akim.css, akim.i18n.json); демо-сервер tests/civic/R08/demo_server.py.
- Для проверки в рабочей папке лежит ВРЕМЕННАЯ копия ui/civic_heat (R07 @ c3c9777), в git не добавлена
  (.git/info/exclude). Следующая сессия: git archive origin/claude/upbeat-knuth-i0rqaa ui/civic_heat | tar -x

Дальше: ui_check.cjs (состояния, 375/1366, ru/kk, печать, клавиатура), скриншоты, DELIVERY.json, RUN.txt, INTEGRATION.txt.
