# Демо-мир Астаны · схема `birge-demo-world-v1`, версия 1.0.1 (R02, раунд 15)

Один синтетический месяц-два Астаны, из которого **каждый модуль берёт свою часть** — тогда числа на карте, в
«Обращениях», в «Картине дня», на табло служб и в «Моём дворе» совпадают (CONTRACT §11). Записи — строго в форматах
CONTRACT §5 (раунд 15) и §5 раунда 14; ниже — только то, что добавляет или уточняет мир.

| Файл | Что это |
|---|---|
| `world_v1.json` | полный мир (генерирует `python3 -m ml.datasets.demo_world`, seed 15, без сети) |
| `world_v1.sample.json` | образец: 10–20 записей каждого вида **из того же генератора**, тот же формат — для тестов ролей |
| `EXPECTED.json` | числа, которые должны получиться на экранах при опорном `now` (считает генератор, сверка R10) |
| `DATASHEET.md` | что синтетическое, как сгенерировано, распределения, ограничения (для диплома) |
| `SCHEMA.md` | этот файл |

Помощник для модулей (только стандартная библиотека, без сети): `ml/datasets/demo_world_io.py`

```python
from ml.datasets.demo_world_io import load_world, materialize
world = load_world()                       # world_v1.json (или путь; переменная CIVIC_DEMO_WORLD_PATH)
part = materialize(world, now)["complaints"]   # абсолютные ISO-времена (+05:00) от момента засева
```

## 0. Правила для всех

- **Всё синтетическое**: у каждой записи `demo: true` (интерфейс пишет «Пример / Үлгі»). Реальные — только цели
  (объекты, участки улиц, дворы OpenStreetMap, ODbL) и, если будут, работы из `data/civic/astana/nura-real/records.csv`
  (`source: "real"`, без `demo`). Тексты жителей придуманы по шаблонам R02 `ml/datasets/synth_v3/templates.py`.
- **Нет личных данных**: в текстах нет телефонов, ИИН, e-mail, номеров квартир, ФИО. У «старших по двору» — только
  выдуманное отображаемое имя (одно слово). Устройств в мире нет: модуль сам делает синтетические хэши (п. 2.3).
- **id** проходят правило шлюза `CIVIC_ID` = `^[A-Za-z0-9][A-Za-z0-9._:-]{0,95}$` и правила модулей (жалоба —
  `^c-[A-Za-z0-9]{6,40}$`). Префиксы мира: `c-w…`, `w-w15-…`, `idea-w15-…`, `i-w15-…`, `inc-w15-…`, `m-w15-…`,
  `q-w15-…`, `ev-w15-…`, `cf-w15-…`. Исключение — 2 жалобы «Хан Шатыр» шага 2 демо FINAL-4: их id совпадают с
  `ui/civic_feedback/v2/demo_seed.py` (`c-demo<sha16>`), чтобы оба засева не дублировали друг друга.
- **Районы**: `nura, esil, almaty, saryarka, baikonur, saraishyk` (как у R06/R07/R08). Службы — только id из CONTRACT §3.
  Категории и уточнения — только `research/round-14/categories_v2.json`.
- **Цели** (CONTRACT §4): `{"kind": "object|segment|area", "id", "label_ru", "label_kk", "object_kind"?}`;
  подписи взяты у R12 `engine.civic_geo.target_geometry()` — те же, что покажет карточка.

## 1. Время — относительно момента засева

В файле нет абсолютных дат. Любое поле времени из CONTRACT §5 записано **объектом относительного времени**:

| Объект | Значит | Превращается в |
|---|---|---|
| `{"ago_hours": 30.5}` | 30,5 ч назад | мгновение ISO 8601 `2026-10-15T10:01:00+05:00` |
| `{"in_hours": 42}` | через 42 ч | мгновение |
| `{"ago_days": 3.25}` / `{"in_days": 2}` | назад / вперёд на N суток (дробь можно) | мгновение |
| `{"day": -12}` | дата: сегодня (по Астане) − 12 дней | дата `YYYY-MM-DD` |
| `{"season": {"month": 5, "day": 4}}` | дата в **следующем строительном сезоне**: год = текущий, если сейчас январь–март, иначе следующий | дата |
| `{"next_weekday": {"weekday": 5, "hour": 10, "minute": 0}}` | ближайшая суббота (пн = 0 … вс = 6) в 10:00 по Астане, но не раньше чем через 12 ч | мгновение |

