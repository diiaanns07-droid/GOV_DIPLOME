# R05 раунд 12 — подтверждённые работы, стройки и события Астаны

- Роль: R05. Ветка: `claude/focused-hypatia-z8h0no` (назначена средой; прежде здесь была работа R06 раунда 11, 73f9576).
- CODE_BASE_SHA: `56538a3a7504d4589c38ab4d3c5107f12aa7f8a6`; пакет раунда 12: origin/codex/govtech-main-interface @19f90e6.
- **BASE_MISMATCH:** перевести ветку на 56538a3 не удалось (merge `-s ours` отклонён автоматической проверкой
  как разрушительная git-операция; force push запрещён). Мои коммиты раунда 12 трогают только новые пути R05,
  проверка выполняется в отдельном worktree от 56538a3, переносимый патч — в `research/round-12-results/R05/`.
- Пути: `data/civic/astana/round12-verified/`, `tests/civic/R05/round12/`, `research/round-12-results/R05/`, этот файл.

## Статус: PARTIAL — checkpoint 1

- Сеть: все KZ-источники, OSM и wikipedia.org закрыты политикой egress (proxy 403 / WebFetch EGRESS_BLOCKED),
  журнал `data/civic/astana/round12-verified/network_audit.json`. Работает только серверный WebSearch
  (заголовки + URL + пересказ) — пригоден для поиска кандидатов, не для подтверждения.
- Сделано: схема пакета `SCHEMA.md`, `config.json`, README, журнал сети.
- В работе: поиск кандидатов (6 поисковых срезов + 3 скептика), инструмент `tools/r12.py`
  (verify по дословным выдержкам, build пакета, геокодирование по OSM-снимку), тесты.

Следующий шаг: реестр источников и кандидатов из результатов поиска, затем `tools/r12.py` и тесты.
