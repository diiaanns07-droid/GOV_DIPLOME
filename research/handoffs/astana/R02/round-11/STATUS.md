# R02 — Сервер, база объектов и доступ редактора (раунд 11, Астана)

- Роль: R02. Ветка: `claude/trusting-ptolemy-6ms354` в origin `https://github.com/diiaanns07-droid/gov_diplome`
  (GOV_DIPLOME). Сессия была запущена в ADMIT_STUTU; его remote не менялся. GOV_DIPLOME клонирован
  отдельно в `/home/user/gov_diplome`, своя ветка создана там (в origin её раньше не было).
- Исходный HEAD ветки: `b2cb2e02c602c166ba6d47c02d8e902e5478c791` (прикладной снимок `claude/beautiful-clarke-sbzomj`;
  CODE_SHA сборщика `6de3f25` — его предок). Ветка не перемещалась на main.
- PACK_SHA: `9c2f5c0dae14b46c0697a9dfc7f854351bfd570d` (`origin/codex/govtech-main-interface`, PACK_STATUS=READY).
  Прочитаны BRIEF, CONTRACT (civic-v1), ROLES, BASELINE, prompts/R02, fixtures/civic_object.json.
- Свои пути: `ui/civic_store/`, `tests/civic/R02/`, `research/round-11-results/R02/`, этот файл.
  Общие файлы (ui/web_server.py, app.py, .gitignore, requirements) не редактируются — патч и инструкции для R01
  будут в `research/round-11-results/R02/`.

## Checkpoint 1 — схема и пустая база (DONE)
- `ui/civic_store/db.py`: миграция 1 (таблицы `civic_*`), WAL, busy_timeout, BEGIN IMMEDIATE, соединение на
  операцию, контроль checksum миграций, отказ от понижения версии, append-only триггеры истории,
  запрет DELETE объектов. База только вне репозитория или в `.runtime/` (сама пишет `.runtime/.gitignore` = `*`),
  `web/` и другие папки проекта отклоняются.
- Проверка: `python -m pytest -q -p no:cacheprovider tests/civic/R02` → 13 passed (2026-10-06T15:36Z).

## Checkpoint 2 — валидация, CRUD, публичная проекция, сервис (PARTIAL → DONE для чтения/создания)
- `validate.py` (civic-v1: даты, NaN/Infinity, геометрия в рамке Астаны, деньги с источником, plain text без HTML),
  `dto.py` (allowlist), `objects.py` (draft/publish/archive в одной транзакции с историей и публичной проекцией),
  `auth.py` (scrypt, сессии, CSRF, лимит входов), `service.py` (CivicService.handle + resolve_principal).
- Миграция 2: `civic_create_requests` (Idempotency-Key для повторной отправки формы).
- Проверка: `python -m pytest -q -p no:cacheprovider tests/civic/R02` → 80 passed.

## Следующий шаг
Тесты update/publish/409/истории/original_planned_end и auth (неверный пароль, истечение, logout, CSRF).
