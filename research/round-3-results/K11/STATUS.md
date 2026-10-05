# K11 round 3 — STATUS

Задача: K11 «Малый аудит конфликтов» (`research/round-3/prompts/K11.txt`).
Агент: слот K11, Claude Code, ветка `claude/save-work-handoff-fmjw6r`. Город: shared.
Обновлено: 2026-10-05, UTC.
Статус: **ready_for_review**.
Исходные данные:
- назначения: `origin/codex/research-import-2026-10-05` @ `6602bb86f152d24edcb66f8b45122844323116bc`, файл `research/round-3/snapshots.json`;
- база: `b87e5af6eeb6a5bdc33037a9f16d4e3377166ee5`;
- мой предыдущий результат: `677b305` (`research/next-round/K11/`, не изменялся).

Назначенный путь: `research/round-3-results/K11/`.

## Что сделано

- Получены 12 назначенных веток (только `git fetch`). Все 12 SHA снимков доступны, база — предок каждого.
- Для каждого снимка получен список изменённых файлов относительно базы. Найдены пересечения путей, записи в чужие папки, изменения продукта и общих файлов.
- Две версии `territory_registry` в K03 сравнены по id git-blob и по структуре: столбцы, строки, ID, поля общих OSM relation. Содержимое не выбиралось, merge не выполнялся.

## Результат

1. Конфликтов путей два, оба в K03: `research/next-round/K03/territory_registry.csv` и `.json`, у K02 `c534321` и K03 `a8f1e17`. **Байты различаются.** Владелец следующего раунда — K03, `claude/epic-curie-iitc43`.
2. Ветка K02 записала в папки K03 8 файлов: 7 в `next-round/K03/` и handoff в `handoffs/shared/K03/`. Остальные 10 веток пишут только в свои папки.
3. Файлы продукта (вне `research/`) и общие файлы координатора/импорта не менялись ни в одной ветке. Во всех 179 изменениях статус A, изменений и удалений нет.
4. Реестры: по 18 строк, разные схемы (21 и 27 столбцов).
   - 8 общих ID и поля 6 районов Астаны совпадают.
   - Расходятся 5 соседних территорий: у K02 есть ID, у K03 ID пустой.
   - Расходятся 5 районов Шымкента: у K02 коды КПСиСУ без названий, у K03 названия-гипотезы без кодов.
5. K01 ушёл вперёд снимка (`50df8eb`, только `round-3-results/K01/`). В аудите использован снимок.

## Файлы результата

- `research/round-3-results/K11/CONFLICTS.json` — по веткам; конфликты с blob/байтами/владельцем; записи в чужие папки; сравнение реестров.
- `research/round-3-results/K11/INTEGRATION_NOTES.txt` — читаемые выводы и рекомендация координатору.
- `research/round-3-results/K11/k11_conflicts.py` — генератор `CONFLICTS.json`, только чтение Git.
- `research/round-3-results/K11/STATUS.md` — этот файл.

## Проверки (реально выполнены)

- `git cat-file -e <sha>^{commit}` и `git merge-base --is-ancestor b87e5af <sha>` для 12 снимков: все доступны, база — предок.
- `python3 research/round-3-results/K11/k11_conflicts.py`: exit 0. Итог: `{"branches_checked": 12, "path_conflicts": 2, "folder_intrusions": 8, "branches_with_product_changes": [], "branches_with_coordinator_file_changes": [], "non_add_changes": {}}`.
- `json.load(CONFLICTS.json)`: успешно. Сумма `changed_files` = 179.
- Байты сравнены по `git rev-parse <sha>:<path>` (id blob) и `git cat-file -s`.
- Не запускалось: чужие скрипты (`build_registry.py`, `k03_geometry.py`, `k03_geo_verify.py` и др.) и тесты приложения (код продукта не менялся).

## Ограничения

- Интернет не использовался: задание локальное.
- Сравнение реестров — сверка файлов между собой, без проверки фактов по первоисточникам.
- Записи в чужие папки определяются по соглашению имён папок (`next-round/KXX`, `handoffs/shared/KXX`, `round-3-results/KXX`). Папки с именем сессии (`handoffs/shared/claude-epic-curie-iitc43/`) назначенным слотом не считаются.

## Следующий шаг

1. K03 (epic-curie) решает, какой реестр основной. Нужное из `c534321` переносит в свою ветку под новыми именами, без merge веток K02 и K03. Нужен источник, связывающий коды КПСиСУ 197910–197914 с названиями районов Шымкента.

## Воспроизведение

```bash
git fetch origin codex/research-import-2026-10-05
git fetch origin $(git show origin/codex/research-import-2026-10-05:research/round-3/snapshots.json \
  | python3 -c "import json,sys;print(' '.join('+refs/heads/%s:refs/remotes/origin/%s'%(a['branch'],a['branch']) for a in json.load(sys.stdin)['assignments']))")
python3 research/round-3-results/K11/k11_conflicts.py   # Python 3.11, stdlib; пишет только CONFLICTS.json
```
