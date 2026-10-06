# R04 — Кабинет редактора и публикация изменений (раунд 11, Астана)

- Роль: R04 (назначена промптом пользователя, не по имени ветки)
- Ветка: `claude/fervent-ritchie-1zih1y`
- Исходный HEAD ветки: `834a25fb860dd5514d02c9274b70d7bf8a53a79c`
- PACK_SHA (origin/codex/govtech-main-interface при старте): `9c2f5c0dae14b46c0697a9dfc7f854351bfd570d`
- Исходники приложения для сравнения: `6de3f253d8ec0743450259f9f13722c16cd36099` (CODE_SHA сборщика), читались через `git show`
- Собственные пути: `web/civic/editor/`, `tests/civic/R04/`, `research/round-11-results/R04/`, этот файл

## Состояние: PARTIAL (checkpoint 2)

Сделано:
- `web/civic/editor/editor-core.js` — чистая логика без DOM/сети: модель формы ↔ объект civic-v1,
  проверки полей (ошибка привязана к полю, текст формы не меняется), «было/станет», правила обязательной
  причины, матрица draft/published/archived, allowlist публичного предпросмотра, нормализация ошибок API,
  3-way merge для 409 и восстановления из памяти, поиск дубликата после обрыва связи при создании.
- `tests/civic/R04/core.test.cjs` — 17 контрактных проверок (node:test).
- `tests/civic/R04/fixtures/civic_object.json` — байтовая копия fixture из PACK_SHA.

- `web/civic/editor/editor.js` + `editor.css` — `window.CivicEditor.mount({root,map,api,onPublished}) -> {openObject,destroy}`:
  вход/выход, список, форма из 5 разделов, точка/линия на общей карте, источники, предпросмотр карточки жителя,
  публикация/архив с причиной, история, 409/401/сеть/двойное нажатие, память несохранённых правок (только RAM).
- `tests/civic/R04/contract_mock.cjs` (+ тест) — контрактный mock civic-v1 (НЕ R02), `stand.cjs`, `harness/`.

Проверено:
- `node --test tests/civic/R04/*.test.cjs` → 26 pass, 0 fail (Node v22.22.0).
- Ручной smoke в headless Chromium (Playwright 1.56.1): вход → список → новый объект рендерится, карта MapLibre 5.6.2 загружена (software WebGL, без подложки).

Не запускалось: полный браузерный walkthrough (следующий шаг), R02 (не опубликован).

Следующий шаг: `tests/civic/R04/e2e.test.cjs` — сценарии приёмки в браузере + screenshots 390/1280.
