# R01 — журнал сборки раунда 14

## I0 — шаг 1: перенос путей (без патчей)

База: `claude/round-14-package` @ af77b78 (= c076569 + research/round-14). После 56538a3 база меняла только research/,
поэтому поставки раунда 13, сделанные от 56538a3, совместимы с базой.

| Модуль | Пути | Источник (ветка @ SHA) | Код поставки |
|---|---|---|---|
| оболочка R01 р.13 | web/index.html, web/style.css, web/map.js, web/interface.js, web/civic/shell/, ui/web_server.py, tests/civic/R01/ | claude/affectionate-ride-bol5v8 @ cb9d60a | b137df9 (+ handoff) |
| хранилище объектов | ui/civic_store/, tests/civic/R02/ | claude/elegant-franklin-jbhprq @ 26793c8 | b9eb180 |
| карта | web/civic/map/, tests/civic/R03/ | claude/zen-mendel-e79iiv @ 7de5e0b | f0a52f7 (пути идентичны) |
| редактор | web/civic/editor/, tests/civic/R04/ | claude/intelligent-sagan-7shpeh @ 9c996c6 | 9c996c6 |
| жалобы v1 | ui/civic_feedback/, web/civic/feedback/, tests/civic/R06/ | claude/focused-hypatia-z8h0no @ 933cd90 | 12b3170 |
| сценарии | engine/civic_scenarios/, web/civic/scenarios/, tests/civic/R07/ | claude/brave-hopper-bkc58b @ 16aa37a | 1197f7d |
| помощник | agent/civic_assistant/, web/civic/assistant/, tests/civic/R09/ | claude/wizardly-ptolemy-qy8ltw @ 14c3384 | c46b2ed |
| классификатор v1 | ml/civic_classifier/, tests/civic/R08/ | claude/wizardly-ptolemy-qy8ltw @ 14c3384 | = дерево в cb9d60a (5824fab) |
| проверенные данные | data/civic/astana/round12-verified/, data/civic/astana/round13-verified/, tests/civic/R05/round12/, tests/civic/R05/round13/ | claude/fervent-dijkstra-1cqrg5 @ a995f9f | a995f9f |

Проверки до запуска:
- Удалений файлов нет ни в одном источнике (`git diff --diff-filter=D HEAD <sha> -- <пути>` пусто).
- Ветки R06/R07/R09 построены от старого main (834a25f); их пути побитно совпадают с `56538a3 + *_vs_56538a3.patch`
  (сравнение деревьев `write-tree`), т. е. перенос путей = поставка, без чужой истории.
- Код прочитан на сеть/процессы: сеть только в ручной команде R05 `r12.py fetch` (pytest её не вызывает);
  тесты поднимают локальные HTTP-серверы и вызывают python/node.

Внимание для ролей раунда 14: папки tests/civic/R02…R09 сейчас содержат тесты раунда 13 по СТАРОЙ нумерации ролей
(R02 = хранилище, R03 = карта, R04 = редактор, R05 = данные, R06 = жалобы, R07 = сценарии, R08 = классификатор v1,
R09 = помощник). Новые тесты раунда 14 кладите в новые файлы своих папок; старые тесты не удаляйте без согласования с R01.

## I0 — шаг 2: INTEGRATION-патчи раунда 13 к общим файлам

`git apply --check` на перенесённом дереве: чисто применяются 2 из 9 (остальные писались к оболочке 56538a3/223296e,
а cb9d60a уже изменил shell.js и web_server.py). Каждый патч прочитан и перенесён по смыслу:

