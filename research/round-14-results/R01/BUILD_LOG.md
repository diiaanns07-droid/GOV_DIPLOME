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

## B3 (сессия b11, ветка claude/r14-R01, 10 окт 15:36–16:00) — восстановлено R01 по коммитам

b11 вела R01 в ветке `claude/r14-R01` поверх f54361d (без расхождений). Ночью R01 перенёс эти 4 коммита в ветку из
реестра `claude/sharp-dijkstra-0t87gl` (fast-forward, d9a8895). Журнал b11 не вела — ниже по сообщениям коммитов.

| Коммит | Что |
|---|---|
| a8fabce | R06 поставка 2 (b42e790) + r01_b2_r02_tests.patch; R07 day 3 (306074b, records()/generation у R07 — патч R08 снят); шлюз: metoo_times из R09, адаптер ячеек R01 убран, /heat/target staff только после проверки сессии; оболочка: fitPadding/avoidRects для R07, адаптер R05→R06 сокращён до DELETE→withdraw и device_id; BUGS.md I-01..I-03 |
| be82fa8 | R11 52d7c59 (563 ключа, дробные формы ru), R02 f62cc93 (probe_v2), R10 9c364c7 (инструменты приёмки), R14 8e106a9 (docs) |
| 7227fce | офлайн-фон: оси улиц OSM вместо пустого поля; CIVIC_DEMO=1 сам засевает демо R06 (seed-r14-demo не нужен); каталог «Что построить?» свёрнут в кнопку; кнопки карты 44/48 px; шрифты ≥ 14 px; телефон: «Территория» свёрнута, мастер жалобы вне слоя панели, «Сообщить о проблеме» в одну строку; значки R07 и подписи R05 пропускают нажатие при выборе места |
| d9a8895 | R03 d472baf (MODEL_CARD после LOCAL-4, ONNX по умолчанию, результаты без весов) |

## Ночь, круг 1 (10–11 окт) — коммит 2b9e837

Источники: R10 BUGS.md/ACCEPTANCE_B2.md (ac8508e), R11 UX_REVIEW (52d7c59), R15 SECURITY_REVIEW/INTEGRATION (77bd744),
LOCAL_B2.md (a38da11). Новые DELIVERY: R15 c5b98a0 (тесты; patches b892532), R10 08392e7 (тесты). Остальные роли —
без новых DELIVERY (R07 голова 35e6feb, R05 169c56b, R12 8bb7bf8 — коммиты после DELIVERY, не сданы).

- R15: тесты tests/civic/R15 + 5 patch (P-R01 мой шлюз; P-R09, P-R07, P-R04, P-R02 — применяет R01 по INTEGRATION R15).
  Все 13 открытых находок закрыты: tests/civic/R15 **99 passed** (ID перенесены в FIXED, как просил R15).
- R10: tests/e2e (path-scoped 9c364c7..08392e7).
- R01: B-022 (каталог 3D на телефоне), B-025 (ссылка «Перейти к главной кнопке»), B-021 частично (служебная строка
  кабинета скрыта; перевод кабинета — R12/R11, BUGS I-04).
- pytest tests до круга (d9a8895): 6 failed, 2436 passed, 21 skipped, 1 error; после: **6 failed, 2535 passed, 21 skipped,
  1 error** — те же чужие падения (R07 I-01/I-03, R08 I-02 — ошибка сбора, R10 точность: данные R12 c01, R05 c07/c16/c22).
- r14_b2.cjs **25/0** (добавлены клавиатура и кнопка каталога на телефоне).

## Ночь, круг 2 — коммиты daec72a, 095653b, ef1ef44 и следующий (поставки третьей волны)

Приёмка R10 на 2b9e837 (run_acceptance.cjs, облако): сценарий 79/18/4, UX 58/34/8 — по R01: лента работ по-русски
в ҚАЗ (39–40 строк), шрифт 12 px в «Для сотрудников» и «Слоях», список районов 23 px, ручка шторки 36 px, Tab > 40.
- daec72a (оболочка): лента работ раунда 13 скрыта в Birge (карточка объекта работ по нажатию на карте остаётся),
  корень формы жалобы сразу за #map (13-й Tab после щелчка по карте), шрифты ≥ 14 и зоны ≥ 44 px, «Территория» на
  телефоне не наезжает на шторку, заглушка для значков POI без спрайта (web/map.js). r12_city — под свёрнутую панель B3.
- 095653b: R03 937f665, R05 169c56b (клиент под контракт R06, сам следует birge:mode → адаптер build3dFetch и
  пересоздание убраны), R06 d20c7e2, R07 597ec4f (I-01/I-03), R08 828ee0d (I-02), R11 a62a67c, R13 15fc856.
  pytest: 4 failed (только проверки точности R10: данные R12 и R05), 2584 passed.
- ef1ef44: слита база пакета a38da11 (погода LOCAL-9 для R13, отчёт LOCAL_B2) — только добавленные файлы.
- Третья волна (рабочее дерево после ef1ef44): R03 ac0e954, R05 fc03e19, R06 efafee9 (S15 R15 внутри), R07 b28268b,
  R08 c7646a1, R11 f0e5e80, R13 a0133e9, R14 16ee4f7 (docs), R10 3623f65 (тесты); tests/civic/R15 — с ветки R15
  (054b056, как просит R15), S15 перенесён в FIXED: R15 121/0. «Картина дня» монтируется с titleTag: "h2" (R08 4д).
- **0a7a346** — третья волна + R01: при CIVIC_DEMO=1 3 синтетические жалобы R09 у «Хан Шатыр» (B-030: «Я тоже» на
  шаге 2), связка модулей при старте (B-032), 3D скрыт при открытом кабинете (B-031), клиент api.v2 — оборванный
  ответ = «нет связи» (R05 bad_response в r14_shell), titleTag h2 для «Картины дня». Тесты R01 — под слова словаря R11.
  pytest: **1 failed** (двор R12, B-009), **2638 passed**, 21 skipped; браузер: B1 15/0, B2 25/0, шапка 38/0, город 81/0.
  Приёмка R10 на ef1ef44 (до этих правок): сценарий 110/3, UX 94/0 — по R01 остался только B-030 (исправлен здесь).

## Ночь, круг 3

Полный run_checks.sh на **0a7a346** (отдельная копия): pytest 1 failed (R10 точность: двор R12, B-009) / 2639 passed /
21 skipped; web_check и node — PASS; браузер: P0 63/1/1 (известная гонка demo-ring модуля карты R12), сценарии 16/0,
город 81/0, пустой реестр 15/0, шапка 38/0, путь B1 15/0, путь B2 25/0.
Приёмка R10 (их ACCEPTANCE_FINAL на ef1ef44): «можно показывать, блокеров нет»; на R01 оставались B-030/B-032 (закрыты
в 0a7a346) и B-021 (кабинет на ҚАЗ).

Четвёртая волна (рабочее дерево после cb6d336): R05 f946157, R07 13042af (P-R07 R15 внутри), R11 4ed2ece, R14 4706aa3.
B-021: патч R11 `patches/R12_staff_i18n.patch` к кабинету сотрудника (web/civic/editor/editor.js, путь R12) применён R01
по правилу «патчи ролей через INTEGRATION» — R12 ночью без поставок, а это последний провал приёмки на ҚАЗ. Тексты кабинета
берутся из ключей staff.* / works.* словаря R11 (русский — запасной). Тесты редактора R12: 92/93 (1 — «geo server did not
start» за 60 с под нагрузкой параллельного прогона; без нагрузки — см. ниже).
