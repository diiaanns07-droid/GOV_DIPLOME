# Раунд 15 — общий контракт (Birge «Бірге — вместе»)

Основа: сборка R01 **FINAL-4, код `a4937462`** (ветка `claude/sharp-dijkstra-0t87gl`). Пакет раунда — ветка
`claude/clever-hypatia-q6ts4g` (= FINAL-4 + `research/round-15/`). Идея и сцены — `IDEA.md`. Если старые документы
расходятся с этим файлом — для раунда 15 прав этот файл. Всё, что сказано в CONTRACT раунда 14 и не изменено здесь
(§3 категории, §4 цель жалобы, §6 тепловая карта, §8 точность), действует.

## 0. Цель и сценарий демо v2

**FINAL-5** к вечеру второго дня: одна сборка, в которой проходит сценарий v2 (IDEA.md §3) на ҚАЗ и РУС, 1366 / 1024 / 375:
- **Часть 1** — шаги 1–6 и сцена «Служба сообщила → Проверено жителями», как в FINAL-4 (регресс — R10);
- **Часть 2 «Бірге»** — сцены 7 «Двор вместе», 8 «Ведомства вместе», 9 «Буран» (кризисный штаб + хроника).
Главный зритель — акимат на ноутбуке. Жюри Gton кликает само — ни одного пустого экрана и ни одного противоречия в числах.

## 1. Ветки и последние поставки

- База — FINAL-4 `a4937462`. Роль работает в своей ветке сессии (или `claude/r15-<роль>`), не в `main` и не в ветке пакета.
- Если твой путь в FINAL-4 старее твоей последней поставки раунда 14 — сначала восстанови её путями
  (`git fetch origin <ветка> && git checkout <sha> -- <пути>`), запиши SHA в DELIVERY.json (`restored_from`).

| Роль | Ветка раунда 14 | В FINAL-4 | Новее FINAL-4 |
|---|---|---|---|
| R01 | claude/sharp-dijkstra-0t87gl | a4937462 | — |
| R02 | claude/r14-R02 | f62cc93 | — |
| R03 | claude/r14-R03 | 0164d64 | — (модель ONNX — на ноутбуке, не в Git) |
| R04 | claude/r14-R04 | 8e2b2ae | — |
| R05 | claude/r14-R05 | 82d47a07 | — |
| R06 | claude/r14-R06 | 2f749aeb | — |
| R07 | claude/r14-R07 | 913b18a3 | **fe209c56** (круги 5–6) + patches/R01_shell_closable_desktop.patch |
| R08 | claude/r14-R08 | d5719635 | — |
| R09 | claude/modest-shannon-0ki93p | 82056b7b | чекпойнт 280dab7a без DELIVERY — R09 решает сам |
| R10 | claude/r14-R10 | 656681ee | правка шага 3: research/round-14-results/R01/patches/R10_demo_flow_reference.patch |
| R11 | claude/r14-R11 | 2a30d7a2 | — |
| R12 | claude/tender-brahmagupta-ef5ztl | 016c93b5 | — |
| R13 | claude/r14-R13 | 0487f2a6 | — |
| R14 | claude/r14-R14 | 19715dbe | ветка 204f6500 (только STATUS) |
| R15 | claude/r14-R15 | 540b4d3c | — |

## 2. Кто какими путями владеет

Меняй только свои пути, свою папку `research/round-15-results/<R>/` и свой handoff
`research/handoffs/astana/<R>/round15/STATUS.md`. Нужна правка чужого — `INTEGRATION.txt` с минимальным patch в своей папке.

