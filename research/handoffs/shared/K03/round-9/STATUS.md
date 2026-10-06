# Handoff K03 · round 9

- Агент: Claude Code, ветка `claude/epic-curie-iitc43` (слот K03 по `research/round-9/snapshots.json`), не BUILD.
- Проверенная сборка: `d865dd4a124291e10dd0b7bb1d9eada20d34c268`; код = `3e1302a` (дерево прототипа совпадает).
- Результаты: `research/round-9-results/K03/` — подробности в `STATUS.md`.
- Этап 1: **done**. PASS 10 / FAIL 0. Отрицательный контроль: 5/5 испорченных копий пойманы.
- Этап 2: в работе (case-builder исключений ID). Этап 3: не начат.
- Интеграция устойчивости в BUILD: на d865dd4 её нет; не проверялась.
- Следующий шаг: этап 2. Создать `resilience_cases.js` и Python-оракул, fixtures обоих городов, sidecar provenance исключаемых ID.
