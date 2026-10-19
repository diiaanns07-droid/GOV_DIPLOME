# R09 · дефекты из LOCAL_FINAL.md (Codex, Windows, FINAL 8e67c65) — исправлены

Источник: `research/round-14-results/LOCAL/LOCAL_FINAL.md` в `claude/round-14-package` (2c3f559), раздел «Оставшиеся проблемы».
Исправление: `claude/modest-shannon-0ki93p` @ **437c5f3** (пути R09: `ui/civic_feedback/v2/api.py`, `web/civic/feedback/complaint.js`).

| № | Что было (как у Codex) | Причина | Исправление |
|---|---|---|---|
| 1 (P1) | Сотрудник вошёл заранее → «Житель» → Хан Шатыр → «Отправить»: вместо «Об этом уже сообщили N человек» сразу «Обращение отправлено» (новая B-0003) | при сессии сотрудника `GET /complaints/{id}` отдавал ответ для сотрудника — без поля `reporters`; мастер проверял `match.reporters > 0` | мастер жителя просит `GET /complaints/{id}?view=public` (тот же ответ, что любому жителю, права не расширяются) и считает людей надёжно: `reporters`, иначе `1 + metoo`; ответ сотруднику тоже содержит `reporters` |
| 2 (P2) | «У меня другое» → успех → сразу Escape: `Cannot read properties of null (reading 'text')` (4 исключения) | таймер подсказки `/classify` (0,7 с), запущенный при перерисовке шага ③ во время отправки, срабатывал после закрытия, когда `state = null` | `close()` отменяет таймер; каждый ответ сети (`/targets`, `/classify`, `/similar`, отправка, «Я тоже», «Мои обращения», геолокация) проверяет, что мастер всё тот же |

## Проверки
| Где | Что | Результат |
|---|---|---|
| Настоящее приложение: FINAL R01 `a2d90dd` + пути R09 @ 437c5f3, свежая демо-база, реальный вход сотрудника R02 | `node tests/civic/R09/app_demo_r09.cjs --root <дерево>` — основной сценарий 4 варианта + «вход заранее» 375 ru и 1366 kk + «У меня другое → сразу Escape» | **71/71** (`APP_RESULT_LOCAL_FINAL.txt`): «вход заранее» — «Об этом уже сообщили 3 человека», «Я тоже» → 4 |
| То же дерево, но R09 как в FINAL (без исправления) | `R09_ONLY_LOCAL=1 node tests/civic/R09/app_demo_r09.cjs` | **6 FAIL** — ровно дефекты Codex (`APP_RESULT_LOCAL_FINAL_BEFORE_FIX.txt`) |
| Стенд R09, Chromium, 375/1366 × ru/kk | `node tests/civic/R09/browser_r09.cjs` (сценарии `staff-first`, `quick-close` + прежние) | **212/212** (`BROWSER_RESULT.txt`) |
| pytest | `test_staff_session_does_not_hide_people_count_from_resident_wizard` | PASS |

Скриншоты: `screens-local-final/` (шаг «Я тоже» при входе сотрудника, 375 ru и 1366 kk).

## Для R01
Взять пути R09 из `claude/modest-shannon-0ki93p` @ 437c5f3 (ночная ветка `claude/wizardly-ptolemy-qy8ltw` больше не обновляется —
её код перенесён сюда побайтно в 38e6d67):
    git fetch origin claude/modest-shannon-0ki93p
    git checkout 437c5f3 -- ui/civic_feedback web/civic/feedback
Маршруты шлюза менять не нужно (параметр `view=public` идёт в query). После этого DEMO_SCRIPT можно снова начинать со входа
сотрудника — обход «войти на шаге 5» больше не обязателен.
Примечание: в этом коммите уже есть серверная часть волн 1–2 (новые поля и маршруты — совместимо со старыми вызовами,
прежний сценарий 71/71 на приложении); новые маршруты волн для шлюза — в INTEGRATION.txt (раздел «Волны»), когда будет фронтенд.