| Роль | Пути |
|---|---|
| R01 Интегратор и оболочка | `web/index.html`, `web/style.css`, `web/map.js`, `web/interface.js`, `web/civic/shell/`, `ui/web_server.py`, `run.bat`, `run.sh`, `run-city.bat`, `tests/civic/R01/` |
| R02 Демо-мир и данные | `ml/datasets/`, `ml/labeling/`, `web/labeling/`, `data/civic/astana/demo-world/`, `tests/civic/R02/` |
| R03 ИИ-аналитик акима | `agent/civic_assistant/`, `web/civic/assistant/`, `ml/civic_classifier_v2/` (только оценка и отчёты), `tests/civic/R03/` |
| R04 ИИ: службы, ответы, модерация | `ml/civic_dedup/`, `ml/civic_replies/`, `ui/civic_ml_api/`, `tests/civic/R04/` |
| R05 3D-Астана | `web/civic/build3d/`, `web/vendor/three/`, `data/civic/astana/landmarks/`, `tests/civic/R05/` |
| R06 Проекты, идеи, работы, уведомления | `ui/civic_store/`, `web/civic/proposals/`, `web/civic/ideas/`, `web/civic/notify/`, `tests/civic/R06/` |
| R07 Живая карта и хроника | `ui/civic_heat/`, `web/civic/heat/`, `web/civic/replay/`, `tests/civic/R07/` |
| R08 Картина дня и ситуационный центр | `ui/civic_akim/`, `web/civic/akim/`, `web/civic/nearby/`, `web/civic/board/`, `tests/civic/R08/` |
| R09 Обращения: несколько служб | `ui/civic_feedback/`, `web/civic/feedback/`, `tests/civic/R09/` |
| R10 Приёмка и демо-ролик | `tests/civic/R10/`, `tests/e2e/` |
| R11 UX, схема меню, ui-kit, ҚАЗ | `web/civic/ui-kit/`, `web/civic/i18n/`, `tests/civic/R11/` |
| R12 Карта и календарь работ | `engine/civic_geo/`, `data/civic/astana/geo/`, `web/civic/map/`, `web/civic/editor/`, `web/civic/qr/`, `web/civic/works-calendar/`, `tests/civic/R12/` |
| R13 Встречи, вопросы, прогноз | `ml/civic_forecast/`, `ui/civic_forecast/`, `ui/civic_qa/`, `web/civic/qa/`, `ui/civic_meetings/`, `web/civic/meetings/`, `tests/civic/R13/` |
| R14 Диплом, Gton, документы | `docs/birge/`, `docs/diploma/`, `docs/gton/` |
| R15 Безопасность и приватность | `tests/civic/R15/` (чужой код — только patch в INTEGRATION.txt) |
| R16 Бірге: жители (двор, инициативы) | `ui/civic_together/`, `web/civic/together/`, `tests/civic/R16/` |
| R17 Бірге: ведомства (штаб, кризис) | `ui/civic_agencies/`, `web/civic/agencies/`, `tests/civic/R17/` |
| LOCAL (Codex/владелец на ноутбуке) | `data/civic/astana/landmarks/raw/`, `research/round-15-results/LOCAL/` |

Заморожено: `engine/` (кроме `engine/civic_geo/`; `engine/civic_scenarios/` — только чтение), `agent/` (кроме
`agent/civic_assistant/`), `web/govtech/`, Шымкент, `legacy/`, `research/round-14/categories_v2.json` (правку категорий
предлагать R11 + владельцу).

## 3. Службы — один справочник

Идентификаторы служб уже совпадают в двух местах: `ui/civic_feedback/v2/lifecycle.py` `SERVICES` (R09) и таблица
маршрутизации R08 `GET /api/civic/v2/akim/routing` → `services`: `road, traffic, street_cleaning, transport, lighting,
landscaping, greenery, waste, utilities, heating, water, power, gas, housing, ecology, emergency, police, animals, parking,
akimat`. Новых id не придумывать. R17 делает **профиль службы** (вид, цвет, иконка, срок по умолчанию) поверх этих id;
названия ru/kk остаются в таблице R08. Реальные названия организаций и людей не использовать.

## 4. Цель жалобы и двор

Как в раунде 14 (§4): `{"kind": "object|segment|area", "id": …}`. Двор — `area` с `id = yard-<id>` (дворы R12 из OSM
`landuse=residential`). «Мой двор» и инициативы привязываются к той же цели. Нет двора — ячейка `cell-<id>` с пометкой
«примерное место».

## 5. Записи (новые поля и новые виды)

Общие правила: `id` — строка по правилу `CIVIC_ID` шлюза; время — ISO 8601 с поясом; `demo: true` у синтетики (интерфейс
пишет «Пример»); тексты жителей — только после модерации R04 (`moderation` как в раунде 14); никаких телефонов, ИИН,
e-mail и точных адресов квартир в публичных ответах.

