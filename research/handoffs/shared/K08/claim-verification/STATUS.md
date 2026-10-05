# STATUS — K08, независимая проверка утверждений

**Статус:** partial — проверено 2 из 10.

- Задача: проверить 10 MVP-важных утверждений из исследований обоих городов по первоисточникам (CLAUDE_CAPACITY_12.txt, K08).
- Репозиторий / ветка: `diiaanns07-droid/GOV_DIPLOME`, `claude/dazzling-mayer-drhsxk`. В ветку обычным merge влита `codex/research-import-2026-10-05` @ b87e5af.
- Результаты: `research/next-round/K08/` — `REGISTRY.md`, `registry.json`, `ACCESS_LOG.md`, `verify_claims.sh`, `run_log_stage1.txt`.

## Сделано
- V01 (AST-A06-F007/F008/F009) — подтверждено пересчётом файлов Bussure.
- V02 (AST-A06-F019/F020) — подтверждено чтением кода и пересчётом CSV bus-traffic-astana.

## Проверки
- `verify_claims.sh` запущен, вывод в `run_log_stage1.txt`. Это пересчёт по реальным файлам, а не проверка JSON.
- `python3 -m json.tool registry.json` — синтаксис в порядке. Фактом это не считается.

## Ограничения
- data.egov.kz, stat.gov.kz, gov.kz, opendata.kz, OSM/Overpass, zenodo, doi.org, mdpi, api.citytransport.kz, cts.gov.kz — 403 / EGRESS_BLOCKED.
- GitHub API доступен только для подключённых репозиториев. Публичные репозитории читаются через git clone и raw.githubusercontent.com.
- Утверждения о госуслугах, порталах и статистике первоисточником здесь не проверяются. Они получат вердикт «не проверено» с указанием блокировки.

## Следующий шаг
Проверить V03–V10: GTFS Шымкента на GitHub (A06-F004), geoBoundaries KAZ LFS (A12-F014/AST-A11-F002), неофициальный iKOMEK 109 (AST-A01-F007), утверждения A13 о тестах исходного репозитория (локальный прогон), данные STUPITS по районам Астаны (AST-A06-F028), A12 «27 из 33 наборов не открытые» и ключевые утверждения о госпорталах (с вердиктом «не проверено»).

## Воспроизведение
```bash
git checkout claude/dazzling-mayer-drhsxk
bash research/next-round/K08/verify_claims.sh /tmp/k08_work
```
