# R01 — раунд 14 (Birge): интегратор · handoff

Роль: R01 Интегратор. Аккаунт b1 (s10), продолжение — b12 (s4).
Ветка R01: **`claude/sharp-dijkstra-0t87gl`** (записана координатором в research/round-14/BRANCHES.md).
База: `claude/round-14-package` (влита до d2a4351). Обновлено: 2026-10-10, вечер (UTC).
Свои пути: web/index.html, web/style.css, web/map.js, web/interface.js, web/civic/shell/, ui/web_server.py,
tests/civic/R01/; результаты research/round-14-results/R01/; этот файл.

## Текущая сборка
| Что | SHA | Проверки |
|---|---|---|
| **I0** (модули раунда 13 + их патчи) | `3adabe3` | pytest 1384/12 skip/0 fail; браузер P0 59/0/2 NOT_RUN, сценарии 16/0, город 81/0, пустой реестр 15/0 |
| API v2 | `caf2cff` | pytest 1446/11 skip/0 fail; test_r01_api_v2.py 61/61 |
| шапка Birge | `d27116c` | r14_shell 28/0; найдено: 768 px прокрутка, smoke сценариев на телефоне — исправлено в 2eaeacb |
| R11 ui-kit/i18n | `022787b` | tests/civic/R11 12/12 |
| перевод оболочки ru/kk, шапка < 1024 px | `2eaeacb` | см. «Checkpoint 5» |
| база пакета d2a4351 (LOCAL-1, LOCAL-2, R02 887ef4b) | `3bf631f` | только данные/vendor/R02 — код R01 не менялся |

## Сделано (10 окт)
1. **I0**: модули раунда 13 перенесены по путям с закреплённых SHA (CONTRACT §1), без merge; ветки R06/R07/R09 от
   старого main проверены побитно против их патчей. INTEGRATION-патчи: 2 как есть, 5 перенесены вручную, 4 устарели.
   Подробно — research/round-14-results/R01/BUILD_LOG.md.
2. **API v2** (ui/web_server.py, класс CivicV2Gateway): 14 маршрутов CONTRACT §7 + GET /api/civic/v2/modules. Нет модуля
   или функции — 503 {"error":"module_not_ready","module","role"}; приложение и v1 работают. Параметры проверяются до
   вызова; PUT только в v2; маршруты сотрудника — сессия R02. Какие имена функций ищет шлюз — INTEGRATION.txt §1.
3. **Оболочка Birge** (web/civic/shell/birge.js, birge.css, shell-text.js): шапка Birge, «Карта | Картина дня»,
   «Акимат | Житель», «ҚАЗ | РУС» (выбор запоминается); ниже 1024 px — ≡ Меню. «Картина дня» (#day) монтирует
   window.BirgeAkim (R08) или показывает «скоро появится» + «Вернуться к карте». Вид «Житель» скрывает инструменты
   акимата. «Школы» и «Учебная модель» убраны из меню (код цел; ссылки #school / #training).
4. **ҚАЗ/РУС в оболочке**: все тексты shell.js и explore.js — через ключи; словари R11 главнее, запасной текст —
   shell-text.js; районы — ключи R11 district.*; ключи shell.* переданы R11 (INTEGRATION.txt §5).
5. **R11** интегрирован с claude/r14-R11 @ ba8758b (ui-kit, шрифт Inter локально, i18n, тесты).
6. Документы: BUILD_LOG.md, INTEGRATION.txt, RUN.txt, DEMO_SCRIPT.md, DELIVERY.json.

## Checkpoint 5 — перевод оболочки (2eaeacb)
- r14_shell 35/0 (1366, 768, 375; ru и kk: шапка, панель, навигация, «Картина дня», меню, клавиатура, #training);
  r12_city 81/0; explore unit 5/5. Полный run_checks на 2eaeacb — см. BUILD_LOG.md (последний раздел).

## Известные проблемы
- Модуль карты (R12, код R03 f0a52f7): иногда предупреждение «Image civic-r03-demo-ring could not be loaded» после смены
  стиля (1 раз в прогоне P0 на d27116c; на I0 не было). Владелец — R12; тест выделяет его отдельной строкой.
- Подложка OpenFreeMap в облаке недоступна (упрощённый фон) — на ноутбуке с интернетом проверить LOCAL-7.
- Тексты скрываемых модулей (сравнение ограничений, помощник) не переведены — решение: скрыть их из Birge к B1.

## Следующий шаг (для b12 или следующей сессии)
1. Правая панель 400 px по UX_SPEC §1 (сейчас панель слева 420 px) — shell.css; проверить r12_city (раскладка) и P0.
2. Скрыть «Сравнить ограничения» и помощника из интерфейса Birge (код и API v1 остаются); поправить P0/сценарии.
3. Ежедневно: забирать поставки ролей с DELIVERY.json (сейчас есть только у R11 — новая голова 3890314),
   переносить пути с закреплённого SHA, подключать функции v2 (таблица V2_HANDLERS), прогонять run_checks.sh.
4. B1 — вечер 13 окт, B2 — вечер 14 окт, FINAL — 15 окт 18:00 (составы и проверки — в BUILD_LOG.md).

## Невключённые поставки (на 10 окт, вечер)
R02 claude/r14-R02, R05 claude/r14-R05, R06 claude/round-14-r06, R07 claude/upbeat-knuth-i0rqaa, R08 claude/r14-R08,
R09 claude/modest-shannon-0ki93p, R12 claude/tender-brahmagupta-ef5ztl — только checkpoint'ы, DELIVERY.json ещё нет.
Замечание координатору: в claude/r14-R08 и в базе пакета лежит коммит R02 887ef4b (web/labeling) — по BRANCHES.md это ожидаемо.