`materialize(world, now)` заменяет каждый такой объект на строку (мгновение — по Астане, секунды без долей; дата — по
календарю Астаны). Строки, уже абсолютные, не трогает — можно звать дважды. `now` по умолчанию — сейчас.
**R01 передаёт всем модулям один и тот же `now`** (момент запуска сервера), иначе «сегодня» у модулей разойдётся.

`season` — только у работ следующего сезона (асфальт в мае, сети в июле — сцена 8): так «копаем дважды» всегда
выглядит правдоподобно (асфальт не попадает на зиму), в какой бы день ни шёл показ.

## 2. Вид записей (ключи верхнего уровня)

```json
{
  "schema": "birge-demo-world-v1", "schema_version": "1.0.1", "seed": 15, "synthetic": true,
  "generator": "ml/datasets/demo_world.py", "inputs": {"…": "sha256 входных файлов"},
  "counts": {"complaints": 812, "…": 0},
  "districts": [...], "services": [...],
  "events": [...], "yards": [...], "complaints": [...], "works": [...], "planned_conflicts": [...],
  "ideas": [...], "initiatives": [...], "incidents": [...], "meetings": [...], "questions": [...],
  "scenes": {...}
}
```

| Ключ | Кто берёт (`seed_world`) | Формат |
|---|---|---|
| `complaints` | **R09** (хранилище жалоб); R07, R08, R16, R17 читают их **у R09**, не из файла | §2.3 |
| `works` | **R06** (хранит), R12 привязывает и ищет конфликты | §2.4 |
| `planned_conflicts` | R12 (сверка: его поиск должен найти эти конфликты), R10 | §2.5 |
| `ideas` | **R06** | §2.6 |
| `yards`, `initiatives` | **R16** | §2.2, §2.7 |
| `incidents` | **R17** | §2.8 |
| `meetings`, `questions` | **R13** | §2.9, §2.10 |
| `events` | R07 (подписи хроники «Буран 12 окт»), R08 (пульс), R17 | §2.1 |
| `services` | справка: id, ru, kk (= таблица R08/R09); профили служб делает R17 | — |
| `scenes` | R01 (палитра «сцены»), R10, R14 | §3 |

### 2.1 Событие мира (`events`)
`{"id": "ev-w15-buran", "kind": "blizzard|snow|ice|season", "title_ru": "Буран в Нуре", "title_kk": "Нұрада боран",
"district": "nura" | null, "started_at": {"ago_hours": 70}, "ended_at": {"ago_hours": 3} | null, "demo": true}` —
источник аннотаций хроники и кризиса (имена полей времени — как у кризиса §5.5). Жалобы, вызванные событием, помечены
`"event": "ev-w15-buran"`.

### 2.2 Двор (`yards`, CONTRACT §5.3)
`{"id": "yard-1026285032", "osm": "osm-way-1026285032", "label_ru", "label_kk", "district", "point": [lon, lat],
"members": 37, "captain": {"display_name": "Айгуль", "since": {"ago_days": 40}} | null, "demo": true}`.
Только дворы R12 (`data/civic/astana/geo/yards.json`, OSM `landuse=residential`). `members` — число (кто — нигде нет).

### 2.3 Жалоба (`complaints`, R09 v2 раунд 14 + v2.1 §5.1)
Ровно запись R09 (`ui/civic_feedback/v2/record.py`, `schema: "civic-complaint-v2"`), времена — относительные:

```json
{
  "id": "c-w15a00042", "schema": "civic-complaint-v2", "created_at": {"ago_hours": 30.5},
  "text": "…", "lang": "ru|kk|mixed", "category": "roads", "subtopic": "pothole" | null,
  "category_source": "resident|model", "model": {"label", "score", "version": "demo-world-v1", "needs_review"} | null,
  "point": [lon, lat], "target": {"kind", "id", "label_ru", "label_kk", "object_kind"?}, "district": "nura",
  "status": "new|accepted|in_progress|fixed|rejected",
  "status_history": [{"at": {"ago_hours": 30.5}, "status": "new"}, …, {"at": …, "status": "in_progress", "reopened_by_residents": true}],
  "metoo": 3, "metoo_times": [{"ago_hours": 29.1}, …],
  "duplicate_of": null, "demo": true,
  "service": "water",
  "services": [{"service": "water", "role": "lead", "status": "done", "note": "…", "updated_at": {…}},
               {"service": "road", "role": "partner", "status": "in_progress", "updated_at": {…}}],
  "handoffs": [{"at": {…}, "from": "road", "to": "water", "reason": "…", "by_role": "operator"}],
  "route_hint": {"services": ["water", "road"], "joint": true, "source": "rules", "model_version": null},
  "passport": {"assignee_id": "road", "next_step": "…", "fix_eta": {"day": 6},
               "delay": {"reason_code": "needs_decision", "needs_decision": true, "problem_ru/kk", "blocker_ru/kk",
                         "options": [{"ru", "kk"}, {"ru", "kk"}], "decision_ru/kk", "temp_measure_ru/kk"}},
  "resolution": {"round": 1, "state": "reported|verified|reopened", "reported_at": {…}, "what_done": "…",
                 "by": "service", "photos_after": [], "votes": {"yes": 2, "no": 0, "cant": 0},
                 "verified_at": {…} | null, "reopened_at": {…} | null, "reopen_count": 0},
  "updates": [{"at": {…}, "kind": "fixed|reopened|passport|note", "text": "…"}],
  "event": "ev-w15-buran" | null, "scene": "scene8" | null
}
```

