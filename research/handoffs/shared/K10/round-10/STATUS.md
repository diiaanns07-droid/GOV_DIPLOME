Задача / идентификатор: round-10 · K10 · «Астана: отдельные реальные данные и проверка переноса» (research/round-10/prompts/K10.txt @ codex/govtech-main-interface 7c6fb75)
Агент / город / сфера: K10 / astana (+ проверка переноса Шымкент ↔ Астана) / данные школ, case-пакет, перенос сценария
Обновлено: 2026-10-06, UTC
Статус: partial (этап 0)
Рабочая ветка: claude/save-work-handoff-j7pc05
Исходный коммит: 657db5207a2c92d1f64fd94f39ba98f56cc30fa8 (последний коммит прежней сессии K10, r9; роль принята по назначению пользователя)
Назначенные пути: research/round-10-results/K10/, research/handoffs/shared/K10/round-10/STATUS.md

Сделано:
- Проверен доступ: официальные сайты РК, OSM, Wikidata, 2GIS — NOT_FETCHED (403 CONNECT); доступен только бакет Overture и WebSearch (наводки без открытия страниц). sources/access_log.json.
- scripts/overture_bbox.py — извлечение Overture по bbox с буфером (без телефонов, e-mail, соцсетей).

Не сделано: этапы 1–3.
Следующий шаг: сопоставить 8 школьных записей среза Астаны (d2ff344 data.js) с OSM-слоями Overture и наводками поиска.
Для воспроизведения: см. research/round-10-results/K10/STATUS.md.
Конфликты: общий код меняет только BUILD (K04). K01 делает тот же CONTRACT для Шымкента; K10 не пишет в его папку.
