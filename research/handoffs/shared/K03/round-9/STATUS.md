# Handoff K03 · round 9

- Агент: Claude Code, ветка `claude/epic-curie-iitc43` (слот K03 по `research/round-9/snapshots.json`), не BUILD.
- Закреплённая сборка: `d865dd4a124291e10dd0b7bb1d9eada20d34c268`; дерево прототипа = `3e1302a`.
- Явно проверенные новые SHA BUILD:
  - `e1cbc3fa84518a84698c03d014dc153f71338d54` — `web/resilience.js`;
  - `d18847f9e7c18fcfae3349c0b223b023d359a838` — последняя на 2026-10-06.
- Результаты: `research/round-9-results/K03/` — `STATUS.md`, `HANDOFF.md`, `CASES_API.md`, `patches/README.md`.
- Этап 1: **done**. PASS 10 на всех трёх SHA. Отрицательный контроль: 5/5.
- Этап 2: **done**. `resilience_cases.js` и оракул, 211 fixtures. PASS 8 на всех трёх SHA. Отрицательный контроль: 7/7.
- Этап 3: **done**.
  - d865dd4: PASS 8, часть устойчивости NOT_RUN — `resilience.js` нет.
  - e1cbc3f и d18847f: PASS 16, INFO 1.
  - Отрицательный контроль: 5/5.
  - Кейсы Шымкента и Астаны — в `cases/`. У Астаны нет группы COLOCATED: показано статусом `no_qa_group`, группа не создана.
- Предложение BUILD: `patches/build_d18847f_k03_same_coords_label.patch` (P1 — подсказка общих координат, P2 — одиночный суррогат в подписи). Не применено. Тесты сборки до и после одинаковы: 112/112, 164/164, браузер 40/40.
- Следующий шаг:
  - BUILD решает по P1/P2;
  - координатор задаёт единое правило подписи случаев;
  - на новом SHA перезапустить `run_stage{1,2,3}.py`.
