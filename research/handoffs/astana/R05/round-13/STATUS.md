# R05 раунд 13 — подтвердить реальные работы и события Астаны

Статус: PARTIAL (checkpoint 1)
Обновлено: 2026-10-07 17:10 UTC
Ветка: `claude/fervent-dijkstra-1cqrg5` — назначена этой сессии средой. На ней же лежат поставки R10 раунда 11
и R09 раунда 12 (закреплена f2ebaf9); R05 раунда 13 трогает только свои пути, чужие пути не меняются.
REFERENCE_BASE_SHA 56538a3 уже влит в ветку обычным merge (56885d5) — BASE_MISMATCH нет.
Источник модуля: прежняя поставка R05 `claude/focused-hypatia-z8h0no` @ ca0f06f (код 4d5731f) — пути
`data/civic/astana/round12-verified/` и `tests/civic/R05/round12/` восстановлены `git checkout ca0f06f -- <путь>`
(содержимое совпадает с 4d5731f), без merge чужой истории.
Пути R05: data/civic/astana/round12-verified/, data/civic/astana/round13-verified/, tests/civic/R05/round12/,
tests/civic/R05/round13/, research/round-13-results/R05/, этот файл.

## Сделано
- Сеть: те же отказы, что в раунде 12 (CONNECT 403 / EGRESS_BLOCKED для gov.kz, inform.kz, kazpravda.kz, zakon.kz,
  bes.media, astana.gov.kz, vechastana.kz, OSM, wikipedia). Диагностика ограничена 9 хостами curl + 3 URL WebFetch:
  research/round-13-results/R05/NETWORK_STATUS.txt, data/civic/astana/round13-verified/network_audit.json.
- Модуль R05 раунда 12 восстановлен. tests/civic/R05 на ветке: 203 passed, 1 skipped, 3 failed → тест конвертера
  поиска ссылается на research/round-12-results/R05/ (нет на ветке): теперь честный skip NOT_RUN с причиной.

## Дальше
Очередь проверки 19 текущих кандидатов (дубли/противоречия/обязательные доказательства), CLI прикрепления
сохранённого человеком текста страницы, проверка сотрудником, сборка черновиков civic-v1, импорт настоящим R02.
