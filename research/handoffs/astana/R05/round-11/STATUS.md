# R05 — Реальные объекты Астаны, геоданные и права (раунд 11)

- Роль: R05 (единственная роль этой сессии)
- Ветка: `claude/intelligent-sagan-7shpeh` (origin https://github.com/diiaanns07-droid/GOV_DIPLOME)
- Исходный HEAD ветки: `834a25fb860dd5514d02c9274b70d7bf8a53a79c`
- PACK_SHA (origin/codex/govtech-main-interface): `9c2f5c0dae14b46c0697a9dfc7f854351bfd570d` (PACK_STATUS=READY)
- Снимок приложения для сравнения: `b2cb2e02c602c166ba6d47c02d8e902e5478c791` (читается через git show, не checkout)
- Собственные пути: `data/civic/astana/`, `tests/civic/R05/`, `research/round-11-results/R05/`, этот файл.

## Checkpoint 1 — PARTIAL

Сеть: исходящий HTTPS контейнера ограничен политикой egress. gov.kz, astana.gov.kz, data.egov.kz, egov.kz,
primeminister.kz, stat.gov.kz, inform.kz, astanatimes.com, tengrinews.kz, wikipedia/wikidata, openstreetmap.org,
osmfoundation.org, opendatacommons.org, openfreemap.org (+tiles), openmaptiles.org, docs.overturemaps.org,
overpass-api.de — proxy 403 (2026-10-06 15:28–15:35 UTC). Доступен только raw.githubusercontent.com:
получены официальные тексты условий OpenMapTiles, OpenFreeMap, Overture (attribution), MapLibre.
Обход не выполнялся. Следствие: подтверждённых реальных объектов Астаны в этом раунде нет; работаю по ветке
«ЕСЛИ СЕТЬ ЗАКРЫТА» промпта.

Готово:
- `data/civic/astana/sources.json` — реестр 28 источников с реальными попытками доступа (7 fetched, остальное not_fetched/egress 403).
- `data/civic/astana/tools/civic_v1.py` — валидатор civic-v1 (профили contract/real/demo), stdlib.
- `data/civic/astana/tools/build_geofence.py` → `geofence.json` (из сохранённых OSM-полигонов районов, детерминированно).
- `data/civic/astana/tools/probe_sources.py` — проба доступности без сохранения страниц.
- `data/civic/astana/templates/intake_record.template.json` — честный шаблон неизвестных полей.
- `research/round-11-results/R05/fetch_audit_2026-10-06_{a,b}.json` — сырые результаты проб.

Проверки:
- `python3 -m pytest tests/civic/R05 -q` → PASS (32 passed) на рабочем дереве checkpoint 1.

Следующий шаг: builder среза (intake → civic-v1 objects.json, стабильные ID, версия среза),
LICENSE_REGISTER/ATTRIBUTION, synthetic demo slice, импорт-хелпер для R02.
