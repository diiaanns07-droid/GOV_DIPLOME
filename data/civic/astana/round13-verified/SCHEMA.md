# Форматы пакета R05 раунда 13 (`round13-verified/`)

Цель: реальная запись появляется на карте только после трёх независимых шагов —
**сохранённый текст страницы → выдержки найдены дословно → проверка другим человеком** — и только черновиком.
Неизвестное остаётся `null`/`unknown`. Состояние цели нигде не хранится: `tools/r13.py` каждый раз вычисляет его
из содержимого `evidence/`, `reviews/` и их sha256-отпечатков. Имя или место файла статус не повышает.

Реестр источников и кандидаты раунда 12 (`../round12-verified/sources.json`, `candidates.json`) только читаются.

## 1. `analysis/queue_analysis.json` (`r05-r13-queue-analysis-v1`)

Разбор 19 текущих кандидатов раунда 12: кластеры (канонический/дубликат/пересечение/программа без места),
противоречия с происхождением подсказок, цели проверки (`targets[]`). Цель — одно место/участок/событие:

| поле | смысл |
|---|---|
| `slug` | стабильный id цели `a-z0-9-` (3–40); id записи civic = `ast-r05-<kind>-<slug>` |
| `kind` | construction / roadworks / landscaping / event |
| `candidate_ids`, `source_ids` | кандидаты и источники раунда 12; источники — что открыть первым |
| `location_text`, `osm_query`, `geometry_level` | где по подсказкам; запрос к OSM-снимку; уровень геометрии |
| `timing` | подсказки начала/окончания и их происхождение (`url`/`search_title`/`search_summary`) |
| `required_evidence`, `do_not_infer` | что должна показать выдержка; чего не выводить |
| `mappable`, `provability`, `priority` | можно ли показать на карте; насколько вероятно подтверждение; порядок |

Подсказки — не факты: заголовок/пересказ поиска ничего не подтверждает.

## 2. `VERIFY_QUEUE.json` (`r05-r13-verify-queue-v1`) — строится `r13.py queue`

Для каждой цели: вычисленное `state`, источники для открытия, подсказка геометрии по OSM-снимку 2026-05-06
(тип, основа, район по OSM-границам — не официальным), сроки-подсказки, обязательные доказательства,
противоречия, последующие сообщения из поиска (`followup_hints`, только подсказка), следующий шаг.
Отдельно — решение по каждому из 19 текущих кандидатов.

## 3. Состояния цели (вычисляются)

| состояние | условие |
|---|---|
| `candidate` | нет `evidence/<slug>/*.json` |
| `evidence_invalid` | доказательство не проходит проверку (схема, выдержки/контекст, дата, город, длина текста, ПДн) |
| `evidence_attached` | ≥1 корректное доказательство, проверки нет |
| `review_stale` | доказательства или геометрия OSM изменились после проверки (отпечатки не совпали) |
| `review_invalid` | проверка неполна/некорректна (тот же человек, нет решения по полю, конфликт значений…) |
| `rejected` | сотрудник отклонил цель |
| `reviewed_no_geometry` | принято, но пригодной геометрии нет — не публикуется |
| `draft_ready` | всё сходится; запись попадает в пакет черновиков (если её пропускает профиль real R05) |
| `blocked_by_validator` | профиль real R05 отклонил собранную запись (или валидатора нет в дереве) |

## 4. `evidence/<slug>/<source.id>.json` (`r05-r13-evidence-v1`) — пишет только `r13.py attach`

