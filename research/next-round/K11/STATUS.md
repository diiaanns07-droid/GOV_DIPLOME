# K11 — STATUS

Задача / идентификатор: K11, небольшой аудит комплектности загруженной базы исследований (отчёты, evidence, файлы, на которые они ссылаются; особое внимание — `AST_A10_evidence.json` и вложенные транспортные материалы).
Агент / город / сфера: слот K11, Claude Code (сессия `session_01MRqqVxeuDmJHvqzCYTKXv8`) / shared: Шымкент и Астана раздельно / комплектность данных.
Обновлено: 2026-10-05, UTC.
Статус: **ready_for_review** (запрошенный аудит выполнен; восстановление отсутствующих файлов вне полномочий K11).
Рабочая ветка: `claude/save-work-handoff-fmjw6r`.
Исходный коммит: `codex/research-import-2026-10-05` @ `b87e5af6eeb6a5bdc33037a9f16d4e3377166ee5`, влит обычным merge (`3c50b0e`). Прежние коммиты ветки сохранены, без reset и force push.
Назначенные пути: `research/next-round/K11/`.

## Цель и критерий готовности

Есть машиночитаемый и читаемый список: (1) отсутствующих файлов; (2) ссылок, которые не разрешаются как написаны, с фактическим путём, если файл есть. По `AST_A10_evidence.json` проверены все доступные места.

## Что реально сделано

- Прочитаны `CLAUDE.md`, `research/README.md`, `coordination/STATUS.txt`, `FIRST_REVIEW.txt`, `CLAUDE_CAPACITY_12.txt` (раздел K11) и `prepare_results.py`. Последний не запускался: он перезаписывает `INVENTORY.json` и `STATUS.txt` координатора.
- Написан read-only скрипт `k11_ref_audit.py`. Он извлёк 855 уникальных ссылок из отчётов, evidence, README и скриптов и разрешил их по Git-дереву и `INVENTORY.json`. Все 206 неразрешённых ссылок просмотрены вручную, решения зашиты в правила скрипта.
- Сверены SHA256 Git с `INVENTORY.json`. Проверены дубликаты.
- Прочитан ввод-вывод скриптов с межпапочными ссылками: AST-A06 r1/r1b/r2, SHY-A06 e1–e3, `ast_a10_experiment.py`, `AST_A12_experiments.py`, `A02_priority_experiment.py`, `A03_multiseed.py`.
- Поиск `AST_A10_evidence.json` и результатов роли 14:
  - в рабочем дереве;
  - в `INVENTORY.json`;
  - во всех 14 ветках `origin` на дату проверки (только чтение `git fetch`, чужие ветки не изменялись);
  - в `git log --all`.

## Главные результаты

1. `AST_A10_evidence.json` **не найден нигде**. Ссылка на него: `AST_A10_report.md` L5. Содержание не восстанавливалось.
2. Роль 14: результатов нет в обоих городах, есть только prompts.
3. Новое: 16 файлов из `astana-results/13_architecture_ai_thesis/extracted_files__34_/SHA256SUMS.txt` отсутствуют, хотя отчёт (L150) пишет, что они сохранены.
4. Транспорт:
   - все объявленные результаты обоих вложенных пакетов на месте;
   - ссылки evidence `r1/…` и `e1/…` не учитывают каталог `extracted_*`;
   - входы GTFS не сданы;
   - для `r1/third_party_zero_profile.json` нет скрипта.
5. 35 ссылок с неверным путём внутри роли, 46 межгородских ссылок голыми именами. Из них два запуска ломаются: `ast_a10_experiment.py` L13 и `AST_A12_experiments.py` L69. Ещё 14 из 43 скриптов используют пути `/home/claude/...`.
6. 5 CSV отличаются от SHA256 описи. Для всех пяти хэш описи воспроизводится заменой LF→CRLF, то есть меняется только перевод строк, данные целы.

## Файлы результата

- `research/next-round/K11/REPORT.md` — выводы и таблицы.
- `research/next-round/K11/K11_missing_files.csv` — 50 строк: роли, `AST_A10_evidence.json`, 16 файлов контрольных сумм, 30 несданных входов скриптов.
- `research/next-round/K11/K11_wrong_local_links.csv` — 86 строк: ссылка как написана и фактический путь.
- `research/next-round/K11/k11_ref_audit.json` — полный разбор: все ссылки, категории, роли, целостность, дубликаты, абсолютные пути.
- `research/next-round/K11/k11_ref_audit.py` — генератор трёх файлов выше.
- `research/next-round/K11/STATUS.md` — этот файл.

## Проверки

- `python3 research/next-round/K11/k11_ref_audit.py`: exit 0, 855 ссылок; категории в REPORT §6.
- `json.load` нового `k11_ref_audit.json`: успешно (проверено перед commit).
- `sha256sum` двух копий `A02_priority_experiment.py`: обе `c953a035…`, совпадает с `AST_A02_report.md`.
- `git diff b87e5af HEAD -- research/*-results research/coordination research/README.md CLAUDE.md`: пусто, файлы импорта не изменены.
- `git log --all --name-only | grep -i AST_A10_evidence`: пусто.
- Не запускалось: скрипты исследователей (только чтение кода) и тесты приложения (код приложения не менялся).

## Доказательства и ограничения

- Интернет не использовался: задача локальная, внешние источники не нужны.
- Разбор ссылок эвристический (regex). Ссылки словами или без расширения не ловятся.
- Исходные ZIP недоступны облачной сессии. Членство архивов и исходный перевод строк проверены только через `INVENTORY.json`.
- Синтетики и гипотез в этой работе нет. Всё это наблюдения над файлами репозитория.

## Незавершённое

- Отсутствующие файлы можно вернуть только из исходных чатов или экспортов владельца. K11 их не восстанавливает.
- Исправление ссылок в чужих отчётах сознательно не делалось: старые отчёты не переписываются.

## Следующий конкретный шаг

1. Владелец или координатор ищет в исходном экспорте AST-A10 (чат роли 10 по Астане) файл `AST_A10_evidence.json`, а в экспорте AST-A13 — 16 файлов из `SHA256SUMS.txt` и скрипт профиля `bus_traffic_dataset.csv`. Найденное кладётся рядом с отчётами без изменений. После этого координатор перезапускает `prepare_results.py`, а K11 повторяет `k11_ref_audit.py`.

## Для воспроизведения

```bash
git fetch origin codex/research-import-2026-10-05 claude/save-work-handoff-fmjw6r
git checkout claude/save-work-handoff-fmjw6r
python3 research/next-round/K11/k11_ref_audit.py   # Python 3.11, только stdlib; пишет только в research/next-round/K11/
git log --all --name-only --format= | grep -i 'AST_A10_evidence'
```

## Известные конфликты и зависимости

- Пересечение с K01 (`claude/loving-thompson-nmajdo`, `research/next-round/K01/`) отсутствует: разные папки.
- В ветке также лежит мой прежний checkpoint `research/handoffs/unassigned/claude-session_01MRqqVxeuDmJHvqzCYTKXv8/…`. Он не изменялся.
- `INVENTORY.json` и `STATUS.txt` координатора не изменялись.
