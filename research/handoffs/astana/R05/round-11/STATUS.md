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

## Checkpoint 2 — PARTIAL

Готово:
- `tools/build_slice.py` — сборка срезов из intake: `objects.json` (реальные, draft), `historical.json`,
  `demo_synthetic.json` (slice.demo=true), `evidence_index.json` (claim→источник→выдержка, для редактора),
  `validation.json` (QA). Без чтения часов; версия среза = хэш содержимого и входов; `--check` сравнивает с диском.
- `intake/demo/demo_records.json` — 9 синтетических записей (сдвиг срока, план, unknown, событие, завершено,
  отменено, без геометрии, draft, archived). Геометрия схематичная в районе графа K03, бюджет/организация null.
- `intake/real/` пуст: реальные источники не получены (egress 403). objects.json содержит 0 записей.

Проверки: `python3 -m pytest tests/civic/R05 -q` → 47 passed; `python3 -I data/civic/astana/tools/build_slice.py --check` → exit 0.
Следующий шаг: LICENSE_REGISTER.json/ATTRIBUTION.txt, import helper для R02, INTEGRATION.txt.

## Checkpoint 3 — PARTIAL

Готово:
- `LICENSE_REGISTER.json` (11 записей: OSM/ODbL, тайлы OSMF, OpenFreeMap, OpenMapTiles, Overture, MapLibre,
  geofence, демо, реальные объекты, проприетарные карты, код) и `ATTRIBUTION.txt`. Для каждой записи указано,
  получен ли текст условий в этом раунде; not_fetched = перепроверить.
- `tools/import_helper.py` — пакет → план импорта для R02 (create/skip_unchanged/update_import_draft/
  editor_review/report_missing; публикации нет), проверка целостности среза, демо только флагом.
  Согласовано со схемой R02 `ui/civic_store/db.py` @ a95f857 (import_source/external_id/digest, id ≤ 64).
- `tools/pilot_check.py`, `pilot_reference.json`, `research/round-11-results/R05/PILOT.md`.
- `README.md` пакета, `research/round-11-results/R05/INTEGRATION.txt`.

Проверки: `python3 -m pytest tests/civic/R05 -q` → 71 passed; `build_slice.py --check` → без изменений.
Следующий шаг: stretch — обнаружение смены опубликованного срока между двумя версиями источника; затем
независимая проверка (adversarial review) и финальный DELIVERY.