- `service` — ведущая служба (таблица R09 `lifecycle.default_service` = умолчания R08), есть у **всех** жалоб.
  `services`, `handoffs`, `route_hint` — только у совместных (~5 %: 2 службы). Статус части: `new|accepted|in_progress|done`.
  Статус жалобы = статус ведущей части; `fixed` — только когда все части `done`. Срок ответа при передаче не
  начинается заново (в мире `created_at` не меняется).
- `resolution` — у части исправленных: `verified` (~10 % всех жалоб — «проверено жителями»), `reported`
  (служба сообщила, ждёт проверки), у «вернули жители» — `reopened` + шаг истории с `reopened_by_residents: true`.
- `metoo` = длина `metoo_times`. Людей у жалобы = `1 + metoo` (R07 `people`, R09 `reporters`).
- **Нет в мире** (ставит R09 при засеве): `code` (номер `B-0001` — `_next_code`), `due_at` (срок ответа в рабочих днях
  РК — `record.due_at(created_at, category)`), хэши устройств. Устройство «Я тоже» №n жалобы:
  `sha256("demo-world-v1:" + id + ":" + n)` (hex) — одинаково при каждом засеве.

### 2.4 Работа (`works`, CONTRACT §5.6 + поля «Рядом» раунда 14)
```json
{
  "id": "w-w15-007", "type": "work", "service": "water", "kind": "dig|surface|closure|landscape|lighting|other",
  "segments": ["osm-w123-4", "osm-w123-5"], "street_ru": "улица …", "street_kk": "… көшесі", "district": "nura",
  "starts_on": {"day": -12} | {"season": {…}}, "ends_on": {"day": 6},
  "status": "planned|in_progress|done", "work_kind": "roadworks|construction|landscaping|lighting|event|other",
  "title_ru", "title_kk", "why": {"problem_ru", "problem_kk", "reason_ru", "reason_kk", "result_ru", "result_kk",
  "inconvenience_ru", "inconvenience_kk"},
  "geometry": {"type": "MultiLineString", "coordinates": [...]}, "length_m": 412,
  "source": "demo" | "real", "demo": true, "scene": "scene8" | null
}
```
Участки — только рёбра графа R12 (`osm-w<way>-<n>`), форма `geometry` — из того же графа (OSM, ODbL). `status` выведен
из дат (до начала — planned, после конца — done) и записан для совместимости с «Рядом» R06/R08. Есть и несколько
отключений `"type": "outage"` (`utility: water|heating|power|gas|road_closure`, `starts_at`, `ends_at` — мгновения,
`zone_ru/kk`) — как в «Рядом» раунда 14. Реальные работы (если владелец положит `nura-real/records.csv`) —
`source: "real"`, без `demo`, только поля из файла.

### 2.5 Задуманные конфликты (`planned_conflicts`)
`{"id": "cf-w15-01", "kind": "dig_after_surface|parallel_closures|same_segment_overlap", "works": ["w-…", "w-…"],
"segments": [...], "severity": "high|medium", "advice_ru", "advice_kk", "demo": true}` — формат конфликта R12 §5.6.
Это **ожидание** для проверки: свой поиск R12 должен найти их на тех же участках (может найти и больше).

