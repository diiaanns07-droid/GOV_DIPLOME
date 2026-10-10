# R01 — журнал сборки раунда 14

## I0 — шаг 1: перенос путей (без патчей)

База: `claude/round-14-package` @ af77b78 (= c076569 + research/round-14). После 56538a3 база меняла только research/,
поэтому поставки раунда 13, сделанные от 56538a3, совместимы с базой.

| Модуль | Пути | Источник (ветка @ SHA) | Код поставки |
|---|---|---|---|
| оболочка R01 р.13 | web/index.html, web/style.css, web/map.js, web/interface.js, web/civic/shell/, ui/web_server.py, tests/civic/R01/ | claude/affectionate-ride-bol5v8 @ cb9d60a | b137df9 (+ handoff) |
| хранилище объектов | ui/civic_store/, tests/civic/R02/ | claude/elegant-franklin-jbhprq @ 26793c8 | b9eb180 |
| карта | web/civic/map/, tests/civic/R03/ | claude/zen-mendel-e79iiv @ 7de5e0b | f0a52f7 (пути идентичны) |
| редактор | web/civic/editor/, tests/civic/R04/ | claude/intelligent-sagan-7shpeh @ 9c996c6 | 9c996c6 |
| жалобы v1 | ui/civic_feedback/, web/civic/feedback/, tests/civic/R06/ | claude/focused-hypatia-z8h0no @ 933cd90 | 12b3170 |
| сценарии | engine/civic_scenarios/, web/civic/scenarios/, tests/civic/R07/ | claude/brave-hopper-bkc58b @ 16aa37a | 1197f7d |
| помощник | agent/civic_assistant/, web/civic/assistant/, tests/civic/R09/ | claude/wizardly-ptolemy-qy8ltw @ 14c3384 | c46b2ed |
| классификатор v1 | ml/civic_classifier/, tests/civic/R08/ | claude/wizardly-ptolemy-qy8ltw @ 14c3384 | = дерево в cb9d60a (5824fab) |
| проверенные данные | data/civic/astana/round12-verified/, data/civic/astana/round13-verified/, tests/civic/R05/round12/, tests/civic/R05/round13/ | claude/fervent-dijkstra-1cqrg5 @ a995f9f | a995f9f |

Проверки до запуска:
- Удалений файлов нет ни в одном источнике (`git diff --diff-filter=D HEAD <sha> -- <пути>` пусто).
- Ветки R06/R07/R09 построены от старого main (834a25f); их пути побитно совпадают с `56538a3 + *_vs_56538a3.patch`
  (сравнение деревьев `write-tree`), т. е. перенос путей = поставка, без чужой истории.
- Код прочитан на сеть/процессы: сеть только в ручной команде R05 `r12.py fetch` (pytest её не вызывает);
  тесты поднимают локальные HTTP-серверы и вызывают python/node.

Внимание для ролей раунда 14: папки tests/civic/R02…R09 сейчас содержат тесты раунда 13 по СТАРОЙ нумерации ролей
(R02 = хранилище, R03 = карта, R04 = редактор, R05 = данные, R06 = жалобы, R07 = сценарии, R08 = классификатор v1,
R09 = помощник). Новые тесты раунда 14 кладите в новые файлы своих папок; старые тесты не удаляйте без согласования с R01.
