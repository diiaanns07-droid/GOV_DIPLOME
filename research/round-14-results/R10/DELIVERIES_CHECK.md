# R10 · проверка поставок ролей по отдельности (10 окт, до B1)

Цель: до сборки B1 убедиться, что каждая поставка запускается «как есть» и её PASS воспроизводится не только у автора.
Каждая ветка проверялась в отдельном `git worktree` на её голове (SHA ниже). Код тестов перед запуском просмотрен:
сеть наружу не используется, удаляются только свои временные папки.

Среда: облачный Linux, Python 3.13.16, Node 22.22.0, Playwright 1.56.1 + Chromium headless (программный WebGL),
без интернета (подложка OpenFreeMap недоступна), без torch/GPU.

## 1. Владение путями (CONTRACT §2)

Файлы, изменённые веткой относительно её точки ответвления от `claude/round-14-package`, сверены с таблицей §2
(+ своя папка `research/round-14-results/<R>/` и handoff). Копии LOCAL-данных (`data/civic/astana/osm-objects/`,
`web/vendor/three/`) без изменений считаются допустимыми.

| Роль | Ветка @ голова | Файлов | Вне своих путей |
|---|---|---|---|
| R02 | claude/r14-R02 @ 73b97d2 | 39 | 0 |
| R03 | claude/r14-R03 @ 1d0edd7 | 31 | 0 |
| R04 | claude/r14-R04 @ baee61c | 21 | 0 |
| R05 | claude/r14-R05 @ e533e67 | 61 | 0 (+14 копий LOCAL) |
| R06 | claude/round-14-r06 @ 3d10f7d | 80 | 0 (+14 копий LOCAL) |
| R07 | claude/upbeat-knuth-i0rqaa @ 3eb3f9d | 56 | 0 (+14 копий LOCAL) |
| R08 | claude/r14-R08 @ a4189ba | 40 | 0 |
| R09 | claude/modest-shannon-0ki93p @ e012f73 | 111 | 0 (+14 копий LOCAL) |
| R11 | claude/r14-R11 @ cc77761 | 82 | 0 |
| R12 | claude/tender-brahmagupta-ef5ztl @ 8bb7bf8 | 107 | 0 (+14 копий LOCAL) |
| R13 | claude/r14-R13 @ 754de0c | 8 | 0 |
| R14 | claude/r14-R14 @ fc2fc7a | 1 | 0 |
| R15 | claude/r14-R15 @ 479d948 | 1 | 0 |

Итог: **все роли меняют только свои пути.** R01 (интегратор) переносит чужие пути по закреплённым SHA — так и задумано.

## 2. Тесты ролей, повторённые R10