**5.1 Жалоба v2.1 (R09, дополнение к §5 раунда 14)** — совместное исполнение и передачи:
```json
{
  "service": "water",
  "services": [
    {"service": "water", "role": "lead", "status": "done", "note": "Трубу заменили", "updated_at": "…"},
    {"service": "road", "role": "partner", "status": "in_progress", "updated_at": "…"}
  ],
  "handoffs": [{"at": "…", "from": "road", "to": "water", "reason": "Сначала нужна замена трубы", "by_role": "operator"}],
  "route_hint": {"services": ["water", "road"], "joint": true, "source": "model|rules", "model_version": "…"}
}
```
`service` (прежнее поле, ведущая служба) сохраняется для совместимости. Срок ответа жителю при передаче **не начинается
заново**. Статус всей жалобы — по ведущей службе; «исправлено» — когда все части `done`.

**5.2 Инициатива (R16)**
```json
{
  "id": "i-…", "kind": "cleanup|greening|snow|repair|help|other",
  "title": "Субботник во дворе", "text": "…", "lang": "ru|kk|mixed",
  "target": {"kind": "area", "id": "yard-123", "label_ru": "Двор у ул. Коксенгир", "label_kk": "…"},
  "point": [71.41, 51.10], "district": "nura",
  "starts_at": "…", "ends_at": "…", "bring": ["перчатки", "мешки"],
  "status": "on_review|published|done|cancelled|hidden",
  "joined": 15, "author_device": "(не отдаётся наружу)",
  "support": {"by_akimat": true, "inventory": true, "pickup_service": "waste", "note": "Мешки и вывоз в 14:00"},
  "report": {"text": "Убрали двор и посадили 6 саженцев", "photo_ids": ["p-…"], "at": "…"},
  "from_idea": "idea-…|null", "demo": true
}
```

**5.3 Двор (R16)** — `{"id": "yard-123", "label_ru", "label_kk", "district", "members": 37, "captain": {"display_name":
"Айгуль", "since": "…"} | null}`. Члены — только число; кто именно — не отдаётся никому. «Старший по двору» —
добровольно, отображаемое имя после модерации, снять можно одним действием.

**5.4 Профиль службы (R17)** — `{"id": "water", "kind": "utility|road|cleaning|transport|safety|social|admin",
"color": "#…", "icon": "ui-kit id", "sla_answer_days": 3, "sla_fix_days": 10}`.

**5.5 Кризис (R17)**
```json
{
  "id": "inc-…", "kind": "blizzard|heat_outage|water_outage|flood|other",
  "title_ru": "Буран", "title_kk": "Боран",
  "zone": {"kind": "district|targets|polygon", "district": "nura", "targets": ["yard-1"], "geometry": null},
  "started_at": "…", "status": "active|closed",
  "tasks": [{"id": "t-1", "service": "street_cleaning", "text_ru": "…", "text_kk": "…", "status": "todo|doing|done"}],
  "updates": [{"at": "…", "text_ru": "…", "text_kk": "…", "public": true}],
  "result": {"text_ru": "…", "text_kk": "…"} | null, "demo": true
}
```

**5.6 Работа v2 (R06 хранит, R12 привязывает и ищет конфликты)** — к записи работ раунда 14 добавить:
`"service": "water"`, `"kind": "dig|surface|closure|landscape|lighting|other"`, `"segments": ["osm-w123-4", …]`
(рёбра графа R12, форма — из OSM), `"starts_on": "2026-05-01"`, `"ends_on": "2026-05-20"`, `"source": "real|demo"`.
Конфликт (R12): `{"id": "cf-…", "kind": "dig_after_surface|parallel_closures|same_segment_overlap",
"works": ["w-1", "w-2"], "segments": […], "severity": "high|medium", "advice_ru": "…", "advice_kk": "…"}`.

**5.7 Встреча (R13)** — `{"id": "m-…", "district", "title_ru", "title_kk", "at", "place": {target},
"registered": 54, "questions": ["q-…"], "orders": [{"id": "o-1", "text_ru", "text_kk", "service", "due",
"status": "todo|in_progress|done", "link": {"kind": "complaint|work|project", "id": "…"}|null}], "demo": true}`.
Ведущий встречи — «аким района» без имени.

**5.8 Событие ленты уведомлений (каждый модуль → R06)** — `{"id", "at", "module": "R16|R17|R13|R09|R06",
"kind": "yard.news|initiative.update|incident.update|meeting.result|complaint.update|work.near",
"target": {…}, "title_ru", "title_kk", "link": "#together/i-…"}`. Модуль отдаёт свои события функцией `updates(device, since)`,
R06 собирает общую ленту — модули не пишут в чужие таблицы.

## 6. Тепловая карта и хроника

