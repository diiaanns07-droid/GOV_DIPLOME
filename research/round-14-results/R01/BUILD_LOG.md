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
