# STATUS — K08, независимая проверка утверждений

**Статус:** partial — проверено 6 из 10.

- Задача: проверить 10 MVP-важных утверждений из исследований обоих городов по первоисточникам (CLAUDE_CAPACITY_12.txt, K08).
- Репозиторий / ветка: `diiaanns07-droid/GOV_DIPLOME`, `claude/dazzling-mayer-drhsxk`. В ветку обычным merge влита `codex/research-import-2026-10-05` @ b87e5af.
- Результаты: `research/next-round/K08/` — `REGISTRY.md`, `registry.json`, `ACCESS_LOG.md`, `verify_claims.sh`, `render_registry.py`, `run_log.txt`.

## Сделано
- V01 (AST-A06-F007/F008/F009) — подтверждено пересчётом файлов Bussure.
- V02 (AST-A06-F019/F020) — подтверждено чтением кода и пересчётом CSV bus-traffic-astana.
- V03 (AST-A06-F005/F006, A06-F004) — подтверждено по каталогам MobilityData и transitland: фидов KZ нет. Поиск GitHub A06-F004 не воспроизведён: search API недоступен.
- V04 (AST-A11-F003/F004, AST-A06-F002/F028/F004) — подтверждено по data/ репозитория. Уточнение: osm_timestamp = null. Геоданных районов Шымкента в data/ нет.
- V05 (AST-A01-F004) — текст политики iKOMEK 109 от 13.03.2019 подтверждён в зеркале GitHub. Официальность и текущая работа не проверены.
- V06 (AST-A01-F007) — неофициальная платформа ikomek_platform подтверждена по README; LICENSE нет.

## Проверки
- `verify_claims.sh` запущен, вывод в `run_log.txt`. Это пересчёт по реальным файлам, а не проверка JSON.
- `python3 -m json.tool registry.json` — синтаксис в порядке. Фактом это не считается.

## Ограничения
- data.egov.kz, stat.gov.kz, gov.kz, opendata.kz, OSM/Overpass, zenodo, doi.org, mdpi, api.citytransport.kz, cts.gov.kz — 403 / EGRESS_BLOCKED.
- GitHub API доступен только для подключённых репозиториев. Публичные репозитории читаются через git clone и raw.githubusercontent.com.
- Утверждения о госуслугах, порталах и статистике первоисточником здесь не проверяются. Они получат вердикт «не проверено» с указанием блокировки.

## Следующий шаг
V07–V10: прогон тестов исходного репозитория (утверждение A13), утверждение A12 о 27 из 33 наборов, A08-F012 (данные Казгидромета по запросу) и одно ключевое утверждение о госпортале (вероятно, «не проверено» из-за блокировки).

## Воспроизведение
```bash
git checkout claude/dazzling-mayer-drhsxk
bash research/next-round/K08/verify_claims.sh /tmp/k08_work
```
