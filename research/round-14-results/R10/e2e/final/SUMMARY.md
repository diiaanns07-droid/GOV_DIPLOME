# R10 · приёмка FINAL-candidate-85c16e2 · сборка a8e05d0

Папка сборки: <worktree a8e05d0>
Когда: 2026-10-10T19:40:25.229Z · Node v22.22.0 · Python: python3

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

PASS 131 · FAIL 5 · NOT_RUN 0 — подробно e2e/RESULT.md

| Шаг | PASS | FAIL | NOT_RUN |
|---|---|---|---|
| * | 4 | 0 | 0 |
| 0 | 27 | 2 | 0 |
| 1 | 16 | 0 | 0 |
| 2 | 17 | 0 | 0 |
| 3 | 10 | 0 | 0 |
| 4 | 5 | 0 | 0 |
| 5 | 30 | 0 | 0 |
| 6 | 10 | 3 | 0 |
| E | 12 | 0 | 0 |
- FAIL UI 1366-kk шаг 6: акимат: карточка остановки → «Взять в работу» → «Отметить исправленным» → «Түзетілді», зелёным на карте
- FAIL UI 375-ru шаг 6: акимат: карточка остановки → «Взять в работу» → «Отметить исправленным» → «Исправлено», зелёным на карте
- FAIL UI 375-kk шаг 0: ҚАЗ: на экране нет строк, оставшихся по-русски
- FAIL UI 375-kk шаг 0: ҚАЗ: во всей странице (с прокруткой панелей) нет строк по-русски
- FAIL UI 375-kk шаг 6: акимат: карточка остановки → «Взять в работу» → «Отметить исправленным» → «Түзетілді», зелёным на карте

## 4. UX по экранам (tests/e2e/ux_screens.cjs)

PASS 88 · FAIL 6 · NOT_RUN 8 — подробно ux/UX_RESULT.md
- FAIL [R01] Главная карта · житель 375 kk: казахский полный — на экране (нет русских строк)
- FAIL [R01] Главная карта · житель 375 kk: казахский полный — вся страница с прокруткой панелей
- FAIL [R01] Главная карта · акимат 375 kk: казахский полный — на экране (нет русских строк)
- FAIL [R01] Главная карта · акимат 375 kk: казахский полный — вся страница с прокруткой панелей
- FAIL [R01+R08] Картина дня (в оболочке) 375 kk: казахский полный — на экране (нет русских строк)
- FAIL [R01+R08] Картина дня (в оболочке) 375 kk: казахский полный — вся страница с прокруткой панелей
