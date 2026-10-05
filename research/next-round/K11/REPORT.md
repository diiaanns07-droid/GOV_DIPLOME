# K11. Аудит комплектности загруженной базы исследований

Дата: 2026-10-05. Исполнитель: слот K11 (Claude Code), ветка `claude/save-work-handoff-fmjw6r`.
Проверенное состояние: исходная ветка `codex/research-import-2026-10-05` @ `b87e5af`, влитая в рабочую ветку merge-коммитом `3c50b0e`. Файлы `research/*-results/`, `research/coordination/`, `research/README.md` и `CLAUDE.md` в `3c50b0e` побайтно совпадают с `b87e5af` (`git diff b87e5af HEAD` по этим путям пуст).

Это проверка **наличия файлов и ссылок**, а не истинности содержания. Скрипты исследователей не запускались. Ничего не удалено, не переименовано и не восстановлено.

## 1. Итог в пяти пунктах

1. **Отчёты и evidence:** Шымкент — 13/14 и 13/14, Астана — 13/14 и 12/14, как и в `coordination/STATUS.txt`. Подтверждено по Git-дереву.
2. **`AST_A10_evidence.json` отсутствует везде, где можно было проверить.** Его нет в рабочем дереве (поиск без учёта регистра), в `INVENTORY.json`, в 14 ветках `origin` на дату проверки и в истории их коммитов. Отчёт `AST_A10_report.md`, строка 5, перечисляет его среди своих файлов. Восстановить его можно только из исходного чата или экспорта. По тексту отчёта его не восстанавливал.
3. **Роль 14 (`14_synthesis_product_audit`):** ни одного файла результата ни в одном городе, ни в одной ветке, ни в истории. Есть только задания `research/{govtech,astana}-14/prompts/14_synthesis_product_audit.txt`.
4. **Новая находка:** в AST-A13 `SHA256SUMS.txt` перечисляет **16 файлов**: копии README и CITATION сторонних репозиториев. В экспорте **нет ни одного**. Отчёт `AST_A13_report.md`, строка 150, говорит «сохранены файлы и sha256». Сверить эти хэши невозможно, пока файлы не переданы.
5. **Транспортные вложенные архивы распакованы полностью** по README-командам: все объявленные результаты на месте. Но:
   - ссылки evidence записаны относительно корня ZIP (`r1/…`, `e1/…`), а в репозитории перед ними стоит каталог `extracted_*`;
   - входные GTFS-файлы зеркала не сданы;
   - для `r1/third_party_zero_profile.json` нет порождающего скрипта;
   - 2 CSV изменены переводом строк (CRLF→LF).

## 2. Отсутствующие файлы

Полный список: `K11_missing_files.csv`, 50 строк.

| Что отсутствует | Где ожидалось / кто ссылается | Найдено ли где-либо |
|---|---|---|
| `AST_A10_evidence.json` | `research/astana-results/10_safety/`. Ссылается `AST_A10_report.md` L5: «`AST_A10_evidence.json` — источники, факты, наборы, идеи, `city_comparison`» | **Нет.** Проверено: рабочее дерево, `INVENTORY.json`, 14 веток `origin`, `git log --all`. В `INVENTORY.json` у Астаны/10_safety ZIP нет, файлы лежат прямо в папке роли, вскрывать нечего |
| Отчёт и evidence роли 14, Шымкент | `research/govtech-results/14_synthesis_product_audit/` | Нет (только prompt) |
| Отчёт и evidence роли 14, Астана | `research/astana-results/14_synthesis_product_audit/` | Нет (только prompt) |
| 16 файлов из `SHA256SUMS.txt` (`gboeing_osmnx.README.md`, `SALib_SALib.CITATION.cff`, `UDST_urbansim.README.rst` и др.) | `research/astana-results/13_architecture_ai_thesis/extracted_files__34_/` | Нет. Это публичные файлы GitHub. Скачать их заново можно, но совпадение с хэшами автора не гарантировано |
| Скрипт профиля `bus_traffic_dataset.csv` | Результат `extracted_AST_A06_real_aggregates/r1/third_party_zero_profile.json`. README_REAL L2: «pandas — только для профиля стороннего CSV» | Нет. Ни один из `r1_*.py`, `r1b_*.py`, `r2_*.py` этот файл не создаёт и не упоминает |

**Входные данные скриптов, которые не сданы** (30 строк категории `script_input_not_shipped`). Это внешние наборы, не результаты агентов. Без них эксперименты не воспроизводятся:

