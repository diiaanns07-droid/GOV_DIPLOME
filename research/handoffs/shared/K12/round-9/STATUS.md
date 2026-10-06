Задача / идентификатор: round-9 K12 — негативная проверка и границы API (research/round-9/tasks/K12.txt @ 0ab1667)
Агент / город / сфера: K12 / shared (Шымкент и Астана, синтетические планы на реальных ID записей) / city-evidence: city-plan-v2 и city-resilience-v1
Обновлено: 2026-10-06, UTC
Статус: ready_for_review (этапы 1–3 готовы)
Рабочая ветка: claude/save-work-handoff-xuav3q
Исходный коммит, от которого началась работа: c7dfafb (конец r8 K12)
Назначенные пути / модуль: research/round-9-results/K12/, эта запись

Цель и проверяемый критерий готовности:
- Публичные API v2 и устойчивости отклоняют непроверенный или изменённый вход до тяжёлой работы.
- Корпус устойчивости и ограниченный fuzz на настоящем BUILD с независимым оракулом.
- Поздние ответы UI не применяются; маленькие патчи с регрессионными тестами.

Что реально сделано:
- Проверены SHA BUILD d865dd4 (закреплён), 33cc635, e1cbc3f и финальный d18847f (код e82214e).
- Финал d18847f:
  - api_guard 33 PASS / 1 FAIL / 1 ADVISORY;
  - корпус 63 PASS / 2 ADVISORY;
  - fuzz устойчивости и v2 PASS;
  - UI 21 PASS / 2 ADVISORY;
  - порядок ID: JS ≠ Python-оракулы BUILD (4 из 4).
- r8 F1 закрыт самим BUILD (e990f01).
- Патч fixes/build_e1cbc3f_k12_r9c.patch (G1–G5) с тестами. На d18847f с патчем:
  - все проверки K12 PASS (35/35, 65/65, 23/23, 4 из 4);
  - BUILD check_all exit 0; браузер smoke 24, plan_smoke 52, whatif_smoke 32, plan_keyboard 16, resilience_smoke 40.

Файлы результата:
- research/round-9-results/K12/STATUS.md, HANDOFF.md, FIX_PROPOSALS.md
- research/round-9-results/K12/api_guard.cjs, resilience_stress.cjs, resilience_fuzz.cjs, id_order_probe.cjs, ui_r9_browser.cjs
- research/round-9-results/K12/make_resilience_fixtures.py, fixtures_rs/, FIXTURES_RS_INDEX.json, oracle/resilience_oracle.py, expected/
- research/round-9-results/K12/adapters/*.cjs, fixes/*.patch, fixes/r9*/tests/*, results/*, manifests/*

Проверки:
- Команды и фактические PASS/FAIL/ADVISORY — в research/round-9-results/K12/HANDOFF.md и STATUS.md.
- Не запускалось:
  - Windows — NOT_RUN;
  - evidence.js rebuild в check_all — SKIP самого BUILD (нет shapely/pyproj);
  - на d865dd4 — группа R (модуля не было).

Доказательства и ограничения:
- Синтетические планы, стоимости и веса; ID записей — настоящие ID среза (data.js sha256 bb2a7e66…). Это не городская статистика.
- Находки G1–G5 касаются прямого API, правил названий и порядка ID в оракулах. Это не удалённая атака: UI и импорт валидируют вход.

Незавершённое:
- Решение BUILD по патчу r9c.
- Решение координатора по CORE_SPEC (порядок ID, политика названий).

Следующий конкретный шаг:
1. BUILD: применить или отклонить fixes/build_e1cbc3f_k12_r9c.patch; затем повторить команды HANDOFF на новом SHA.

Для воспроизведения:
- Node 22.22.0, Python 3.11.15, Playwright 1.56.1 + Chromium; секретов и сети не нужно.

Известные конфликты и зависимости от других агентов:
- BUILD (claude/beautiful-clarke-sbzomj) владеет prototypes/city-evidence; K12 только предлагает патчи.