Формула и цвета — раунд 14 §6 (вес `0.5 ^ (возраст / 14)`, уровни `heat_levels`, «исправлено» 7 дней). Хроника (R07)
пересчитывает ту же формулу на каждую дату периода — никакой отдельной математики. Кадр хроники — тот же формат, что
`/heat`, плюс дата. Аннотации («Буран 12 окт») — только из событий демо-мира или кризисов R17.

## 7. HTTP API v2 — новые маршруты (всё под `/api/civic/v2/`)

Существующие маршруты FINAL-4 не меняются. **R01 в первый же час добавляет в `V2_ROUTES` / `V2_HANDLERS` все строки ниже**
— пока модуля нет, шлюз отвечает `503 module_not_ready` (так уже устроен FINAL-4). Роль, назвавшая функцию иначе, пишет
это в INTEGRATION.txt. Вид `service` = `make_service(db_path).handle(method, path, query, body, principal, context)` →
`{"status", "headers", "body"}`, как у R09 и R13. «Сотрудник» = сессия + CSRF, проверяет и шлюз, и модуль.

| Метод и путь | Роль | Модуль · функция (вид) | Кто может |
|---|---|---|---|
| `GET together/initiatives?bbox&status&kind&yard` | R16 | `ui.civic_together` · make_service (service) | все |
| `POST together/initiatives` | R16 | то же | житель (устройство), модерация R04 |
| `GET together/initiatives/{id}` | R16 | то же | все |
| `POST together/initiatives/{id}/join` · `/leave` | R16 | то же | житель |
| `POST together/initiatives/{id}/support` | R16 | то же | сотрудник |
| `POST together/initiatives/{id}/moderate` | R16 | то же | сотрудник |
| `POST together/initiatives/{id}/report` | R16 | то же | автор или сотрудник |
| `GET together/yards/{id}` | R16 | то же | все |
| `POST together/yards/{id}/join` · `/leave` | R16 | то же | житель |
| `GET together/updates?since` | R16 | то же | житель |
| `GET agencies` | R17 | `ui.civic_agencies` · make_service (service) | все |
| `GET agencies/board?days&district` | R17 | то же | сотрудник |
| `GET agencies/joint` · `GET agencies/handoffs?days` | R17 | то же | сотрудник |
| `GET incidents` · `GET incidents/{id}` | R17 | то же | все (публичная часть) |
| `POST incidents` · `POST incidents/{id}/task` · `POST incidents/{id}/update` · `POST incidents/{id}/close` | R17 | то же | сотрудник |
| `GET incidents/updates?since` | R17 | то же | житель |
| `POST complaints/{id}/handoff` | R09 | `ui.civic_feedback.v2.integration` · make_service (service) | сотрудник |
| `POST complaints/{id}/services` · `POST complaints/{id}/part` | R09 | то же | сотрудник |
| `GET works-calendar?from&to&district&street` | R12 | `engine.civic_geo.api` · handle (raw, strip_prefix) | сотрудник |
| `GET works-conflicts?from&to&district` | R12 | то же | сотрудник |
| `GET heat/replay?from&to&step&category&district` | R07 | `ui.civic_heat.api` · handle_get (raw) | все (мягкий вид) |
| `GET akim/board` · `GET akim/week?date` | R08 | `ui.civic_akim.api` · handle_get (raw) | сотрудник |
| `GET meetings` · `GET meetings/{id}` · `GET meetings/updates?since` | R13 | `ui.civic_meetings` · make_service (service) | все |
| `POST meetings` · `POST meetings/{id}/order` · `POST meetings/{id}/result` | R13 | то же | сотрудник |
| `POST meetings/{id}/register` · `POST meetings/{id}/question` | R13 | то же | житель |
| `POST route` | R04 | `ui.civic_ml_api` · route (function) | все |
| `POST reply-draft` | R04 | `ui.civic_ml_api` · reply_draft (function) | сотрудник |
| `POST moderate` | R04 | `ui.civic_ml_api` · moderate (function) | все (предпросмотр) |
| `POST assistant/ask` | R03 | `agent.civic_assistant.api` · ask (function) | сотрудник |
| `GET notifications?since` · `POST notifications/read` | R06 | `ui.civic_store.v2` · list_notifications / read_notifications (function) | житель |
| `POST ideas/{id}/to-initiative` | R06 | `ui.civic_store.v2` · idea_to_initiative (function, вызывает функцию R16) | сотрудник |

