Задача / идентификатор: round-9 · K07 · «Исправление настоящего интерфейса» (research/round-9/tasks/K07.txt @ codex/research-import-2026-10-05 0ab1667)
Агент / город / сфера: K07 / shared (Шымкент и Астана) / интерфейс планировщика и панели устойчивости BUILD
Обновлено (дата, время, часовой пояс): 2026-10-06, UTC
Статус: done (этапы 1–3); итоговые прогоны e1cbc3f и d865dd4 — см. STATUS.md
Рабочая ветка: claude/save-work-handoff-ku3ej3
Исходный коммит, от которого началась работа: ab71b735e5300ec4bd1d267b01b9d7b67603e6b0 (K07 r8)
Назначенные пути / модуль: research/round-9-results/K07/, этот файл

Цель и проверяемый критерий готовности:
- Этап 1: воспроизвести K2–K5 на BUILD d865dd4; отдельно оценить N2; подтверждение исправления — только новый SHA BUILD.
- Этап 2: компактный патч панели «Устойчивость к допущениям» с клавиатурным путём.
- Этап 3: браузерные тесты настоящей страницы на 390 px и desktop на явно закреплённом SHA.

Проверенные SHA BUILD (claude/beautiful-clarke-sbzomj):
- вход: d865dd4a124291e10dd0b7bb1d9eada20d34c268;
- промежуточный: e1cbc3fa84518a84698c03d014dc153f71338d54;
- итоговый: d18847f9e7c18fcfae3349c0b223b023d359a838 (prototypes/city-evidence = e82214e).

Что реально сделано:
- K2–K5 воспроизведены на d865dd4 и исправлены BUILD: на d18847f браузер r8 31/31, движок r8 211/211.
- N2 — не дефект (данные не теряются); на d18847f при 390/320 px переполнения нет.
- Панель K07 (этап 2) заменена панелью BUILD.
- Этап 3 на d18847f:
  - resilience.js BUILD = Python-оракул K07, 69/69;
  - панель BUILD в браузере 32/36 — новые дефекты D1 (клик с удержанием 100 мс после ввода теряется) и D2 (сообщение о сайте старого города после быстрой смены города);
  - патч patch/build_d18847f_r9_pointer_flush.patch на копии → 36/36, тесты BUILD 164/164 без регрессий.

Файлы результата (точные пути от корня):
- research/round-9-results/K07/STATUS.md, HANDOFF.md, API.md
- research/round-9-results/K07/patch/build_d18847f_r9_pointer_flush.patch (актуальный)
- research/round-9-results/K07/patch/build_d865dd4_r9_{keyboard,resilience_panel}.patch (история, заменены BUILD)
- research/round-9-results/K07/tests/{k07r9_build_resilience_ui.cjs, build_resilience_crosscheck.cjs, resilience_cases.cjs, oracle_resilience.py, resilience_k07.test.cjs, k07r9_resilience_ui.cjs, k07r9_n2_scroll.cjs}
- research/round-9-results/K07/web/{resilience_k07.js, resilience_panel_k07.js} (предложение этапа 2)
- research/round-9-results/K07/scripts/{extract_build.py, make_patch.py, run_r9_review.sh}
- research/round-9-results/K07/results/build_<sha7>[+k07r9]/, build_snapshot_<sha7>.json

Проверки:
- NODE_PATH="$(npm root -g)" bash research/round-9-results/K07/scripts/run_r9_review.sh d18847f → exit 0:
  - d18847f: тесты BUILD 164 PASS / 0 FAIL; r8 211/211 и 31/31; N2 1/1; адаптер 77/77; движок BUILD 69/69; панель 32/36 (FAIL BR24, BR25, BR21b, BRT2);
  - d18847f + патч K07: то же, панель 36/36.
- Не запускалось (NOT_RUN): tools/check_all.py BUILD (нужно полное дерево); Safari, Firefox, Windows; средство чтения экрана; реальное сенсорное устройство.

Доказательства и ограничения:
- Данные — срез K10 в BUILD. Планы, точки, места и стоимости в тестах — SYNTHETIC; исключение записи — допущение, не закрытие.

Незавершённое:
- Нет (ожидается новый SHA BUILD с D1/D2).

Следующий конкретный шаг:
1. BUILD применяет patch/build_d18847f_r9_pointer_flush.patch и выпускает SHA; K07 или REVIEW запускает run_r9_review.sh <NEW_SHA> (критерий: панель 36/36, тесты BUILD без FAIL).

Для воспроизведения:
- git fetch origin claude/beautiful-clarke-sbzomj; NODE_PATH="$(npm root -g)" bash research/round-9-results/K07/scripts/run_r9_review.sh d18847f

Известные конфликты и зависимости от других агентов:
- prototypes/city-evidence меняет только BUILD; K07 хранит патчи как предложения.
