# K03 round 9 — HANDOFF

**Кто и что.** Claude Code, ветка `claude/epic-curie-iitc43`, слот K03 «чувствительность к качеству координат», не BUILD.

**Проверено.**
- Закреплённая сборка: `d865dd4`.
- Явно, по новым SHA BUILD: `e1cbc3f` и `d18847f`. Последний на 2026-10-06; движок и данные у него те же, что у `e1cbc3f`.

Подробности, таблицы и команды — `STATUS.md`.

## Что готово

1. **Этап 1.** Адаптер `plan_adapter.cjs` к настоящему `plan.js` и прогон r8 geo-fixtures (`run_stage1.py`). Проверены:
   - nearest/ties/QA на всех 55 настоящих записях школ и поликлиник;
   - 800 synthetic строк;
   - «совпадающие координаты ≠ дубликат».
2. **Этап 2.** Модуль `resilience_cases.js` и независимый оракул `resilience_cases_ref.py`.
   - Случаи создаются только явным выбором: одна запись, группа, указанная QA-группа.
   - Есть manifest provenance на базовом срезе.
   - 211 fixtures. API — `CASES_API.md`.
3. **Этап 3.**
   - Кейсы Шымкента и Астаны (`cases/`).
   - Проверки фильтрации на `plan.js` и `web/resilience.js` (`run_stage3.py`, `resilience_adapter.cjs`).
   - Независимый перебор `robust_ref.py`.
   - Патч-предложения P1/P2 (`patches/`) с проверкой в браузере и тестами сборки.

## Что важно знать следующему

- **Ничьи в общих координатах.** В Шымкенте 14 записей стоят группами в одних координатах. Исключение одной из них не меняет расстояние — это верно, но в UI неочевидно. P1 добавляет подсказку; в сборку она не внесена.
- **Астана.** Групп COLOCATED нет. Модуль честно возвращает `no_qa_group`, сборка групп тоже не создаёт.
- **Политика подписей.** Различия K03 и сборки — `patches/README.md`. Решение за координатором; эталон по ответу сборки я не менял.
- **Erratum к моему r8 STATUS.** «Астана — пара поликлиник без COLOCATED» неверно: в Астане внутри категорий школ и поликлиник общих координат нет.

## Как перепроверить новый SHA BUILD

```bash
git fetch origin claude/beautiful-clarke-sbzomj
python3 research/round-5-results/K03/extract_build.py --sha <SHA> --out /tmp/appN
for s in 1 2 3; do python3 research/round-9-results/K03/run_stage$s.py --app-root /tmp/appN --target-sha <SHA> --json /tmp/s$s.json; done
```

- Если `data.js`/`evidence.js` изменились, результат — TEST_INCOMPATIBLE. Тогда пересоздать fixtures: `make_stage1_scan.py`, `make_stage2.py`, `make_stage3.py` с `--app-root /tmp/appN --target-sha <SHA>`.
- Если в сборке нет `web/resilience.js`, часть B этапа 3 = NOT_RUN.

## Открыто / следующий шаг

- BUILD решает, принять ли P1/P2: `git apply research/round-9-results/K03/patches/build_d18847f_k03_same_coords_label.patch`. После этого перепроверить: `run_stage3.py` и `ui_same_coords_check.cjs` должны дать PASS.
- Координатор решает, какое правило подписи случаев единое. После этого выровнять модуль K03 и fixtures.
- Не сделано:
  - раскрытие ничьей в таблице плана v2 (`plan-ui.js`, nearest_before) — отмечено на этапе 1, патча нет;
  - Windows и другие браузеры — NOT_RUN.
