# Раунд 14 — общий контракт (Birge, Астана)

Дата: 2026-10-10. Рабочие дни: 11–15 октября. После 15-го Claude недоступен, продолжает GPT/Codex — поэтому всё, что сделано, должно быть понятно без этого чата.

## 0. Цель и сценарий демо

Продукт **Birge** — платформа обратной связи между жителями и акиматом Астаны. Главный зритель демо — **акимат на ноутбуке**. Каждая роль работает ради этого сценария (3 минуты на защите Gton):

1. Житель пишет жалобу (казахский, русский или вперемешку) и выбирает место на карте; система предлагает объект: «Это остановка "…"?».
2. Модель определяет категорию и находит похожие обращения; житель может нажать «Я тоже» вместо новой жалобы.
3. На карте акимата объект/участок/двор плавно краснеет — видно, где больше всего жалоб (тепловая карта объектов).
4. «Картина дня»: аким за 10 секунд видит темы, районы, горячие места, просрочки и объекты с отставанием.
5. Акимат предлагает решение — ставит на 3D-карту объект (сквер, площадка, спортплощадка, остановка, освещение), он «строится» с пометкой «проект»; жители голосуют.
6. После ремонта объект становится зелёным «исправлено», житель видит статус.

Фокус-район для крупного плана: **Нура** (по нему собираем реальные объекты и работы). Остальной город — тот же функционал.

## 1. Ветки и основа

- Пакет и основа раунда: ветка **`claude/round-14-package`** (= `codex/govtech-main-interface` @ c076569 + `research/round-14/`). Новая сессия выбирает её как базу.
- Каждая роль работает в **своей** ветке сессии. Не работать в `main`, не делать force push, не трогать чужие ветки.
- Модули раунда 13 ещё не собраны вместе. Если ваш путь раньше принадлежал другой роли, восстановите его из последней поставки раунда 13 командой `git fetch origin <ветка> && git checkout <sha> -- <ваши пути>` и запишите SHA в DELIVERY.json:

| Модуль (пути) | Ветка раунда 13 | SHA головы |
|---|---|---|
| оболочка, `ui/web_server.py`, `web/civic/shell/` | claude/affectionate-ride-bol5v8 | cb9d60a |
| `ui/civic_store/` | claude/elegant-franklin-jbhprq | 26793c8 |
| `web/civic/map/` | claude/zen-mendel-e79iiv | 7de5e0b (код f0a52f7) |
| `web/civic/editor/` | claude/intelligent-sagan-7shpeh | 9c996c6 |
| `ui/civic_feedback/`, `web/civic/feedback/` | claude/focused-hypatia-z8h0no | 933cd90 |
| `engine/civic_scenarios/`, `web/civic/scenarios/` | claude/brave-hopper-bkc58b | 16aa37a |
| `agent/civic_assistant/`, `web/civic/assistant/` | claude/wizardly-ptolemy-qy8ltw | 14c3384 |
| `ml/civic_classifier/` (v1) | claude/wizardly-ptolemy-qy8ltw | 14c3384 |
| `data/civic/astana/round13-verified/` | claude/fervent-dijkstra-1cqrg5 | a995f9f |

Перед восстановлением прочитайте DELIVERY/handoff этой ветки. Код чужих поставок сначала прочитать, потом запускать.

## 2. Кто какими путями владеет

Меняйте **только свои пути** и свою папку результатов `research/round-14-results/<R>/`. Нужна правка чужого модуля — положите в свою папку `INTEGRATION.txt` с минимальным patch; применяет R01.

| Роль | Пути |
|---|---|
| R01 Интегратор | `web/index.html`, `web/style.css`, `web/map.js`, `web/interface.js`, `web/civic/shell/`, `ui/web_server.py`, `tests/civic/R01/` |
| R02 Данные | `ml/datasets/`, `ml/labeling/`, `web/labeling/`, `tests/civic/R02/` |
| R03 Модель v2 | `ml/civic_classifier_v2/`, `tests/civic/R03/` |
| R04 Дубли и ML-API | `ml/civic_dedup/`, `ui/civic_ml_api/`, `tests/civic/R04/` |
| R05 3D-превью | `web/civic/build3d/`, `web/vendor/three/`, `tests/civic/R05/` |
| R06 Предложения и этапы | `ui/civic_store/`, `web/civic/proposals/`, `tests/civic/R06/` |
| R07 Тепловая карта | `ui/civic_heat/`, `web/civic/heat/`, `tests/civic/R07/` |
| R08 Картина дня | `ui/civic_akim/`, `web/civic/akim/`, `tests/civic/R08/` |
| R09 Жалоба v2 | `ui/civic_feedback/`, `web/civic/feedback/`, `tests/civic/R09/` |
| R10 Приёмка | `tests/civic/R10/`, `tests/e2e/` |
| R11 UX и казахский | `web/civic/ui-kit/`, `web/civic/i18n/`, `tests/civic/R11/` |
| R12 Точность карты | `engine/civic_geo/`, `data/civic/astana/geo/`, `web/civic/map/`, `web/civic/editor/`, `tests/civic/R12/` |
| R13 Прогноз (прототип) | `ml/civic_forecast/`, `ui/civic_forecast/`, `tests/civic/R13/` |
| LOCAL (Codex на ноутбуке) | `data/civic/astana/osm-objects/`, `data/civic/astana/nura-real/`, `data/civic/astana/weather/`, `web/vendor/three/` (первичная загрузка) |

Заморожено в этом раунде: `engine/` (кроме `engine/civic_scenarios/` только чтение), `agent/`, `web/govtech/`, Шымкент, `legacy/`.