| Скрипт | Нужные входы | Источник по словам автора |
|---|---|---|
| AST `r1_astana_regularity.py`, `r1b_sensitivity.py` | GTFS `trips.txt`, `routes.txt`, `stops.txt`, `calendar_dates.txt` | зеркало github.com/Mrithula742/Bussure @0356bb5b37ef (Zenodo 15769359). `stop_times.txt` автор сам получить не смог (Git LFS) |
| AST `AST_A12_experiments.py` | GTFS (то же зеркало), `ne_adm1.geojson`, `ne_pp.geojson`, `datasets_export.csv`, `byMIO.csv` | Natural Earth, egov-web-crawler, opengov-kz |
| SHY `a12_experiment.py` | `ne_adm1.geojson`, `ne_pp.geojson` | Natural Earth |
| AST `AST_A08_astana_real_checks.py`, `AST_A08_sensor_gap_real_geometry.py`; SHY `A08_airdata_sample_check.py` | `sensors.xlsx`, `layer_03_data_prepared_25.03.22.csv`, `air_quality_data.csv`, `темп_возд_KZ-AKM_Астана.csv` | сторонние GitHub-репозитории без лицензии (по словам автора) |
| AST `ast_a09_heating_experiment.py` | `weather3.csv` | Building Data Genome 1 |
| SHY `a09_bdg1_experiment.py` | `raw/meta_open.csv`, `raw/temp_open_utc.csv` | Building Data Genome 1 |

## 3. Неправильные локальные ссылки

Полный список: `K11_wrong_local_links.csv`, 86 строк. Во всех случаях **файл существует**, но ссылка в написанном виде из папки ссылающегося файла не разрешается.

**3.1. Неверный путь внутри роли (35 ссылок, `wrong_local_path`).**

| Ссылка как написано | Фактический путь (от `research/`) | Причина |
|---|---|---|
| `AST_A06_evidence.json`: `r1/results.json`, `r1/cv_sensitivity.json`, `r1/ptal_vs_observed.json`, `r1/trip_duration.csv`, `r1/third_party_zero_profile.json` | `astana-results/06_transport/extracted_files__28_/extracted_AST_A06_real_aggregates/r1/…` | путь относительно корня вложенного ZIP |
| `A06_evidence.json` (Шымкент): `e1/results.json`, `e2/results.json`, `e3/results.json`, `e1_flyover.py`, `e2_closure.py`, `e3_access.py` | `govtech-results/06_transport/extracted_files__15_/extracted_A06_experiments_synthetic/…` | то же |
| `AST_A09_evidence.json`: `AST_A09_attachments/*.csv`, `*.py` (4) | `astana-results/09_energy/extracted_files__31_/<имя>` | папка `*_attachments` в экспорте сплющена |
| `A09_evidence.json`: `A09_attachments/*` (5) | `govtech-results/09_energy/extracted_files__18_/<имя>` | то же |
| Выходы в скриптах `/home/claude/ast/…`, `/home/claude/exp/…`, `out/A03_multiseed_rows.jsonl` | рядом со скриптом в `extracted_*` | абсолютные пути песочницы автора и каталог `out/` |
| `README_REAL.md`, `r1_astana_regularity.py`: `regularity.csv`, `trip_duration.csv`, `sample_stops_5rows.json` | `…/extracted_AST_A06_real_aggregates/r1/` | имя без префикса `r1/`. Мелочь: в README рядом указано `r1/` |

**3.2. Ссылка в другую папку города или роли (46, `cross_city_or_role`).** Отчёты и evidence Астаны называют файлы первого прохода по Шымкенту голыми именами (`A01_evidence.json`, `A12_schema.sql` и т. д.). Все эти файлы есть в `govtech-results/<роль>/…`. Для чтения это не мешает. Для запуска мешают две ссылки:
- `astana-results/10_safety/ast_a10_experiment.py` L13 открывает `A10_sample_kpssu_shymkent_aggregates.json` из текущего каталога. Файл лежит только в `govtech-results/10_safety/`, поэтому скрипт в папке Астаны упадёт.
- `astana-results/12_data_gis/extracted_files__33_/AST_A12_experiments.py` L69 читает `/home/claude/a12/A12_schema.sql`. Файл лежит в `govtech-results/12_data_gis/extracted_files__20_/A12_schema.sql`.

**3.3. ZIP из ссылки не в Git (5 ссылок, `zip_not_in_git_unpacked`).** `AST_A06_real_aggregates.zip` и `A06_experiments_synthetic.zip` исключены `.gitignore`. Их содержимое распаковано в `extracted_AST_A06_real_aggregates/` и `extracted_A06_experiments_synthetic/` рядом.

**3.4. Абсолютные пути песочницы.** 14 из 43 скриптов зашиты на `/home/claude/...`: `stupits`, `bdg1`, `bussure`, `ast`, `exp`. Путь `/home/claude/stupits[/hack-d3b2c613-stupits-main]` соответствует корню этого репозитория на `834a25f`. Список: `scripts_with_absolute_sandbox_paths` в `k11_ref_audit.json`.

## 4. Вложенные транспортные материалы

