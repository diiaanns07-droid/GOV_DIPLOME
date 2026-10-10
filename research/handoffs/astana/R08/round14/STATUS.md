Задача: Раунд 14 · R08 · «Картина дня» для акима
Агент: Claude Code (облачная сессия) · Астана · Birge
Обновлено: 2026-10-10 (checkpoint 1)
Статус: partial
Ветка: claude/r14-R08 · основа claude/round-14-package @ 2131c15
Пути: ui/civic_akim/, web/civic/akim/, tests/civic/R08/, research/round-14-results/R08/

Сделано:
- ui/civic_akim/: summary(date, district) — KPI (новые за день/7 дней с изменением, в работе, ждут ответа,
  просрочено по таблице сроков deadlines.py, исправлено за неделю), топ-10 горячих мест, темы, районы и
  главная проблема — из HeatService R07 (ровно ответ /heat за 7 дней), «неделю назад» — расчёт R07 по снимку
  записей на тот момент; объекты и предложения — функция R06 или фикстуры fixtures/*.json (demo).
- text.py: сводка ru/kk по шаблону (склонения, «1 666», «40 %»), api.py: GET /api/civic/v2/akim/summary.
- tests/civic/R08/test_r08_summary.py — 37 PASS.
- Для проверки в рабочей папке лежит ВРЕМЕННАЯ копия ui/civic_heat (R07 @ c3c9777), в git не добавлена
  (.git/info/exclude). Следующая сессия: git archive origin/claude/upbeat-knuth-i0rqaa ui/civic_heat | tar -x

Дальше: тесты текста и API, тест совпадения с картой (test_r08_heat_match.py), web/civic/akim/,
скриншоты 1366/375 ru/kk, DELIVERY.json, RUN.txt, INTEGRATION.txt.