### 2.6 Идея (`ideas`, формат R06 раунда 14)
`{"id": "idea-w15-03", "status": "review|voting|project|rejected", "votes": 31, "district",
"geometry": {"type": "Point", …}, "target": {"kind": "area", "id": "yard-…", …} | null, "object": {"kind"} | null,
"title_ru", "title_kk", "description_ru", "description_kk", "lang", "created_at": {…}, "decided_at": {…} | null,
"check": {"land", "networks", "access", "maintenance"} | null, "reason_ru/kk", "can_improve_ru/kk",
"self_doable": true | false, "to_initiative": "i-w15-…" | null, "demo": true}`.
`self_doable` — жители могут сделать сами (уборка, посадка, лавочки) → R06 «Сделайте вместе» → инициатива R16.

### 2.7 Инициатива (`initiatives`, CONTRACT §5.2)
Ровно §5.2: `id, kind, title, text, lang, target, point, district, starts_at, ends_at, bring, status, joined,
support, report, from_idea, demo` (`author_device` нет — его делает R16). `target` — двор из `yards`.

### 2.8 Кризис (`incidents`, CONTRACT §5.5)
Ровно §5.5 (`zone.kind: district`, задачи служб, обновления ru/kk), плюс `"event": "ev-…"` — связь с событием мира.

### 2.9 Встреча (`meetings`, CONTRACT §5.7)
Ровно §5.7; `place` — цель (двор или объект OSM), `orders[].due` — дата `{"day": N}`, `orders[].link` — на жалобу
или работу **этого же мира**. `questions` — id из `questions`.

### 2.10 Вопрос (`questions`, формат R13 «Вопрос акиму»)
`{"id": "q-w15-04", "district", "lang", "text", "status": "published|pending", "created_at", "published_at",
"base_votes", "answer_ru", "answer_kk", "answered_at", "meeting": "m-w15-1" | null, "demo": true}`.

## 3. Сцены (`scenes`)
Стабильные id для демо (IDEA §3), R01 вешает их на палитру Ctrl+K, R10 проверяет:
- `step2` — «Хан Шатыр»: `target`, `complaints` (освещение: 3 человека; павильон: 2), как в FINAL-4;
- `scene7` — `yard`, `initiative` (субботник, «Я приду» 14 → 15), `support`;
- `scene8` — `complaint` («яма после раскопок», 2 службы), `works` (асфальт и сети), `conflict`, `segments`;
- `scene9` — `incident` («Буран»), `event`, `district`, ожидаемый пульс «Снег в Нуре ×N».

## 4. `seed_world` в модулях (CONTRACT §11)
`seed_world(db_path, records, now=None) -> {"inserted", "skipped"}`; модуль берёт **только свой ключ**.
**R01 передаёт уже материализованный мир**: `records = materialize(load_world(), now)` — все времена в нём ISO
(`2026-10-15T10:01:00+05:00`, даты `2026-10-04`), один `now` на все модули. Так «терпимые» разборщики модулей (ISO-поля
`*_at`, `starts_on`) работают без знания §1, а формы `season` и `next_weekday` уже посчитаны. Модуль, получивший сырой
мир (тест, ручной запуск), зовёт `materialize(records, now)` сам — функция идемпотентна (ISO-строки не трогает).
Модуль, который читает файл мира напрямую (R12 календарь работ, R10 сверка), — тоже через `materialize(load_world(), now)`.
Советы (опыт R09 `seed_demo`, R10 B-048/B-049):
- засев идемпотентен по `id`; **демо-запись с тем же id возвращать в исходное состояние** при каждом запуске
  (`reset`) — иначе через день «сегодня» пусто, а после репетиции «Хан Шатыр» уже исправлен; настоящие записи
  (`demo` не true) не трогать никогда;
- писать только в свои таблицы; читать соседей — через их функции (CONTRACT §7).
R01: при `CIVIC_DEMO=1` и `CIVIC_DEMO_WORLD=1` зовёт все `seed_world` с одним `now` и **не** подмешивает в карту
синтетику R07 (`ui.civic_heat.demo_seed`) — patch в `research/round-15-results/R02/INTEGRATION.txt`.

## 5. Версии
`schema_version` растёт при новых полях (1.1, 1.2 …) — старые поля не меняют смысл. Запросы полей — строкой в STATUS
R02 или в своём INTEGRATION.txt; R02 добавляет в схему и генератор.

| Версия | Что изменилось |
|---|---|
| 1.0 | первая версия (15 окт) |
| 1.0.1 | события: `from/to` → `started_at/ended_at` (как у кризиса); §4 — R01 передаёт материализованный мир (15 окт, вечер) |
