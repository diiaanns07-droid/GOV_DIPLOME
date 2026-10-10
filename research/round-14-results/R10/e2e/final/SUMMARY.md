# R10 · приёмка FINAL-candidate-1dd5b53 · сборка 3b3e4f2

Папка сборки: <worktree 3b3e4f2>
Когда: 2026-10-10T19:53:34.015Z · Node v22.22.0 · Python: python3

## 1. Точность карты (CONTRACT §8)

PASS 29 · FAIL 0 · NOT_RUN 0 (pytest код 0)


## 2. Сервер сборки

запущен на http://127.0.0.1:<порт>/; CIVIC_DEMO=1; база: init:0, seed-demo:0, seed-r14-demo:0; сотрудник: создан

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

PASS 133 · FAIL 2 · NOT_RUN 1 — подробно e2e/RESULT.md

| Шаг | PASS | FAIL | NOT_RUN |
|---|---|---|---|
| * | 4 | 0 | 0 |
| 0 | 27 | 2 | 0 |
| 1 | 16 | 0 | 0 |
| 2 | 17 | 0 | 0 |
| 3 | 10 | 0 | 0 |
| 4 | 5 | 0 | 0 |
| 5 | 30 | 0 | 0 |
| 6 | 12 | 0 | 1 |
| E | 12 | 0 | 0 |
- FAIL UI 375-kk шаг 0: ҚАЗ: на экране нет строк, оставшихся по-русски
- FAIL UI 375-kk шаг 0: ҚАЗ: во всей странице (с прокруткой панелей) нет строк по-русски

## 4. UX по экранам (tests/e2e/ux_screens.cjs)

PASS 88 · FAIL 6 · NOT_RUN 8 — подробно ux/UX_RESULT.md
- FAIL [R01] Главная карта · житель 375 kk: казахский полный — на экране (нет русских строк)
- FAIL [R01] Главная карта · житель 375 kk: казахский полный — вся страница с прокруткой панелей
- FAIL [R01] Главная карта · акимат 375 kk: казахский полный — на экране (нет русских строк)
- FAIL [R01] Главная карта · акимат 375 kk: казахский полный — вся страница с прокруткой панелей
- FAIL [R01+R08] Картина дня (в оболочке) 375 kk: казахский полный — на экране (нет русских строк)
- FAIL [R01+R08] Картина дня (в оболочке) 375 kk: казахский полный — вся страница с прокруткой панелей
