Задача / идентификатор: round-9 · K07 · «Исправление настоящего интерфейса» (research/round-9/tasks/K07.txt @ codex/research-import-2026-10-05 0ab1667)
Агент / город / сфера: K07 / shared (Шымкент и Астана) / интерфейс планировщика BUILD
Обновлено (дата, время, часовой пояс): 2026-10-06, UTC
Статус: partial (этап 1 из 3 готов)
Рабочая ветка: claude/save-work-handoff-ku3ej3
Исходный коммит, от которого началась работа: ab71b735e5300ec4bd1d267b01b9d7b67603e6b0 (K07 r8)
Назначенные пути / модуль: research/round-9-results/K07/, этот файл

Цель и проверяемый критерий готовности:
- Этап 1: воспроизвести K2–K5 на BUILD d865dd4; отдельно оценить N2; подтверждение исправления — только новый SHA BUILD.
- Этап 2: компактный патч панели «Устойчивость к допущениям» к plan-ui.js с клавиатурным путём.
- Этап 3: браузерные тесты настоящей страницы на 390 px и desktop.

Что реально сделано:
- Тесты r8 повторно запущены без изменений на d865dd4 (byte-exact копия, manifest results/build_snapshot_d865dd4.json).
- K2–K5 воспроизведены (FAIL); с патчем r9 на копии — PASS.
- N2 переоценён тестом k07r9_n2_scroll.cjs: данные не теряются, область достижима с клавиатуры (Chromium 141). Это не дефект; добавлены role, имя и tabindex области вместо смены раскладки.

Файлы результата (точные пути от корня):
- research/round-9-results/K07/STATUS.md, HANDOFF.md
- research/round-9-results/K07/patch/build_d865dd4_r9_keyboard.patch
- research/round-9-results/K07/tests/k07r9_n2_scroll.cjs
- research/round-9-results/K07/scripts/{extract_build.py, run_r9_review.sh}
- research/round-9-results/K07/results/build_d865dd4/, build_d865dd4+k07r9/, build_snapshot_d865dd4.json

Проверки:
- bash research/round-9-results/K07/scripts/run_r9_review.sh → exit 0.
  - d865dd4: тесты BUILD все PASS; движок r8 211/211; браузер r8 26/31 (FAIL K2–K5, N2-r8); N2 r9 3/3.
  - d865dd4 + патч: тесты BUILD все PASS; 211/211; браузер r8 30/31 (FAIL только N2-r8, заменён r9); N2 r9 3/3.
- Не запускалось: новый SHA BUILD (его нет) — интеграция NOT_RUN; Safari/Firefox; средство чтения экрана; Windows.

Доказательства и ограничения:
- Данные — срез K10 в BUILD d865dd4. Точки, места и стоимости в тестах — SYNTHETIC или демо-набор BUILD.

Незавершённое:
- Этапы 2 и 3.

Следующий конкретный шаг:
1. Этап 2: research/round-9-results/K07/web/resilience_k07.js (адаптер к plan.js) + панель + патч.

Для воспроизведения:
- git fetch origin claude/beautiful-clarke-sbzomj; NODE_PATH="$(npm root -g)" bash research/round-9-results/K07/scripts/run_r9_review.sh

Известные конфликты и зависимости от других агентов:
- Исправления применяет только BUILD.
- Если BUILD выпустит web/resilience.js с API CORE_SPEC, панель K07 использует его вместо адаптера K07.
