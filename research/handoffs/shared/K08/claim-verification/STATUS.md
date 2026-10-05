# STATUS — K08, независимая проверка утверждений

**Статус:** partial. Проверено 10 основных утверждений и 2 дополнительных: 9 подтверждены (у двух часть не проверена), 0 опровергнуто, 3 не проверены — их первоисточники заблокированы. «Partial» стоит потому, что утверждения о госпорталах и СМИ (V10–V12) ждут разрешённого доступа.

- Задача: проверить 10 MVP-важных утверждений из исследований обоих городов по первоисточникам (CLAUDE_CAPACITY_12.txt, K08).
- Репозиторий / ветка: `diiaanns07-droid/GOV_DIPLOME`, `claude/dazzling-mayer-drhsxk`. В ветку обычным merge влита `codex/research-import-2026-10-05` @ b87e5af. В main ничего не мержилось.
- Результаты: `research/next-round/K08/`
  - `REGISTRY.md` — таблица: утверждение, исходный ID, источник, дата, вердикт, объяснение, итог для MVP;
  - `registry.json` — те же данные в машиночитаемом виде, `render_registry.py` строит из него таблицу;
  - `verify_claims.sh` — команды воспроизведения V01–V09 и V12; `run_log.txt` — вывод последнего полного прогона;
  - `ACCESS_LOG.md` — какие хосты доступны и какие заблокированы.

## Вердикты
| # | Исходные ID | Вердикт |
|---|---|---|
| V01 | AST-A06-F007/F008/F009 (AVL Астаны, Bussure) | подтверждено |
| V02 | AST-A06-F019/F020 (сборщик api.citytransport.kz, одни нули) | подтверждено |
| V03 | AST-A06-F005/F006, A06-F004 (нет GTFS KZ в каталогах) | подтверждено; поиск GitHub не проверен |
| V04 | AST-A11-F003/F004, AST-A06-F002/F028/F004 (OSM-границы Астаны в продукте) | подтверждено |
| V05 | AST-A01-F004 (политика iKOMEK 109, 13.03.2019) | текст подтверждён; официальность не проверена |
| V06 | AST-A01-F007 (неофициальная ikomek_platform) | подтверждено |
| V07 | A13-F001/F002 (112 тестов, check.py 12/12) | подтверждено прогоном |
| V08 | A12-F010/F011 (Natural Earth: Шымкента как единицы нет) | подтверждено |
| V09 | A08-F005/F006 (AirData, посты Казгидромета в Шымкенте) | подтверждено с уточнением периода |
| V10 | A10-F017 (I-Shymkent 109, январь–июль 2026) | не проверено: inform.kz заблокирован |
| V11 | A10-F024 (наборы data.egov.kz по Шымкенту) | не проверено: data.egov.kz заблокирован |
| V12 | A08-F012 (данные Казгидромета по запросу) | не проверено: репозиторий пуст, API недоступен |

## Проверки, которые реально выполнены
- Пересчёт по сырым файлам публичных репозиториев (git clone, raw.githubusercontent.com) и по data/ GOV_DIPLOME.
- `pytest -q` дал 112 passed; `check.py` завершился с кодом 0, 12/12 (Python 3.11.15, numpy 2.4.6, pytest 9.1.1; отдельный worktree 834a25f, затем удалён).
- Полный повторный прогон `verify_claims.sh` завершился с кодом 0, вывод в `run_log.txt`.
- `python3 -m json.tool registry.json` — только синтаксис, фактом не считается.
- Исходники приложения и старые отчёты не изменялись.

## Ограничения сети
data.egov.kz, stat.gov.kz, gov.kz, opendata.kz, openstreetmap.org, overpass-api.de, zenodo.org, doi.org, mdpi.com, api.citytransport.kz, cts.gov.kz, www.inform.kz — 403 / EGRESS_BLOCKED. GitHub API ограничен репозиториями сессии, search API недоступен. Каждый хост проверялся один раз, повторных попыток не было.

## Гипотезы и вторичные данные
Цифры V10 из WebSearch — пересказ поисковой выдачи, а не первоисточник. Выводы «для MVP» в REGISTRY.md — интерпретация K08.

## Нерешённые вопросы
- V10: точные число и рейтинг категорий I-Shymkent 109; расхождение +20% против ≈+15,8%.
- V11: что сейчас есть на data.egov.kz по Шымкенту и Астане.
- Официальность ikomek/ikomek109 и текущая работа iKOMEK 109.
- Лицензия AirData_Shymkent (её нет) и Bussure/Zenodo (CC BY 4.0 только по READ-ME).

## Следующий шаг
Из среды с доступом к data.egov.kz и inform.kz (или по файлам с provenance от K10) проверить V10 и V11 и обновить их записи в `registry.json`, затем выполнить `python3 render_registry.py`.

## Воспроизведение
```bash
git checkout claude/dazzling-mayer-drhsxk
python3 -m venv /tmp/k08v && /tmp/k08v/bin/pip install numpy pytest openpyxl
GOV_DIPLOME_ROOT=$PWD PYTHON=/tmp/k08v/bin/python bash research/next-round/K08/verify_claims.sh /tmp/k08_work
python3 research/next-round/K08/render_registry.py
```
