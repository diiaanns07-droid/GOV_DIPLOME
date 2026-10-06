# K07 · Раунд 9 · HANDOFF

Ветка `claude/save-work-handoff-ku3ej3`. Подробности — `STATUS.md`. Запись координатору — `research/handoffs/shared/K07/round-9/STATUS.md`.

| Этап | Статус |
|---|---|
| 1. K2–K5 на `d865dd4`, оценка N2, патч на копии | готово: K2–K5 воспроизведены, с патчем PASS; N2 — не дефект (данные не теряются, область достижима с клавиатуры), область получила role, имя и tabindex. Интеграция: **NOT_RUN** (нового SHA BUILD нет) |
| 2. Панель «Устойчивость к допущениям» (патч) | в работе |
| 3. Браузерные тесты страницы на 390 px и desktop | в работе |

## Команды

```bash
git fetch origin claude/beautiful-clarke-sbzomj
export NODE_PATH="$(npm root -g)"
bash research/round-9-results/K07/scripts/run_r9_review.sh             # d865dd4 как есть и d865dd4 + патчи K07 r9 (копия)
bash research/round-9-results/K07/scripts/run_r9_review.sh <NEW_SHA>   # новый BUILD как есть — проверка интеграции
```

## Для BUILD

`patch/build_d865dd4_r9_keyboard.patch` правит строки `app.js` и `plan-ui.js`, применяется `git apply -p1` к `d865dd4`. В отличие от патча r8, раскладка таблицы Парето не меняется (решение REVIEW r9).
