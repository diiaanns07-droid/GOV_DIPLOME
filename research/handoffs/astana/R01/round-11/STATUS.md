# R01 BUILD — раунд 11 (Астана)

Роль: R01 — BUILD и единственный интегратор общих app-файлов.
Ветка: `claude/affectionate-ride-bol5v8` (origin GOV_DIPLOME). Не прежний BUILD-сеанс.
Исходный HEAD: `834a25f` (= main). PACK_SHA: `9c2f5c0dae14b46c0697a9dfc7f854351bfd570d`.
Прикладной снимок: `b2cb2e0` (CODE_SHA прежнего BUILD `6de3f25`), импорт по путям.
Пути: ui/web_server.py, app.py, web/{index.html,map.js,interface.js,style.css,app.js},
web/govtech/shell.{js,css}, web/civic/shell/, requirements*.txt, run.{bat,sh},
.gitignore, .gitattributes, tests/civic/R01/, research/round-11-results/R01/, этот файл.

## Checkpoint 1 — аудит (PARTIAL, этап 00–25)
- DONE: импорт проверенных путей снимка b2cb2e0 (57 файлов) + .gitattributes из PACK_SHA.
- DONE: исходные проверки на импортированном дереве — pytest 133, web_check 14, node PASS
  (school_case 3621, school_vs_k05 7560). Подробно: research/round-11-results/R01/BASELINE_AUDIT.txt.
- DONE: MATRIX.json — поставок R02–R10 на 15:29Z нет.
- NOT_RUN: браузер, civic-слой (ещё не создан).

Следующий шаг: civic shell (web/civic/shell/), api.request с CSRF, маршрутизация
/api/civic/v1 в Handler с явным allowlist, civic-режим по умолчанию для Астаны.
