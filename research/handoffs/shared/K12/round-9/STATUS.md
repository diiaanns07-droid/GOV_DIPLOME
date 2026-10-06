Задача / идентификатор: round-9 K12 — негативная проверка и границы API (research/round-9/tasks/K12.txt @ 0ab1667)
Агент / город / сфера: K12 / shared (Шымкент и Астана, синтетические входы) / GovTech-прототип city-evidence, city-plan-v2 и city-resilience-v1
Обновлено: 2026-10-06, UTC
Статус: partial (этап 1 из 3 готов)
Рабочая ветка: claude/save-work-handoff-xuav3q
Исходный коммит, от которого началась работа: c7dfafb (конец r8 K12)
Назначенные пути / модуль: research/round-9-results/K12/, эта запись

Цель и проверяемый критерий готовности:
- Публичные evaluate/optimize/создание поиска BUILD отклоняют непроверенный или изменённый вход до тяжёлой работы.
- Корпус устойчивости city-resilience-v1, ограниченный fuzz на настоящем BUILD, поздние результаты UI.
- Маленькие патчи с регрессионными тестами.

Что реально сделано:
- Этап 1. api_guard.cjs на d865dd4: 2 PASS, 20 FAIL (известный repro r8 F1 и расширение CORE_SPEC r9), 9 NOT_RUN (resilience.js нет).
- Патч fixes/build_d865dd4_k12_r9.patch с новым тестом BUILD tests/plan_api_guard.cjs.
  На копии с патчем: api_guard 22 PASS; check_all exit 0; smoke 24/24, plan_smoke 52/52, whatif_smoke 32/32; харнесс K12 r8 PASS.

Файлы результата:
- research/round-9-results/K12/STATUS.md, HANDOFF.md
- research/round-9-results/K12/api_guard.cjs, adapters/*.cjs
- research/round-9-results/K12/fixes/build_d865dd4_k12_r9.patch, fixes/r9/tests/plan_api_guard.cjs
- research/round-9-results/K12/results/stage1_*, manifests/d865dd4_extract.json

Проверки:
- node api_guard.cjs --app-root <копия d865dd4> → FAIL (ожидаемо, дефект r8); на копии с патчем → PASS.
- Не запускалось:
  - интеграция city-resilience-v1 — NOT_RUN: нового BUILD нет;
  - Windows — NOT_RUN.

Доказательства и ограничения:
- Все сценарии синтетические: условные единицы, веса — приоритеты, не население. Это не городская статистика.
- Через UI и импорт находки недостижимы; это контракт прямого API, а не удалённая атака.

Незавершённое:
- Этап 2: корпус устойчивости и атомарность.
- Этап 3: fuzz, UI и финальный handoff.

Следующий конкретный шаг:
1. Этап 2 по research/round-9-results/K12/HANDOFF.md.

Для воспроизведения:
- research/round-9-results/K12/HANDOFF.md — команды, версии Node 22.22.0, Python 3.11.15, Playwright 1.56.1; секретов нет.

Известные конфликты и зависимости от других агентов:
- BUILD (claude/beautiful-clarke-sbzomj) решает, применять ли патч.
- Модуль resilience.js ещё не опубликован.
