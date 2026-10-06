# K07 · Раунд 9 · HANDOFF

Ветка `claude/save-work-handoff-ku3ej3`. Подробности — `STATUS.md`. Запись координатору — `research/handoffs/shared/K07/round-9/STATUS.md`.

| Этап | Статус |
|---|---|
| 1. K2–K5 на `d865dd4`, оценка N2, патч на копии | готово: K2–K5 воспроизведены, с патчем PASS; N2 — не дефект (данные не теряются, область достижима с клавиатуры), область получила role, имя и tabindex. Интеграция: **NOT_RUN** (нового SHA BUILD нет) |
| 2. Панель «Устойчивость к допущениям» (патч) | готово: адаптер к `plan.js` BUILD 61/61 (Python-оракул), панель 20/20 в браузере на копии `d865dd4` + патчи; в BUILD — NOT_RUN |
| 3. Браузерные тесты страницы на 390 px и desktop | в работе |

## Команды

```bash
git fetch origin claude/beautiful-clarke-sbzomj
export NODE_PATH="$(npm root -g)"
bash research/round-9-results/K07/scripts/run_r9_review.sh             # d865dd4 как есть и d865dd4 + патчи K07 r9 (копия)
bash research/round-9-results/K07/scripts/run_r9_review.sh <NEW_SHA>   # новый BUILD как есть — проверка интеграции
```

## Для BUILD

- `patch/build_d865dd4_r9_keyboard.patch` правит строки `app.js` и `plan-ui.js`, применяется `git apply -p1` к `d865dd4`. В отличие от патча r8, раскладка таблицы Парето не меняется (решение REVIEW r9).
- `patch/build_d865dd4_r9_resilience_panel.patch` применяется после него: `index.html` и два новых файла `web/resilience_k07.js`, `web/resilience_panel_k07.js`. Свой `resilience.js` BUILD делает сам; панель возьмёт его через `window.CITY_RESILIENCE` (API — `API.md`).
