# K01 round-3 — STATUS

**Статус: done** (малое задание «Контроль сохранности»).

## Сделано
- Прочитаны `research/round-3/snapshots.json` и `research/round-3/prompts/K01.txt` из
  `origin/codex/research-import-2026-10-05` @ `6602bb86f152d24edcb66f8b45122844323116bc`.
- Для каждой из 12 веток выполнен один `git fetch origin <branch>`. Проверено: коммит SHA есть,
  SHA входит в историю вершины ветки, файлы `research/next-round/KXX/` в этом коммите (путь, blob, размер, sha256).
- K03: основной источник `claude/epic-curie-iitc43` @ a8f1e17 (6 файлов); дополнительный —
  `claude/clever-mccarthy-pywscu` @ c534321, где тоже есть `research/next-round/K03/` (7 файлов). Разные K03 не сливались.
- Результат: `MANIFEST.json` (13 записей, все `status: ok`), скрипт `check_snapshots.py`.

## Итог проверки
| Слот | Ветка | Файлов в next-round/KXX |
|---|---|---|
| K01 | loving-thompson-nmajdo | 2 |
| K02 | clever-mccarthy-pywscu | 9 |
| K03 | epic-curie-iitc43 (осн.) / clever-mccarthy-pywscu (доп.) | 6 / 7 |
| K04 | beautiful-clarke-sbzomj | 5 |
| K05 | optimistic-davinci-1oiqs9 | 13 |
| K06 | ecstatic-curie-hzfzn0 | 27 |
| K07 | save-work-handoff-ku3ej3 | 14 |
| K08 | dazzling-mayer-drhsxk | 6 |
| K09 | save-work-handoff-qho6eq | 21 |
| K10 | save-work-handoff-j7pc05 | 27 |
| K11 | save-work-handoff-fmjw6r | 6 |
| K12 | save-work-handoff-xuav3q | 11 |

На момент проверки вершина каждой ветки совпадала с зафиксированным SHA (`tip_equals_sha: true`).
Для K01 это изменится после push этого коммита; зафиксированный 8e37ca8 остаётся в истории.

## Ограничения
- Проверялись только git-объекты. Содержание, научные выводы, города и provenance файлов не оценивались.
- Городские данные не скачивались; сеть использовалась только для git fetch с GitHub.
- Код приложения, main и чужие ветки не изменялись.

## Следующий шаг
Координатору: использовать `MANIFEST.json` (sha256 файлов) как контрольную точку при сборке
round-3; при расхождении K03 выбирать основной источник epic-curie.

## Воспроизведение
```bash
git fetch origin codex/research-import-2026-10-05
python3 research/round-3-results/K01/check_snapshots.py > /tmp/MANIFEST.json   # делает git fetch 12 веток
```
