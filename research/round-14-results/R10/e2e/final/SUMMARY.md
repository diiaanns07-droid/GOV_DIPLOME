# R10 · приёмка FINAL-candidate-8e67c65 · сборка 8e67c65

Папка сборки: /home/user/n11
Когда: 2026-10-11T00:07:59.831Z · Node v22.22.0 · Python: python3

## 1. Точность карты (CONTRACT §8)

PASS 29 · FAIL 0 · NOT_RUN 0 (pytest код 0)


## 2. Сервер сборки

запущен на http://127.0.0.1:33837/; CIVIC_DEMO=1; база: init:0, seed-demo:0, seed-r14-demo:0; сотрудник: создан

| Маршрут v2 | Роль | Статус |
|---|---|---|
| classify | R04 | ready |
| similar | R04 | ready |
| targets | R12 | ready |
| complaints.categories | R09 | ready |
| complaints.list | R09 | ready |
| complaints.create | R09 | ready |
| complaints.mine | R09 | ready |
| complaints.events | R09 | ready |
| complaints.summary | R09 | ready |
| complaints.place | R09 | ready |
| complaints.get | R09 | ready |
| complaints.metoo | R09 | ready |
| complaints.status | R09 | ready |
| complaints.duplicate | R09 | ready |
| heat | R07 | ready |
| heat.meta | R07 | ready |
| heat.target | R07 | ready |
| akim.summary | R08 | ready |
| geo.segment | R12 | ready |
| geo.snap | R12 | ready |
| geo.objects | R12 | ready |
| geo.yard | R12 | ready |
| geo.status | R12 | ready |
| proposals.list | R06 | ready |
| proposals.create | R06 | ready |
| proposals.summary | R06 | ready |
| proposals.get | R06 | ready |
| proposals.vote | R06 | ready |
| proposals.approve | R06 | ready |
| proposals.reject | R06 | ready |
| proposals.withdraw | R06 | ready |
| objects.list | R06 | ready |
| objects.lagging | R06 | ready |
| objects.get | R06 | ready |
| objects.stage | R06 | ready |
| objects.stage.get | R06 | ready |
| forecast | R13 | ready |

## 3. Сценарий демо (tests/e2e/demo_flow.cjs)

PASS 160 · FAIL 4 · NOT_RUN 0 — подробно e2e/RESULT.md

| Шаг | PASS | FAIL | NOT_RUN |
|---|---|---|---|
| * | 4 | 0 | 0 |
| 0 | 39 | 2 | 0 |
| 1 | 16 | 0 | 0 |
| 2 | 17 | 0 | 0 |
| 3 | 14 | 0 | 0 |
| 4 | 5 | 0 | 0 |
| 5 | 36 | 2 | 0 |
| 6 | 17 | 0 | 0 |
| E | 12 | 0 | 0 |
- FAIL UI 1366-ru шаг 0: контраст текста ≥ 4.5:1 (крупный ≥ 3:1), UX_BRIEF правило 2
- FAIL UI 1366-kk шаг 0: контраст текста ≥ 4.5:1 (крупный ≥ 3:1), UX_BRIEF правило 2
- FAIL UI 375-ru шаг 5: после «Поставить» проект виден: место на карте не закрыто сообщением или каталогом
- FAIL UI 375-kk шаг 5: после «Поставить» проект виден: место на карте не закрыто сообщением или каталогом

## 4. UX по экранам (tests/e2e/ux_screens.cjs)

PASS 124 · FAIL 6 · NOT_RUN 8 — подробно ux/UX_RESULT.md
- FAIL [R01] Главная карта · житель 1366 ru: контраст текста ≥ 4.5:1 (крупный ≥ 3:1)
- FAIL [R01] Главная карта · житель 1366 kk: контраст текста ≥ 4.5:1 (крупный ≥ 3:1)
- FAIL [R01] Главная карта · акимат 1366 ru: контраст текста ≥ 4.5:1 (крупный ≥ 3:1)
- FAIL [R01] Главная карта · акимат 1366 kk: контраст текста ≥ 4.5:1 (крупный ≥ 3:1)
- FAIL [R01+R08] Картина дня (в оболочке) 1366 ru: контраст текста ≥ 4.5:1 (крупный ≥ 3:1)
- FAIL [R01+R08] Картина дня (в оболочке) 1366 kk: контраст текста ≥ 4.5:1 (крупный ≥ 3:1)