| Патч | Куда | Решение |
|---|---|---|
| R02 `gateway_routes.patch` | ui/web_server.py | применён как есть (staff/meta, staff/audit, import-candidates apply/dismiss) |
| R06 `r08_test_score_hidden.patch` | tests/civic/R08/test_r08_feedback_integration.py | применён как есть (score R08 не хранится и не показывается) |
| R06 `r01_r13_integration.patch` | shell.js, web_server.py | перенесён: ссылка квитанции `#civic-receipt=`, очистка черновиков при выходе, `classifier_source="r08"`; включение R08 по флагу уже было в cb9d60a |
| R09 `r01_integration_r13.patch` | shell.js, web_server.py | кэш расчётов уже был в cb9d60a (своя реализация); перенесён `onStale` при смене редакции карточки |
| R04 `r01_editor_integration.patch` | shell.js, web_server.py | маршруты — вместе с патчем R02; перенесён запрет повторять staff-POST под другим пользователем после CSRF; map-getter и закрытие архивной карточки уже были в cb9d60a |
| R03 `proposed_r01_shell.patch` | shell.js | перенесён: getPitch/getBearing/onDetail, при карте раунда 13 fitAll без подмены map.fitBounds и без лишнего GET /objects/{id} |
| R07 `r01_scenarios_tool.patch`, `r03_pause_map_input.patch`; R04 `r03_editor_tool.patch`; R01 р.13 `r03_r01_proposal.patch` | shell.js, civic-map.js | НЕ применялись: устарели — карта f0a52f7 сама слушает `civic-editor:tool` и `civic-scenarios:tool` (R04 и R07 их отправляют) и обрабатывает `styleimagemissing` |

## I0 — результаты проверок

Среда: облачный Linux, Python 3.13.16, Node 22.22.0, Playwright 1.56.1 (Chromium 1194). Дерево проверки = коммит I0
(рабочее дерево до коммита; `run_checks.sh` печатает предыдущий HEAD 0121238). Команда: `bash tests/civic/R01/run_checks.sh`.

| Проверка | Результат |
|---|---|
| pytest tests/civic на чистом переносе (до патчей) | 1249 passed, 13 skipped, **1 failed** — test_r08_feedback_integration (ожидаемо, чинится патчем R06) |
| pytest tests (весь репозиторий), I0 | **1384 passed, 12 skipped, 0 failed** |
| ui.web_check | PASS |
| node govtech (plan, resilience, whatif, school_case, school_vs_k05) | PASS |
| node R03 core, R04 core+mock, R01 explore | PASS |
| браузер P0 (житель/редактор/квитанция/модерация, 1440 и 390 px) | 59 PASS / 0 FAIL / 2 NOT_RUN |
| браузер сценарии сравнения | 16 PASS / 0 FAIL |
| браузер город r12 (районы, улицы, 360 px) | 81 PASS / 0 FAIL |
| браузер город r12, пустой реестр | 15 PASS / 0 FAIL |

NOT_RUN и пропуски (все с причиной):
- подложка OpenFreeMap и 3D-здания — хост недоступен из облака (упрощённый фон); подпись источника на телефоне — нет
  подписанного источника в офлайн-фоне;
- pytest skip 12: R05 — нет research/round-12-results/R05 и разбора очереди (данные R05 пустые, 0 подтверждённых
  записей); R08 — каталог результатов не перенесён; R02 test_r02_http — патч для старого Handler не нужен;
  R01 p0_api — проверка перезапуска только для SQLite.

Известные ограничения I0: все опубликованные объекты — синтетика (демо); реальных подтверждённых записей 0;
классификатор v1 (R08) обучен только на синтетике и включается флагом; интерфейс — раунда 13 (шапка Birge,
ҚАЗ/РУС и API v2 — следующие шаги R01).

## После I0: API v2, шапка Birge, поставка R11

