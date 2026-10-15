# Раунд 15 — где чья ветка

Реестр вести вручную не нужно: ветки раунда 15 находит скрипт по STATUS.md ролей.

```
python3 research/round-15/tools/find_branches.py            # все роли: ветка, SHA, когда последний коммит, поставка
python3 research/round-15/tools/find_branches.py --role R07 # все ветки одной роли, лучшая первой
python3 research/round-15/tools/find_branches.py --build    # последняя сборка R01 (BUILD.json)
python3 research/round-15/tools/find_branches.py --round 14 # то же по раунду 14 (проверка скрипта)
```

Соглашение: ветка роли — `claude/r15-<роль>`; если среда её не даёт — ветка сессии, а в STATUS первыми строками
«Роль: RXX» и «Ветка роли: <имя>». Скрипт выбирает ветку, где STATUS роли меняли последним.

## Ветки раунда 14 (только чтение; так их нашёл скрипт 15 октября и так их вёл координатор)

| Роль | Ветка раунда 14 | Поставка в FINAL-4 |
|---|---|---|
| R01 | claude/sharp-dijkstra-0t87gl | a4937462 (FINAL-4) |
| R02 | claude/r14-R02 | f62cc93 |
| R03 | claude/r14-R03 | 0164d64 |
| R04 | claude/r14-R04 | 8e2b2ae |
| R05 | claude/r14-R05 | 82d47a07 |
| R06 | claude/r14-R06 | 2f749aeb |
| R07 | claude/r14-R07 | 913b18a3 (новее — fe209c56) |
| R08 | claude/r14-R08 | d5719635 |
| R09 | claude/modest-shannon-0ki93p | 82056b7b |
| R10 | claude/r14-R10 | 656681ee |
| R11 | claude/r14-R11 | 2a30d7a2 |
| R12 | claude/tender-brahmagupta-ef5ztl | 016c93b5 |
| R13 | claude/r14-R13 | 0487f2a6 |
| R14 | claude/r14-R14 | 19715dbe |
| R15 | claude/r14-R15 | 540b4d3c |
| R16, R17 | — | новые роли раунда 15 |

База пакета: FINAL-4 `a4937462` — pytest 3601/0; R10 demo_flow 172/0/0 (с правкой шага 3); R15 r15_reference 18/0/0.