Житель определяется как в R09: заголовок `X-Birge-Device` (запасной вариант — `device_id` в теле). Лимиты частоты —
по образцу R15 (жалобы 5/мин, голоса 20/сутки): для `join`, `register`, `question`, создания инициатив — свои лимиты
в модуле + общий лимит шлюза.

**Вызовы между модулями** — только чтением и только через функции соседа с запасным вариантом (модуля нет → пустой блок
«пока нет данных», а не ошибка): R16 читает R09 (жалобы двора), R07 (уровень), R06 (идеи, работы); R17 читает R09
(части служб, передачи) и R08 (названия служб); R08 читает R16/R17/R13 для ситуационного центра; R12 читает работы R06;
R06 собирает `updates()` R16/R17/R13/R09. Писать в чужие таблицы нельзя.

## 8. Карта

- Точность — раунд 14 §8 без исключений: участки работ и конфликтов — только рёбрами графа OSM; зона кризиса — район,
  дворы или цели; полигон «от руки» — только с подписью «примерная зона».
- **Слои** — через `BirgeShell.registerLayer` (R01). По умолчанию на карте только тепловая карта объектов и работы.
  Новые слои («Инициативы» R16, «Кризис» R17, «Конфликты работ» R12, «Ориентиры» R05) включаются переключателем;
  одновременно — максимум один дополнительный слой.
- **Разделы** — через `BirgeShell.registerScreen({id, mount, modes, titleKey})`; место в меню решает R11 (схема IA_ROUND15),
  R01 ставит. Модуль экрана: `window.<Имя>.mount(root, опции) → {destroy?, setLang?}`.

## 9. Интерфейс и тексты

Правила — `research/round-14/UX_BRIEF.md`, эталон — `research/round-14/design/` (вариант A + качество Linear),
визуальная планка раунда — `research/round-15/VISUAL_BRIEF.md`. Весь видимый текст — ключи R11 (`web/civic/i18n/ru.json`,
`kk.json`); новые ключи роль передаёт R11 в INTEGRATION (запасной текст — в модуле, как `shell-text.js` у R01). Проверка
на 375, 1024 и 1366 px, ҚАЗ и РУС, все состояния (загрузка, пусто, ошибка, успех).

## 10. Приватность и безопасность (обязательно)

- Членство в дворе и «Я приду» — только числа; устройства и время не отдаются наружу.
- Тексты инициатив, вопросов и обновлений — модерация R04 (мат, телефоны, ИИН, e-mail) до публикации; автор видит «на проверке».
- Фото — правила R09 раунда 14 (уменьшение, удаление EXIF и GPS, только сотрудник видит фото жалоб; фото «после» инициативы
  публичное — без людей крупным планом, подсказка автору).
- Действия сотрудника — сессия + CSRF; журнал передач и действий в штабе (кто — роль, а не имя).
- R15 проверяет всё новое; найденное — patch в INTEGRATION.txt владельцу пути.

## 11. Демо-мир (R02)

- Файл `data/civic/astana/demo-world/world_v1.json` (+ `DATASHEET.md`) — **один** детерминированный синтетический месяц:
  `complaints`, `works`, `ideas`, `initiatives`, `yards`, `incidents`, `meetings`, `questions`, `scenes`.
- Время — **относительно момента засева** (`ago_days`, `ago_hours`, `in_days`): демо всегда «свежее» в день показа.
- `scenes` — стабильные id для сцен 7–9 (двор, инициатива, жалоба «яма после раскопок», конфликт работ, кризис).
- Каждый модуль добавляет функцию `seed_world(db_path, records, now=None) -> {"inserted", "skipped"}` (идемпотентно)
  и берёт только свою часть. R01 вызывает их при `CIVIC_DEMO=1` и `CIVIC_DEMO_WORLD=1`; без флага — прежнее демо FINAL-4.
- Пока демо-мира нет — роли работают на своих фикстурах строго в форматах §5.

## 12. Сдача работы

В `research/round-15-results/<R>/`: `DELIVERY.json` (role, branch, base_sha, restored_from, code_sha, tested_sha,
push_status, changed_paths, tests PASS/FAIL/NOT_RUN, screens, known_limits, next_step), `RUN.txt`, `INTEGRATION.txt`.
Handoff: `research/handoffs/astana/<R>/round15/STATUS.md`. Checkpoint с push каждые 30–40 минут и около 85% лимита.