| Шаг | Коммит | Что | Проверки |
|---|---|---|---|
| база пакета | be2cb4e | merge claude/round-14-package @ 7ff639a (правила веток, ui-kit/i18n R11 v1 608e367) | — |
| API v2 | caf2cff | /api/civic/v2/* (14 маршрутов + /modules), 503 module_not_ready | pytest tests: 1446 passed / 11 skipped / 0 failed; test_r01_api_v2.py 61/61 |
| шапка Birge | d27116c | birge.js/birge.css, старые режимы из меню, вид «Житель» | r14_shell.cjs 28/0; полный run_checks — см. ниже |
| R11 | (этот коммит) | пути web/civic/ui-kit/, web/civic/i18n/, tests/civic/R11/ с claude/r14-R11 @ ba8758b (DELIVERY R11: code = голова ветки) | pytest tests/civic/R11 12/12; r14_shell.cjs 28/0; шрифт font/woff2 200, icons.svg image/svg+xml |

Код R11 прочитан: innerHTML только со статической разметкой (тексты — textContent), сети нет, i18n_tools пишет словари
только по явной команде. Удалений относительно 608e367 нет.

## 2eaeacb — полный run_checks.sh (отдельная рабочая копия коммита)

| Шаг | Результат |
|---|---|
| pytest tests | PASS 1458 passed, 11 skipped |
| ui.web_check, node govtech ×5, node R03/R04/R01 | PASS |
| браузер сценарии / город / пустой реестр / шапка r14 | PASS 16/0 · 81/0 · 15/0 · 35/0 |
| браузер P0 | 62 PASS / **1 FAIL** / 2 NOT_RUN — FAIL = предупреждение модуля карты «civic-r03-demo-ring could not be loaded» |

Разбор FAIL: трассировка показала, что предупреждение появляется при смене режима (карта → учебная модель → карта);
отдельный повтор (12 попыток) не воспроизводит; **на I0 (3adabe3) тот же трассирующий P0 дал его в 1 из 2 прогонов** —
это давняя случайная гонка модуля карты (код R03 f0a52f7, владелец в раунде 14 — R12), не регрессия R01.
Передано R12 (INTEGRATION.txt R01 §7).

r13_junctions.cjs (не входит в run_checks): 13 PASS / 2 FAIL и на I0, и сейчас — помощник R09 c46b2ed передаёт поле
revision и иначе снимает объяснение A/B, чем ожидал тест раунда 13. Модули сравнения и помощника скрыты из Birge.

## Панель справа, скрытие модулей раунда 13 вне демо (рабочее дерево после 3bf631f)
- shell.css: на ≥ 761 px панель справа (400 px; 360 px на 761–1100), навигация слева сверху, кнопки карты слева от
  панели/ящика; freeArea() считает панель справа. Телефон без изменений.
- «Сравнить ограничения» и помощник скрыты всегда (body[data-birge-tools="off"]); ?tools=all возвращает их —
  так их проверяют p0_flow, scenarios_smoke, r13_junctions.
- Проверки: r14_shell 38/0 (+ раскладка UX_SPEC и скрытие), r12_city 81/0, scenarios_smoke 16/0, P0 62/1/2 (тот же demo-ring).

## B1 — шаг 1: перенос поставок R02, R07, R08, R09 (без подключения)

Правило переноса: только файлы, которые роль ДОБАВИЛА или ИЗМЕНИЛА относительно своей базы
(`git diff --diff-filter=AM <merge-base> <code_sha> -- <пути роли>`), `git checkout <code_sha> -- <файлы>`.
Так тесты раунда 13 в tests/civic/R07, R08, R09 (которых нет в базах ролей) не удаляются и не откатываются
к версиям раунда 12.

| Роль | Ветка | code_sha (DELIVERY) | Пути | Файлов |
|---|---|---|---|---|
| R02 | claude/r14-R02 | 229f1aa | ml/datasets/, ml/labeling/, web/labeling/, tests/civic/R02/round14/ | 27 |
| R07 | claude/upbeat-knuth-i0rqaa | 5a97636 | ui/civic_heat/, web/civic/heat/, tests/civic/R07/ (новые) | 21 |
| R08 | claude/r14-R08 | 9f1d9c0 | ui/civic_akim/, web/civic/akim/, tests/civic/R08/ (новые) | 20 |
| R09 | claude/modest-shannon-0ki93p | da295be | ui/civic_feedback/v2/, web/civic/feedback/ (новые), tests/civic/R09/ (новые) | 31 (v1 побайтно = I0) |

- INTEGRATION R02: `private/` добавлен в .gitignore.
- Код прочитан: сеть только в LLM-скриптах R02 (`ml/labeling/llm_client.py`, ручной запуск с --confirm-external,
  тесты подставляют транспорт); остальное — stdlib, локальные тестовые серверы, node для проверок.
- pytest tests/civic/R02/round14 tests/civic/R07 tests/civic/R08 tests/civic/R09 — **784 passed, 1 skipped**.

## B1 — шаг 2: подключение R09 + R07 + R08 (коммит d3c33d9)

Что сделано (подробно для ролей — INTEGRATION.txt §8):
- API v2: сервис жалоб R09 отвечает на свои 11 маршрутов как есть (конверт ok/data, сотрудник — по principal R02);
  R07 handle_get — /heat, /heat/meta, /heat/target; R08 handle_get — /akim/summary.
- Связка: карта R07 читает записи R09 (+ синтетический набор R07 при CIVIC_DEMO=1), сброс кэша по событиям R09,
  R08 — те же записи. Ячейки «примерного места» R09 рисуются по сетке R09 (адаптер резолвера; у R07 другая сетка).
- Оболочка: «Карта жалоб» в панели, кнопка жителя «Сообщить о проблеме», «Мои обращения» в шапке, «Картина дня» — R08,
  горячее место → цель на карте, ссылка #target=…; запросы карты несут CSRF сотрудника и id устройства R09.
- Правки в чужих путях (минимальные, переданы владельцам): ui/civic_store/auth.py COOKIE_PATH "/api/civic" (R06) +
  tests/civic/R02/test_r02_auth.py; ui/civic_heat/service.py records()/generation (патч R08 для R07).

Найдено на стыках и исправлено в сборке: cookie сотрудника не доходила до v2 (403 на «Взять в работу»); сетка ячеек
R09 ≠ R07 (место жителя на ~7 км восточнее); разные ключи id устройства R07/R09; панель «Мои обращения» перекрывала
карточку при переключении на «Акимат»; «birge:lang» на document, а R07/R09 слушают window.

Проверки на d3c33d9 (полный run_checks.sh в отдельной рабочей копии):

| Шаг | Результат |
|---|---|
| pytest tests | **1793 passed, 11 skipped** |
| ui.web_check, node ×8 | PASS |
| браузер: сценарии / город / пустой реестр / шапка | 16/0 · 81/0 · 15/0 · 38/0 |
| браузер: путь демо B1 (r14_b1.cjs) | **15/0** — жалоба B-0001, +1 на карте, точность ячейки, «Мои обращения», «Картина дня», горячее место → цель, «Взять в работу» → «Исправлено» (зелёная) |
| браузер P0 | 62/1/2 — FAIL = известная гонка demo-ring модуля карты (R12), воспроизведена на I0 |

Состав B1-кандидата: I0 (раунд 13) + R11 @ ba8758b + R02 @ 229f1aa + R07 @ 5a97636 + R08 @ 9f1d9c0 + R09 @ da295be
+ база пакета d2a4351 (LOCAL-1 объекты OSM, LOCAL-2 three.js). Не включены (нет DELIVERY): R03, R04, R05, R06, R12.

## B2 — шаг 1: поставки R11, R12, R06, R05, R09, R13 по SHA (коммит 915143f)

Правило переноса то же (B1 — шаг 1). Для повторных поставок — файлы, изменённые между прежним и новым code_sha.

| Роль | Ветка | code_sha (DELIVERY) | Пути | Примечание |
|---|---|---|---|---|
| R11 | claude/r14-R11 | cc77761 | web/civic/ui-kit/, web/civic/i18n/, tests/civic/R11/ | повтор поверх ba8758b |
| R12 | claude/tender-brahmagupta-ef5ztl | d13f49a (tested; code 8810221 — предок, разница только в 3 тестах) | engine/civic_geo/, data/civic/astana/geo/, web/civic/map/, web/civic/editor/, tests/civic/R12/ | |
| R06 | claude/round-14-r06 | 7031afa | ui/civic_store/, web/civic/proposals/, tests/civic/R06/ | + патч r02_old_store_tests.patch (тесты R02 под миграцию 6) |
| R05 | claude/r14-R05 | b0353ee | web/civic/build3d/, tests/civic/R05/ | web/vendor/three уже в базе (LOCAL-2) |
| R09 | claude/modest-shannon-0ki93p | a4ab5a4 | ui/civic_feedback/, web/civic/feedback/, tests/civic/R09/ | повтор поверх da295be |
| R13 | claude/r14-R13 | 8705829 | ml/civic_forecast/, ui/civic_forecast/, tests/civic/R13/ | маршрут /forecast — по r01_forecast_route.patch |

Шлюз: 5 маршрутов R12 (raw handle без префикса) + прогрев графа при старте; 13 маршрутов R06 (bind в фабрике
store(), параметры district/status/device_id/since проверяются в шлюзе, лишние именованные аргументы функциям старой
сигнатуры не передаются); GET /forecast (R13). Тесты ролей R12, R06, R09, R05, R11, R02, R07, R08: 1869 passed, 11 skipped.

## B2 — шаг 2: повторные R11/R09/R08, R04 + R03, фронтенд R05/R06 (коммит b5c153d)

| Роль | code_sha | Что |
|---|---|---|
| R11 | 6102dfb | словари: ключи build3d.* (R05) и forecast.* (R13); ui-kit без изменений |
| R09 | fa49fc9 | совместный прогон с настоящими R12 и R04; ячейки в общей сетке |
| R08 | 4ce8f08 | поставка 2: UX-правки R11, функции R06; akim.i18n.json удалён (убран из CIVIC_ASSETS) |
| R04 | deeb1de | ml/civic_dedup/, ui/civic_ml_api/, tests/civic/R04/round14/; патч r01_similar_target.patch; connect_store(store R09) + warmup в wire() |
| R03 | 252913e | ml/civic_classifier_v2/, tests/civic/R03/round14/ (без весов — LOCAL); нужен R04: словарь R03 даёт suggest |

R03 и R04 в просьбе на B2 не было: взяты, потому что у обоих есть DELIVERY, R09 просит подключить R04 (INTEGRATION
R09 «Совместный прогон»), а без кода R03 тест R09 test_r09v2_neighbours падает (suggest=false). Откат — один коммит.
Найдено: тесты R03 `from conftest import needs_ml` ломаются, если запускать папки списком (pytest A B C) — conftest
подменяется чужим; полный `pytest tests` и `pytest tests/civic/R03/round14` отдельно — работают (INTEGRATION §9).

Оболочка: 3D-каталог R05 над картой слева от панели, на телефоне — над опущенной шторкой; пересоздаётся при смене
«Акимат/Житель»; на «Картине дня» скрыт. Адаптер запросов R05 -> R06 @ 7031afa (контракты расходятся — INTEGRATION §9).
Новая проверка tests/civic/R01/browser/r14_b2.cjs (в run_checks.sh).

Не включены (нет новой DELIVERY на момент сборки): R07 (DELIVERY 5a97636; на ветке есть 9bc25e6 «day 3»), R06 d043e7b
(DELIVERY всё ещё 7031afa), R05 305077f/7f42cb3 (checkpoint 6–7, DELIVERY b0353ee).

## B2 — проверки

Полный run_checks.sh на b5c153d в отдельной рабочей копии (git worktree, Linux, Python 3.13, Node 22, Chromium Playwright):

| Шаг | Результат |
|---|---|
| pytest tests | **2377 passed, 20 skipped, 1 xfailed** (было 11 skip на B1; новые 9 — R03 7 и R04 1: нет scikit-learn/onnx/torch в облаке; R06 store 1: копия теста R02 для старого Handler b2cb2e0 — все с причиной в выводе pytest -rs; xfail — test_r08_demo_plausible: ждёт правдоподобный демо-набор R07) |
| ui.web_check, node govtech ×5, node R04, node R01 explore | PASS |
| node R03 core (тест карты раунда 13) | FAIL 24/2 — устарел: карта теперь R12 (область «примерного места», линии по улицам); у R12 своя копия теста с новыми ожиданиями. В run_checks.sh шаг заменён на node R12 map core (29/0) и R12 editor core+mock (40/0) |
| браузер P0 | 62/1/2 — FAIL = известная гонка demo-ring модуля карты (R12/R03), как на I0 и B1; NOT_RUN — подложка OpenFreeMap |
| браузер: сценарии / город / пустой реестр / шапка | 16/0 · 81/0 · 15/0 · 38/0 |
| браузер: путь демо B1 (r14_b1.cjs) | **15/0** |
| браузер: путь демо B2 (r14_b2.cjs на b5c153d) | **17/0** |

После прогона в r14_b2.cjs добавлен путь жителя через R12/R04 (место «Спортплощадка» от /targets, подсказка
«Освещение» от R04, жалоба привязана к объекту OSM, не к ячейке): на рабочем дереве **20/0**. Код приложения после
b5c153d не менялся — только проверки и документы.

## B3 — ветка claude/r14-R01 (10 окт, вечер)

Новая сессия R01 продолжает с B2-кандидата f54361d: ветка `claude/r14-R01` создана от `claude/round-14-package`
и поставлена на `origin/claude/sharp-dijkstra-0t87gl` (f54361d — потомок 4bbf456, т. е. «от пакета»; история R01
целиком, без чужих веток). Правило переноса — как в «B1 — шаг 1»: только файлы, изменённые ролью между прежним и новым
code_sha (`git diff --diff-filter=AM`), `git checkout <code_sha> -- <файлы>`; перед переносом проверено, что эти файлы
не правились в сборке R01 (пересечений нет, кроме одного — ниже).

| Шаг | Коммит | Роль | code_sha (DELIVERY) | Что |
|---|---|---|---|---|
| 1 | a8fabce | R06 | b42e790 (поставка 2) | ui/civic_store, web/civic/proposals, tests/civic/R06 + r01_b2_r02_tests.patch к tests/civic/R02 (3 файла) |
| 1 | a8fabce | R07 | 306074b (день 3) | ui/civic_heat, web/civic/heat, tests/civic/R07; пересечение — ui/civic_heat/service.py (патч R08 records()/generation из B1): взята версия R07, где это уже есть |
| 2 | be82fa8 | R11 | 52d7c59 | словари (563 ключа), i18n.js — склонение дробных в ru, build_shots.cjs |
| 2 | be82fa8 | R02 | f62cc93 | probe_v2 (300 тестовых текстов), README датасетов |
| 2 | be82fa8 | R10 | 9c364c7 | tests/civic/R10 (точность карты), tests/e2e (путь демо, UX-экраны, запуск одной командой) |
| 2 | be82fa8 | R14 | 8e106a9 | docs/birge, docs/diploma |
| 3 | 7227fce | R01 | — | запасной фон OSM, демо-проекты R06 при старте, UX оболочки (ниже) |
| 4 | d9a8895 | R03 | d472baf | MODEL_CARD после LOCAL-4, умолчания ONNX, results/*.json (без весов) + .gitignore artifacts/ |

Не взято: R02 llm_v1 (2a95286 — после её DELIVERY), R05 (DELIVERY всё ещё b0353ee; на ветке checkpoint 11 ef6cf0e и
169c56b — клиент под R06 поставки 2), R15 (нет DELIVERY; patch для R01 обещан в INTEGRATION).

Шлюз и оболочка (подробно — INTEGRATION.txt §10): metoo_times R09 → R07; резолвер ячеек R01 снят; /heat/target со
staff=True только после проверки сессии R02; адаптер R05→R06 урезан до DELETE→withdraw и device_id; R07 монтируется
с fitPadding/avoidRects, ссылки #target= и «Картина дня» — через оболочку, период в focusTarget.

Проверки по ходу (рабочее дерево, облако: Linux, Python 3.13.16, pytest 9.1.1, Node 22.22.0, Playwright 1.56.1,
Chromium headless, программный WebGL, внешние запросы закрыты):
- pytest R01+R06+R07: 843 passed / 3 skipped / **2 failed** — оба у R07 на стыке (BUGS I-01 подписи из реестра R12,
  I-03 тест по старой сетке R09); поведение приложения проверено отдельно (ячейка R09 содержит точку, якорь 59 м).
- pytest R08+R09+R02: 931 passed / 2 skipped / **1 error** — сбор test_r08_heat_match.py (BUGS I-02); прежний XFAIL
  test_r08_demo_plausible теперь проходит (2 passed) — демо-набор R07 правдоподобен.
- pytest R11+R02/round14+R10: 134 passed / **4 failed** — R10 test_r10_accuracy: данные R12 (yards.json: 19 вершин
  двора за границей Астаны — B-009) и R05 (astana-existing.json: 337 координат за границей, 41 ж/д платформа как
  «остановка», 2 остановки дальше 60 м от улицы — B-007/B-008). Владельцы — R12 и R05; в сборку эти данные идут
  как есть, на экране R05 их показывает только в 3D-каталоге (подсказка «рядом уже есть остановка…»).
- браузер r14_b1 15/0 (ожидание выбора цели вместо паузы 800 мс: R07 сначала ведёт камеру), r14_b2 20/0.

Полный run_checks.sh на be82fa8 (отдельная рабочая копия) нашёл то, чего не видно по частям:
- pytest прервался на ошибке сбора R08 — **остальные тесты не выполнились**. run_checks.sh теперь запускает pytest с
  --continue-on-collection-errors: одна сломанная папка роли больше не прячет результаты остальных.
- телефон: легенда R07 @ 306074b (сверху слева) легла на шапку и перехватывала нажатие на «Меню» — P0 и r14_shell
  падали на клике (житель не открыл бы меню). Исправлено в 7227fce (легенда под кнопкой «Территория»).

### B3 — шаг 3: UX оболочки по разбору R11 (B1/B2) и BUGS R10

| Замечание | Что сделано (пути R01) |
|---|---|
| R11 B1 п. 4 «без OpenFreeMap карта пустая» (риск №1) | web/map.js offlineStyle: оси улиц OSM со стенда R07 (город — главные, Нура — все с 12-го масштаба), атрибуция OSM; подписей нет (глифы только с сервера тайлов) |
| R11 B1 п. 5, R10 B-012/B-013 плашка «Подложка OpenFreeMap…» по-русски, 11 px | ключ R11 shell.map.basemap_offline, 14 px, перевод при ҚАЗ/РУС |
| R11 B1 п. 6, R10 B-014 кнопки карты 34–40 px, aria-label по-русски | 44 × 44, зона 48; aria-label/title — shell.map.* |
| R11 B1 п. 7, R10 B-013 панель «Территория» 10–12 px, 440 px на телефоне | весь текст ≥ 14 px, кнопки ≥ 44 px; на телефоне — кнопка «Территория / Аумақ» 48 px, сама сворачивается после выбора |
| R11 B1 п. 14 подзаголовок шапки 11 px | 14 px; ниже 1024 px скрыт |
| R11 B1 п. 1–2 мастер жалобы под панелью «Территория» (375) | корень R09 вынесен из слоя #civic-panel; при html.bc-open «Территория» и легенда скрыты |
| R11 B1 п. 3 значок R07 перехватывает нажатие при выборе места | body.birge-picking: значки R07 и подписи R05 пропускают нажатие к карте |
| R11 B1 п. 8 «Сообщить о проблеме» в 3 строки, закрывает «Мен де» | во всю ширину в одну строку; скрыта, пока открыта карточка цели; низ шторки прокручивается выше неё |
| (новое) 3D-каталог закрывал легенду R07 на ноутбуке | каталог свёрнут в кнопку «Что построить?»; пока каталог открыт или идёт размещение — легенда скрыта |
| (новое) легенда R07 на шапке телефона закрывала «Меню» | легенда ниже кнопки «Территория»; в полноэкранной шторке скрыта (там атрибуция OSM) |
| RUN.txt п. 4 ручной seed-r14-demo | CIVIC_DEMO=1: шлюз сам вызывает seed_r14_demo R06 при старте (идемпотентно) |
| R11: пересылка birge:lang на window лишняя | убрана (i18n R11 шлёт событие и на document, и на window) |

Скриншоты главных экранов — новый tests/civic/R01/browser/r14_shots.cjs (акимат/житель × 1366/375 × ru/kk + каталог
открыт): прокрутки вбок нет; наложений плашек нет, кроме намеренного «кнопка жалобы над шторкой» у жителя на 375.
Тексты < 14 px, оставшиеся на главном экране, — в блоке «городские работы» модуля карты R12 (INTEGRATION §10).

### B3 — полный run_checks.sh на 7227fce (отдельная рабочая копия)

| Шаг | Результат |
|---|---|
| pytest tests (теперь с --continue-on-collection-errors) | **2434 passed, 21 skipped, 7 failed, 1 error** — все объяснены: R07 ×2 (BUGS I-01, I-03), R07 test_citywide_under_300ms — замер времени под нагрузкой (параллельно шли мои браузерные проверки; отдельно 3/3 PASS, 0,6 с), R10 ×4 (данные R12/R05: B-007/B-008/B-009), R08 сбор (BUGS I-02) |
| ui.web_check, node govtech ×5, R12 map/editor, R04, R01 explore | PASS |
| браузер P0 | 63/1/1 — FAIL = давняя гонка demo-ring модуля карты (R12/R03), как на I0/B1/B2; проверка атрибуции на телефоне теперь выполняется (у запасного фона есть источник OSM) и проходит |
| браузер: сценарии / шапка / B1 / B2 | 16/0 · 38/0 · 15/0 · 22/0 |
| браузер: город / пустой реестр | 3/2/1 и 2/1 — мои проверки раунда 12 ждали открытую панель «Территория» на 360 px; поведение изменено намеренно (свёрнута в кнопку). Тест научен раскрывать панель и проверять свёрнутое состояние — и сразу нашёл: кнопка 44 px вместо 48 (правило `.civic-explore button` сильнее) — исправлено. После правки: город **82/0** (плашка фона теперь проверяется), пустой реестр **15/0** |
