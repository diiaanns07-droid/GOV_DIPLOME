# Форматы пакета R05 раунда 12 (`round12-verified/`)

Цель: каждое значение в карточке объекта имеет проверяемое происхождение — URL, дату публикации,
дату получения, короткую выдержку и место в источнике. Неизвестное остаётся `null`/`unknown`.

## 1. `sources.json` — реестр источников (`r05-r12-sources-v1`)

```json
{
  "schema": "r05-r12-sources-v1", "city": "astana",
  "sources": [{
    "id": "src-r12-...",                       // латиница/цифры/._-, ≤ 64
    "url": "https://...",
    "publisher": "Акимат города Астаны" | null,
    "publisher_kind": "official_gov | city_utility_or_operator | state_media | city_media | news | other",
    "title_as_listed": "заголовок, как в выдаче поиска или на странице",
    "published_on": "YYYY-MM-DD" | null,       // только из самой страницы (или из URL, тогда published_on_basis=url)
    "published_on_basis": "page | url | null",
    "discovered_via": {"tool": "WebSearch", "at": "...Z", "query": "..."},
    "access_status": "fetched | not_fetched | unavailable",
    "retrieved_at": "...Z" | null,             // обязательно при fetched
    "content_sha256": "hex" | null,            // sha256 сохранённого текста страницы (сам текст в Git не хранится)
    "fetch_method": "agent_http | human_saved_text" | null,
    "license": "текст условий" | null,
    "license_status": "unknown | stated_on_site | public_official_info",
    "access_attempts": [{"at", "method", "outcome", "detail"}]
  }]
}
```

`fetched` означает: текст страницы реально получен и его sha256 записан. Выдача поиска (заголовок + URL +
сгенерированный пересказ) **не** делает источник `fetched`.

## 2. `candidates.json` — непроверенные и отклонённые кандидаты (`r05-r12-candidates-v1`)

Не импортируются. Каждый кандидат: `id`, `decision` (`to_verify | rejected | duplicate`), `reason`,
`kind`, `title_as_listed`, `source_ids`, `location_text`, `date_hint` + `date_hint_origin`
(`url | search_title | search_summary | none`), `hints` — что выдача *намекает* (поле, текст, происхождение),
`verify_checklist` — какие поля проверить на странице, `geocode` — предложение геометрии из OSM (если есть).

## 3. `drafts/<id>.json` и `verified/<id>.json` — запись (`r05-r12-record-v1`)

```json
{
  "schema": "r05-r12-record-v1",
  "id": "ast-r12-<kind>-<slug>",
  "kind": "construction | roadworks | landscaping | event",
  "title": "простой текст", "description": "простой текст",
  "historical": false,
  "location": {"text": "как в источнике", "geometry": GeoJSON | null,
               "geometry_precision": "approximate | unknown", "geometry_basis": "OSM way/node id, снимок 2026-05-06"},
  "claims": [{
    "field": "status | schedule.planned_start | schedule.original_planned_end | schedule.current_planned_end | schedule.actual_end | budget.amount_kzt | budget.basis | responsible.organization | responsible.public_contact",
    "value": "...",
    "claim_type": "stated | expected | reported_actual",
    "source_id": "src-r12-...",
    "quote": "дословная выдержка ≤ 300 символов",
    "locator": "абзац/таблица",
    "value_basis": "как из выдержки получено значение (например «до конца года» → 2026-12-31)" | null
  }],
  "not_confirmed": ["budget.amount_kzt", "responsible.organization", "..."],
  "evidence_notes": "что подтверждено и чего источник НЕ говорит"
}
```

`verified/` получает запись только командой `tools/r12.py verify`: каждая `quote` должна дословно (после
нормализации пробелов, регистра, кавычек и тире) найтись в сохранённом тексте источника, sha256 текста
записывается в реестр. Иначе запись остаётся в `drafts/`.

Правила значений (как в сборке R05 раунда 11): `expected` подтверждает только `status=planned`;
`in_progress | completed | cancelled` требуют `reported_actual`; `actual_end` — только при `completed`,
не позже даты публикации источника; сумма — только с `budget.basis` из того же источника.
Перевод формулировки в дату («до конца года») — `value_basis`, а запись получает `evidence_type=derived`.

## 4. `package.civic-v1.json` и `historical.civic-v1.json`

Оболочка импортера R02 (`ui/civic_store/importer.py`):
`{"schema_version":"civic-v1","city":"astana","slice":{"name","version","demo":false,"source":"r05-astana-r12-verified","as_of"},"items":[...]}`.
Все записи — черновики (импортер сам ставит `draft`; `publication/revision/updated_at` не передаются).
Строятся детерминированно из `verified/` командой `tools/r12.py build`.
