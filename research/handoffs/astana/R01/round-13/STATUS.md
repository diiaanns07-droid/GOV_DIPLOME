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