| Роль | Что запускал | Результат R10 | Заявлено в DELIVERY | Совпадает |
|---|---|---|---|---|
| R02 | — (данные и инструмент разметки; повтор отложен) | NOT_RUN | 89 pytest + 19 node PASS | — |
| R03 | `pytest tests/civic/R03/round14` (без torch/onnx) | **58 PASS, 7 skip** | 58 PASS + 7 NOT_RUN без torch | да |
| R04 | `pytest tests/civic/R04` | NOT_RUN — тестов раунда 14 ещё нет (checkpoint 2, DELIVERY нет) | — | — |
| R04 | прямой вызов `classify`/`similar` (13 фраз ru/kk/транслит) | 12/13 верно в связке с v1+R03; форма ответа §7 верна; см. B-003, B-004 | — | — |
| R05 | `pytest tests/civic/R05` | **157 PASS, 1 skip** | 9/9 своих python | да |
| R05 | `node --test build3d/test_core.mjs test_models.mjs` | **25/25** | 25/25 | да |
| R05 | `node build3d/browser_check.mjs` | **25 PASS, 0 FAIL, 1 NOT_RUN** | 25/0/1 | да |
| R06 | `pytest tests/civic/R06` | **445 PASS, 5 skip** | 445/5 | да |
| R06 | `browser_r14.cjs` на свежем стенде `--age-days 16 --kit-dir <R11 cc77761>` | **48/48** (без `--kit-dir` — падает, B-006) | 48/48 | да |
| R07 | `pytest tests/civic/R07` | **97 PASS, 1 skip** | 97 | да |
| R07 | `devserver` + `browser/shots.js` | **16/16** | 16 | да |
| R08 | `pytest tests/civic/R08` | **101 PASS, 1 skip** | 112 (в RUN.txt) / 38+58+5+11 | да* |
| R08 | `demo_server.py` + `ui_check.cjs` в своей ветке | 9 PASS, **4 FAIL** (нет R07, B-005) | 77/77 | нет |
| R08 | то же в сборке R01 @ bc7c961 | **78/78** | 77/77 | да |
| R09 | `pytest tests/civic/R09` | **205 PASS** | 83 своих v2 | да (+ тесты раунда 13) |
| R09 | `browser_r09.cjs` | **105/105** | 105/105 | да |
| R11 | `pytest tests/civic/R11` | **14 PASS** | 14 | да |
| R11 | `i18n.test.cjs`, `browser_check.cjs` (витрина 1366 ru/kk) | **PASS**, 4/4 | PASS | да |
| R12 | `pytest tests/civic/R12` | **29 PASS** | 29/29 | да |
| R12 | `node --test map/r12_accuracy.test.mjs` | **4/4** | — | да |
| R13 | — | NOT_RUN — нет DELIVERY, тестов в ветке нет (старт 10 окт) | — | — |
| R14, R15 | — | NOT_RUN — только стартовый handoff | — | — |

\* R08: в RUN.txt написано «112 тестов», фактически в ветке 101 + 1 skip (часть тестов R07-совместимости пропускается
без модуля R07). Расхождение — документация.

## 3. Сборка R01 (текущая)

`claude/sharp-dijkstra-0t87gl` @ `bc7c961` («B1 step 1»: перенесены R02, R07, R08, R09 по SHA).
`GET /api/civic/v2/modules`: ready — только `akim.summary` (R08). `heat`, `complaints.*` — module_not_ready (B-002);
`classify`, `similar`, `targets`, `proposals.*`, `objects.*` — модулей ещё нет в сборке (R04, R12, R06 не перенесены).
Сценарий демо — см. `ACCEPTANCE_PRE_B1.md`.

## 4. Проверка самого e2e на настоящем интерфейсе (стенд R09)

Чтобы `tests/e2e/demo_flow.cjs` не подвёл на B1, его шаги 1–2 прогнаны на стенде R09
(`claude/modest-shannon-0ki93p` @ e012f73, `serve_r09.py --seed --r11 <выгрузка R11 cc77761>/web`; `/targets` и
`/classify` там — фикстуры стенда на реальных данных OSM). Точка — остановка «Ботанический сад»
(`osm-node-10677613224`): «Хан Шатыр» лежит севернее области данных стенда (71.395–71.465 × 51.075–51.125).

Результат (`e2e/r09-stand/RESULT.md`): **шаги 1–2 PASS в 1366/375 × ru/kk** — главная кнопка, остановка после нажатия на
карту, «Похоже на: Остановки и транспорт», отправка → «Об этом уже сообщили 2 человека» + «Я тоже».
Остальные шаги на стенде — FAIL/NOT_RUN по понятной причине (нет R07/R08/R06 и входа сотрудника).

Замечания по стенду R09 (в сборке их закрывает R12, поэтому не в BUGS):
- подпись цели берётся из тега OSM `name` → в русском интерфейсе «Остановка «Ботаникалық бақ»», хотя у R12
  `name_ru` = «Ботанический сад»;
- `--r11` ждёт папку `web` выгрузки R11 (с корнем выгрузки стенд остаётся без стилей — 404 на ui-kit).