## 3. Категории v2

Источник истины — `research/round-14/categories_v2.json` (12 категорий, переводы ru/kk, уровни цвета). Не копировать список руками в код: загружать файл или генерировать из него. Старые метки переводятся по `v1_to_v2`.

## 4. Куда привязана жалоба (target)

```json
{"kind": "object|segment|area", "id": "строка", "label_ru": "Остановка «…»", "label_kk": "…"}
```

- `object` — реальный объект из OSM: остановка, площадка, спортплощадка, парк. `id` = `osm-node-<id>` / `osm-way-<id>`.
- `segment` — участок улицы. `id` = id ребра пешеходного графа `osm-w<way>-<n>` из `engine/civic_scenarios/graphs/osm-astana-walking-20260506.graph.json` (у каждого ребра есть настоящая форма улицы).
- `area` — двор/квартал (`yard-<id>`, из OSM landuse=residential) или ячейка ~150 м (`cell-<id>`) там, где двора нет.

Выбор target делает R12 (`engine/civic_geo`): по точке и категории возвращает 1–3 ближайших кандидата.

## 5. Запись жалобы v2

```json
{
  "id": "c-…", "created_at": "2026-10-11T10:00:00+05:00",
  "text": "…", "lang": "ru|kk|mixed",
  "category": "roads", "category_source": "resident|model|staff",
  "model": {"label": "roads", "score": 0.91, "version": "…", "needs_review": false},
  "point": [71.43, 51.12], "target": {"kind": "segment", "id": "osm-w123-4"},
  "district": "nura", "status": "new|accepted|in_progress|fixed|rejected",
  "status_history": [{"at": "…", "status": "new"}],
  "metoo": 3, "duplicate_of": null, "demo": true
}
```

`demo: true` — синтетическая запись; интерфейс помечает её. Реальные тексты жителей с персональными данными в Git не попадают.

## 6. Вес и цвет на тепловой карте

- Вес цели = сумма по её жалобам и «Я тоже»: `0.5 ^ (возраст_в_днях / 14)`.
- Уровни и цвета — `heat_levels` в categories_v2.json (жёлтый → тёмно-красный) + **число на значке** (цвет никогда не один).
- После статуса `fixed` цель 7 дней показывается зелёной «исправлено», вес обнуляется.
- Форма подсветки: `object` — сам значок + ореол, растущий с весом; `segment` — линия **по настоящей форме улицы**, толщина растёт с весом; `area` — заливка двора или мягкая ячейка.
- Смысловой зум: z < 12 — районы; 12–15 — дворы и участки; ≥ 15 — отдельные объекты со значками.

## 7. HTTP API v2 (всё под `/api/civic/v2/`)

| Метод и путь | Владелец | Ответ |
|---|---|---|
| `POST /classify` `{text}` | R04 (модель R03, запасная v1) | `{category, score, needs_review, model_version, top3:[{category,score}]}` |
| `POST /similar` `{text, point?, days?}` | R04 | `{matches:[{complaint_id, score, target, metoo}]}` |
| `GET /targets?lon&lat&category` | R12 | `{candidates:[{target, distance_m, geometry}]}` |
| `POST /complaints`, `GET /complaints?bbox&since`, `POST /complaints/{id}/metoo`, `POST /complaints/{id}/status` | R09 | запись §5 |
| `GET /heat?bbox&days&category&zoom` | R07 | `{generated_at, items:[{target, geometry, weight, level, count, fixed_until}]}` |
| `GET /akim/summary?date&district` | R08 | темы, районы, топ-10 целей, просрочки, объекты с отставанием |
| `GET/POST /proposals`, `POST /proposals/{id}/vote` `{value:1|-1, device_id}` | R06 | предложение: `{id, kind, geometry, status:"proposal", votes_up, votes_down}` |
| `GET /objects?bbox`, `PUT /objects/{id}/stage` | R06 | объект + `stage`, `planned_end`, `forecast_end`, `delay_days`, `stale` |

Этапы объекта: `planned → design → procurement → construction → acceptance → operating`. `stale = true`, если запись не обновлялась > 14 дней. Python-модули отдают функции; маршруты в `ui/web_server.py` подключает R01. Пока соседа нет — работайте на фикстурах по этому контракту и пометьте это в DELIVERY.

## 8. Точность карты (обязательно)

1. Никаких линий «от руки». Участок улицы = ребра графа между двумя выбранными точками, форма из OSM.
2. Точечные объекты — только реальные из OSM, с их координатами.
3. Тесты: линия участка отстоит от формы ребра не больше чем на 5 м; остановка — не дальше 60 м от улицы; все координаты внутри границы Астаны.
4. Нет точного места — показываем область и пишем «примерное место», а не уверенную линию.

## 9. Интерфейс

Правила — `research/round-14/UX_BRIEF.md`; детали и токены — у R11 (`web/civic/ui-kit/`, `web/civic/i18n/ru.json`, `kk.json`). Весь видимый текст через ключи перевода, оба языка. Проверка в 375 px и 1366 px.

## 10. Сдача работы

В `research/round-14-results/<R>/`: `DELIVERY.json` (role, branch, base_sha, restored_from, code_sha, tested_sha, push_status, changed_paths, tests PASS/FAIL/NOT_RUN, known_limits, next_step), `RUN.txt`, `INTEGRATION.txt`. Handoff: `research/handoffs/astana/<R>/round14/STATUS.md`. Checkpoint с push каждые 30–40 минут и при 85% лимита аккаунта — чтобы следующий аккаунт продолжил с handoff.
