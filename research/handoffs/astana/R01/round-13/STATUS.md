# R01 — раунд 13 (Астана): сборка-кандидат и подключения

Роль: R01 — сборщик кандидата интеграции (исключение ROLES.json) и владелец общих точек подключения.
Ветка: `claude/affectionate-ride-bol5v8`. Продолжение поставки раунда 12 (head 6dc1660, код 223296e).
REFERENCE_BASE_SHA: `56538a3a7504d4589c38ab4d3c5107f12aa7f8a6` (база сравнения, не цель отката).
Свои пути: web/civic/shell/, web/index.html, web/map.js, web/interface.js, web/style.css, ui/web_server.py,
tests/civic/R01/; результаты research/round-13-results/R01/; этот файл.
Чужие модули: только контролируемый импорт путей из ROLES.json по закреплённым SHA, без правок.

## Checkpoint 1 — PARTIAL: состав кандидата и первый запуск
- DONE: прочитаны BASELINE/DELIVERIES/ROLES раунда 13; все 7 закреплённых head совпадают с origin;
  новых веток R07/R10 нет.
- DONE: импорт по путям (без merge), журнал — research/round-13-results/R01/BUILD_LOCK.json (98 файлов,
  blob каждого файла сверен с коммитом кода acb948d): R02 bd7a911, R03 71c4e1b (PARTIAL), R04 69d5691,
  R05 4d5731f (0 подтверждённых, в реестр не импортируется), R06 e0b4741, R08 e311ba8 (synthetic only,
  ещё не подключён), R09 f8aea9a. Удалений файлов базы нет. R07 — код базы (поставки нет).
- DONE: оценка импортированного кода перед запуском: сеть только в ручной команде R05 `fetch`
  (отказывается писать в репозиторий), в локальных HTTP-тестах и в ручном `eval_r12_live.py` R09
  (не собирается pytest); модель R08 — JSON.gz с проверкой sha256, без pickle; зависимости R08 — stdlib.
- DONE (R01): CivicApiError сохраняет безопасные поля ошибки (current_revision, retry_after в т.ч. из
  Retry-After, can_confirm, allowed, previous_receipt) как err.x и err.error.x — их ждут R04 и R06.
- Проверки на acb948d: pytest 1073 passed / 4 skipped / 3 FAIL — все три в
  tests/civic/R05/round12/test_r12_search_import.py: тест читает research/round-12-results/R05/
  import_search_results.py, который не входит в пути импорта R05 (передать R05); node R03 25/25,
  R04 36/36, R01 explore 5/5; браузерный P0 59 PASS / 0 FAIL / 2 NOT_RUN (P0 обновлён под шаг R04
  «точность места» перед инструментом точки).
- Дальше: стыки R04 (поздняя карта, /session, archive), R03 getPadding/editor tool, R09 revision +
  ScenarioResultCache, R06+R08 opt-in.

## Checkpoint 2 — PARTIAL: стыки R03/R04/R06+R08/R09 (код b137df9)
- R04: карта передаётся функцией + setMap после готовности карты (кабинет, открытый до карты, рисует);
  openEditor(id) ждёт ответ /session самого R04 (один повтор), без формы входа; onPublished(item,{action}):
  выбирается только запись, опубликованная сейчас; после архива карточка закрывается.
- Ошибки API: 409 current_revision и 429 retry_after (тело или Retry-After) доходят до модулей полями.
- R03: щелчки по карте при инструменте R04 или открытом сравнении не открывают карточки (отмена в
  onSelect; «выбор из нескольких», оставленный таким щелчком, закрывается по окончании инструмента);
  getPadding/setInteractive передаются с проверкой наличия — текущий R03 их не знает, поэтому адаптер
  fitAll и keepVisible оставлены. Предложенный patch R03: research/round-13-results/R01/proposed/
  r03_r01_proposal.patch (getPadding, setInteractive, styleimagemissing для demo-ring; git apply --check OK).
- R09: редакция карточки при монтировании и обновление при перезагрузке данных/публикации; в ящике
  сравнения помощник объясняет только результат, посчитанный сервером (scenario_id result:<digest>);
  смена входных данных убирает старое объяснение. Кэш R09 в шлюзе: 16 записей, 1 ч, ≤ 1 МБ на результат,
  только после успешного compare; присланные браузером цифры — 400.
- R06+R08: классификатор только по явному включению (--civic-classifier r08 или CIVIC_R08_CLASSIFIER=1),
  статус в /modules (версия, synthetic_demo_only;real_data_NOT_EVALUATED); ошибка/зависание/отсутствие
  модели не мешают сохранению (проверено).
- Проверки: test_r01_round13.py 12/12; r13_junctions.cjs 15 PASS / 0 FAIL; r12_city 81/0; P0 58/1/2 —
  FAIL = периодическое предупреждение R03 demo-ring (выделено в отдельную проверку R03).