| Пакет | Объявлено в README | В репозитории | Пробелы |
|---|---|---|---|
| Шымкент, `A06_experiments_synthetic.zip` → `govtech-results/06_transport/extracted_files__15_/extracted_A06_experiments_synthetic/` | `e1/results.json`, `e2/results.json`, `e3/results.json`, скрипты e1–e3 | всё есть, плюс 6 XML сетей E1 и `e2/closure.add.xml` | `grid.net.xml` и `river.net.xml` создаются при запуске (`netgenerate`/`netconvert`), их отсутствие нормально. Нужен SUMO 1.24.0 |
| Астана, `AST_A06_real_aggregates.zip` → `astana-results/06_transport/extracted_files__28_/extracted_AST_A06_real_aggregates/` | `r1/results.json`, `regularity.csv`, `trip_duration.csv`, `cv_sensitivity.json`, `ptal_vs_observed.json` | всё есть, плюс `sample_stops_5rows.json`, `third_party_zero_profile.json`, `versions.txt` | (1) нет входов GTFS (§2); (2) нет скрипта для `third_party_zero_profile.json`; (3) `regularity.csv` и `trip_duration.csv` отличаются от SHA256 в `INVENTORY.json` |

Сами ZIP в клоне отсутствуют, поэтому список членов архива сверить нельзя. Сверка шла по `INVENTORY.json`, который координатор составил после распаковки.

## 5. Целостность и дубликаты

- **SHA256 Git против `INVENTORY.json`:** 183 из 188 совпадают. 5 CSV Астаны (AST_A01, AST_A02, AST_A04 и два файла `r1/`) отличаются. Для всех пяти хэш из описи **точно воспроизводится заменой LF→CRLF**. Значит, данные не потеряны: перевод строк нормализован при коммите (размер меньше ровно на число строк). При сверке с исходным экспортом учитывать.
- **Вне Git:** 26 файлов описи, все `*.zip` (24 экспорта `files (N).zip` и 2 вложенных транспортных). Они исключены `.gitignore`, содержимое распаковано.
- **Дубликаты (не удалялись):** 5 пар `… (1).…` в `govtech-results/10_safety/` побайтно идентичны. Плюс намеренная копия `A02_priority_experiment.py` в Астане: SHA256 `c953a035…`, совпадает с хэшем, заявленным в `AST_A02_report.md`.

## 6. Что сделано и как классифицированы ссылки

Скрипт `k11_ref_audit.py` извлекает пути из всех отчётов, evidence, README, txt, sql и скриптов в `research/*-results/`:
- в Markdown и тексте — по строкам;
- в JSON — по строковым значениям с JSON-путём;
- в коде — по литералам.

Затем он разрешает каждую ссылку по Git-дереву и `INVENTORY.json`. Всего 855 уникальных пар «файл → ссылка»:

| Категория | Число | Смысл |
|---|---:|---|
| ok | 488 | разрешается как написано |
| app_repo_file | 71 | файл приложения (`data/`, `docs/`, `agent/`), есть в репозитории |
| wrong_local_path | 35 | §3.1 |
| cross_city_or_role | 46 | §3.2 |
| zip_not_in_git_unpacked | 5 | §3.3 |
| missing_deliverable | 1 | `AST_A10_evidence.json` |
| missing_listed_in_checksums | 16 | §2, AST-A13 |
| script_input_not_shipped | 30 | §2, входы скриптов |
| external_third_party_file | 117 | имена файлов сторонних репозиториев и наборов (GTFS, README, `robots.txt`, `config.py` с чужим ключом и т. п.). Сдавать их не требовалось |
| proposed_not_implemented | 22 | предложенные будущие файлы (`config/astana.json`, `registry/sources.jsonl`, схемы `stops.csv` и т. п.) |
| generated_at_runtime_or_tool | 3 | файлы, создаваемые SUMO при запуске |
| placeholder | 7 | аргументы CLI и временные файлы (`card.json`, `/tmp/h.txt`, `--out results.json`) |
| parse_artifact | 14 | ложные срабатывания разбора (`np.log`, `area.a`, координаты) |

Все 206 ссылок со статусом `not_found` я просмотрел вручную на этом коммите: 183 в первом прогоне и 23 новых после добавления абсолютных путей и `.rst`. Решения зашиты в таблицы правил скрипта (`MISSING_DELIVERABLE`, `PROPOSED`, `PLACEHOLDER` и др.), чтобы их можно было перепроверить.

## 7. Ограничения

- Разбор эвристический. Ссылки, записанные без расширения или словами («приложенный архив»), не ловятся. Категория `external_third_party_file` назначена по ручному просмотру: если там спрятан чей-то сданный файл, его надо поднять в `MISSING_DELIVERABLE`.
- Интернет не использовался: задача локальная. Существование сторонних файлов (GTFS, README) на GitHub не проверялось.
- Скрипты исследователей не запускались, только читались, чтобы понять ввод-вывод. Истинность чисел не проверялась.
- Исходные ZIP в облачной сессии недоступны. Членство архивов и «правильный» CRLF-вариант проверены только через `INVENTORY.json`.

## 8. Воспроизведение

```bash
git fetch origin codex/research-import-2026-10-05   # b87e5af
python3 research/next-round/K11/k11_ref_audit.py    # перезаписывает только k11_ref_audit.json и два CSV в этой папке
git log --all --name-only --format= | grep -i 'AST_A10_evidence'   # пусто
```
Python 3.11, только стандартная библиотека.