```json
{
  "schema": "r05-r13-evidence-v1", "target": "<slug>",
  "source": {"id": "src-r12-… | src-r13-<sha256(url)[:12]>", "url": "https://…", "publisher": "…",
             "publisher_kind": "official_gov|city_utility_or_operator|state_media|city_media|news|other",
             "registered": true},
  "capture": {"origin": "human_saved_page_text | agent_http", "attached_by": "метка роли (без контактов)",
              "attached_at": "…Z", "retrieved_at": "…Z", "content_sha256": "<sha256 файла>",
              "text_chars": 5321, "storage": "outside_repo"},
  "page": {"title_quote": "заголовок статьи", "published_on": "YYYY-MM-DD",
           "published_quote": "выдержка с датой публикации", "city_quote": "выдержка, где названа Астана"},
  "claims": [{"field": "what | location.text | status | schedule.* | budget.amount_kzt | budget.basis | responsible.organization",
              "value": "…", "quote": "дословно, 3+ слов, ≤300 символов", "claim_type": "stated|expected|reported_actual",
              "value_basis": "перевод формулировки в значение, если нужно", "locator": "абзац/таблица"}],
  "snapshot": [{"ref": "page.title_quote | claims[i] …", "context": "выдержка ±120 символов из сохранённого текста"}],
  "not_stated": ["budget.amount_kzt", "…"], "notes": "…"
}
```

Правила attach (все проверяются кодом):
- `origin` из выдачи поиска, URL или имени файла (`search_title`, `search_summary`, `search_snippet`, `url`,
  `file_name`, `none`) — отказ `snippet_not_evidence`;
- текст страницы — файл ВНЕ репозитория; в Git — только sha256, длина и короткий контекст выдержек;
- нормализованный текст не короче `min_page_chars` (400): вставленный сниппет страницей не считается;
- каждая выдержка (заголовок, дата, город, все утверждения) найдена дословно, целыми словами, в тексте страницы
  без `<script>/<style>/комментариев`; `published_quote` содержит `published_on`; `city_quote` называет Астану;
- обязательны `what`, `location.text` и «когда»: для перекрытий и событий — `schedule.planned_start` или
  `schedule.current_planned_end`, для остальных — дата или статус;
- дата/сумма значения — в выдержке, иначе пояснение `value_basis` (запись станет `derived`);
- `status`: `planned` — план; `in_progress/completed/cancelled` только `reported_actual`;
  `actual_end` только `reported_actual` и не позже публикации; сумма только с `budget.basis`;
- ПДн (телефон, ИИН, e-mail) в свободном тексте и контексте — отказ.

## 5. `reviews/<slug>.json` (`r05-r13-review-v1`) — пишет только `r13.py review`

`reviewer` (другой человек, не `attached_by`), `reviewed_at`, `method`
(`url_opened_by_reviewer` | `saved_text_rechecked` — тогда файл сверяется по sha256 и выдержкам),
`evidence_digest` (отпечаток всех доказательств цели), `decision` accept/reject, `claims`
{`<source.id>:<field>`: `accept` | `reject: причина`} — решение по каждому утверждению, одно принятое значение
на поле, `title`/`description` для карточки, `geometry`:
`level` = `street_segment` (участок между двумя улицами) | `intersection` (точка пересечения) |
`whole_street` (вся улица, только с `reason`) | `manual` (сотрудник рисует Point/LineString, `basis` обязателен) |
`none` (непубликуемо); `osm_query` для OSM-уровней; `geometry_sha256` ставит команда. Геометрия OSM не хранится
руками — при сборке пересчитывается из запроса; изменение снимка делает проверку устаревшей.
Во всех случаях `geometry_precision = approximate`: снимок OSM — не точный адрес работ.

## 6. Пакеты и сводка — строит `r13.py build`

- `package.civic-v1.json` — текущие/предстоящие черновики; `historical.civic-v1.json` — завершённые/отменённые
  и те, у кого плановый срок прошёл без свежего сообщения о работе (старое объявление ≠ действующее перекрытие).
  Оболочка импортера R02, `slice.demo=false`, `slice.source` = `r05-astana-r13-verified` (`…-historical`).
- Статус `planned/in_progress` из сообщения старше `status_max_age_days` (45) отбрасывается → `unknown`
  с пояснением в `evidence_notes`.
- `summary.json` (`r05-r13-summary-v1`): `verified_current`, `verified_historical`, `candidates`, `rejected`,
  `fetched_sources` (источники с корректно прикреплённым текстом), состояния, покрытие по видам и районам.
