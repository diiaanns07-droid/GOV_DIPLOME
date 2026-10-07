# R04 — Кабинет сотрудника (раунд 12)

- Роль: R04. Ветка: `claude/intelligent-sagan-7shpeh` (origin https://github.com/diiaanns07-droid/GOV_DIPLOME).
- CODE_BASE_SHA: `56538a3a7504d4589c38ab4d3c5107f12aa7f8a6` (codex/govtech-main-interface). Пакет раунда 12: `19f90e6`.
- Основа ветки: обычный merge `56538a3` в ветку сессии (563282a), без reset/force push. После merge дерево = 56538a3
  + старый handoff R05 (`research/handoffs/astana/R05/round-11/STATUS.md`). Сравнение изменений R04: `git diff 56538a3 HEAD -- web/civic/editor tests/civic/R04`.
- Пути: `web/civic/editor/`, `tests/civic/R04/`, `research/round-12-results/R04/`, этот файл.

## Checkpoint 1 — PARTIAL

Исправлено: потеря заполненной формы при перезагрузке/падении вкладки. Раньше несохранённые правки жили только
в памяти страницы (RECOVERY) — F5, случайный переход или сбой вкладки уничтожали форму. Теперь копия формы
пишется в sessionStorage этой вкладки (через 0.6 с после правки): только поля формы, без пароля/токенов/CSRF,
привязана к пользователю сервера, удаляется после успешного сохранения, по «Удалить из памяти» и при выходе.
В интерфейсе подписано: «локальная копия, не на сервере».

Проверки (рабочее дерево checkpoint 1):
- `node --test tests/civic/R04/core.test.cjs` → 18/18 PASS.
- `node --test tests/civic/R04/e2e.test.cjs` (контрактный mock, Chromium из /opt/pw-browsers, Playwright из /opt/node-tools)
  → 18/18 PASS до нового теста; новый тест «round 12: … survives a page reload …» PASS.

Следующий шаг: поток «тип → место → сроки → стоимость/ответственный → источник → предпросмотр», явный выбор
«место точно / приблизительно / неизвестно», рисование участка-полигона.
