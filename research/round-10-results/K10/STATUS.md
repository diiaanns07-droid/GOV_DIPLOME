# K10 · Раунд 10 · «Астана: отдельные реальные данные и проверка переноса» — STATUS

| Поле | Значение |
|---|---|
| Роль | K10 (не BUILD). Задание: `research/round-10/prompts/K10.txt` @ `origin/codex/govtech-main-interface` = `7c6fb75ec66c50627af62b9d0d8e94c1f09bee16` |
| Ветка | `claude/save-work-handoff-j7pc05` (назначена в `snapshots.json`). Роль принята с SHA `657db5207a2c92d1f64fd94f39ba98f56cc30fa8` (последний коммит прежней сессии K10, r9). Перед каждым push проверяется, что удалённая ветка не ушла вперёд: второго писателя быть не должно |
| Кодовая база | `d2ff344c5ec9b9a729ea59df50ec81f981e619de` (корневой `app.py`/`web/` на 8501); BUILD `5f81e4d` = cherry-pick этого же коммита, код `web/ ui/ agent/ app.py tests/govtech` идентичен. Нового BUILD с импортом school-access-case-v1 пока нет |
| Обновлено | 2026-10-06 UTC |
| Статус | **этап 0** (checkpoint): доступ к источникам проверен, извлечение Overture для буфера запущено |
| Пути | только `research/round-10-results/K10/` и `research/handoffs/shared/K10/round-10/STATUS.md` |

## Этап 0 — доступ к источникам (`sources/access_log.json`)

- **NOT_FETCHED** (CONNECT 403 по сетевой политике окружения, по одному запросу на хост): gov.kz (в т. ч. страница управления образования Астаны), astana.gov.kz, egov.kz, data.egov.kz, stat.gov.kz, taldau, OpenStreetMap/Overpass/Nominatim, Wikidata, Википедия, 2GIS, kundelik, bilimal, edu.gov.kz, Geofabrik, OpenFreeMap. WebFetch тоже заблокирован (gov.kz, informburo.kz).
- **Доступно:** публичный бакет Overture Maps (S3, анонимно) — через него можно получить независимые вторичные слои: места (Meta и др.), полигоны землепользования OSM с исходными тегами (`source_tags`), здания OSM.
- **WebSearch** работает, но страницы не открывает: его результаты — только **наводки** с URL, не проверка.

Следствие: официального подтверждения ни одной школы в этой среде не будет. Все школы — `observed_secondary`, `verification_status` = `secondary_only` или `not_fetched`, а конфликты отмечаются явно.

## Срез Астаны в кодовой базе `d2ff344`

`web/govtech/core/data.js`, город `astana`:
- bbox `[71.418372, 51.163033, 71.447, 51.181]` (≈ 2×2 км, выбран в r3 как ячейка с наибольшим числом социальных мест);
- Overture `2026-09-23.1`, извлечено `2026-10-05T06:20:01Z`;
- `kind`: «observed_secondary (Overture/OSM), not an official registry»;
- группа `school` — **8 записей**. По названиям лишь часть похожа на общеобразовательные школы: «Учебный центр ФПРК», «Образовательный центр АЗиЯ», «Учебный центр Expert-A» — вероятно, не школы; «Astana Garden International School» — частная. Решение по каждой — на этапе 1, с источниками.

## Следующий шаг

Этап 1: сопоставление 8 записей с независимыми вторичными слоями (OSM через Overture) и наводками поиска, `match-review.json`, `schools.json`, `sources.json`.
