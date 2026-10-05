# K08 — журнал доступа (2026-10-05)

| Хост | Способ | Результат |
|---|---|---|
| data.egov.kz | curl через прокси; WebFetch | CONNECT 403; EGRESS_BLOCKED |
| stat.gov.kz | curl; WebFetch | CONNECT 403; EGRESS_BLOCKED |
| www.gov.kz | curl | CONNECT 403 |
| opendata.kz | curl | CONNECT 403 |
| www.openstreetmap.org, overpass-api.de | curl | CONNECT 403 |
| zenodo.org, doi.org, www.mdpi.com | curl | CONNECT 403 |
| api.citytransport.kz, cts.gov.kz | curl | CONNECT 403 |
| api.github.com | curl | 200, но для репозиториев вне сессии отвечает «access not enabled» |
| github.com (git clone публичных репозиториев) | git | работает; LFS не скачивался |
| raw.githubusercontent.com | curl | 200 |
| WebSearch | инструмент поиска | работает, но это пересказ выдачи, а не первоисточник; для подтверждения не используется |

Повторных запросов к заблокированным хостам не делал.
| www.inform.kz | WebFetch (1 запрос) | EGRESS_BLOCKED |
| WebSearch по заголовку статьи Kazinform (V10) | 1 запрос | статья с таким URL в выдаче есть; использовано только как вторичный сигнал |
