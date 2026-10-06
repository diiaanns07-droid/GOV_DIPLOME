# K07 · Раунд 9 · HANDOFF

Ветка `claude/save-work-handoff-ku3ej3`. Подробности — `STATUS.md`. Запись координатору — `research/handoffs/shared/K07/round-9/STATUS.md`.

| Этап | Статус |
|---|---|
| 1. K2–K5 на `d865dd4`, оценка N2, патч на копии | готово. K2–K5 воспроизведены на `d865dd4`; **исправлены у BUILD** — на `d18847f` браузер r8 31/31. N2 — не дефект; на `d18847f` переполнения нет |
| 2. Панель «Устойчивость к допущениям» (патч) | готово как предложение для `d865dd4` (адаптер 77/77, панель 25/25 на копии). **Заменено** панелью BUILD (`resilience-ui.js`) |
| 3. Браузерные тесты страницы на 390 px и desktop | готово на закреплённом **`d18847f9e7c18fcfae3349c0b223b023d359a838`**: движок BUILD = оракул K07 69/69; панель BUILD 32/36 — дефекты D1 (клик человека после ввода теряется) и D2 (сообщение старого города); с `patch/build_d18847f_r9_pointer_flush.patch` 36/36 на копии |

## Команды

```bash
git fetch origin claude/beautiful-clarke-sbzomj
export NODE_PATH="$(npm root -g)"
bash research/round-9-results/K07/scripts/run_r9_review.sh d18847f   # BUILD как есть + копия с patch/build_d18847f_*.patch
bash research/round-9-results/K07/scripts/run_r9_review.sh <NEW_SHA> # новый BUILD как есть — проверка интеграции
bash research/round-9-results/K07/scripts/run_r9_review.sh           # d865dd4 как есть + патчи K07 к d865dd4 (история этапов 1–2)
```

## Для BUILD

- Применить `patch/build_d18847f_r9_pointer_flush.patch` (`git apply -p1`, только `web/plan-ui.js` +7/−1). Он исправляет D1 и D2, тесты BUILD не ломаются.
- Независимые тесты для приёмки: `tests/k07r9_build_resilience_ui.cjs` (36), `tests/build_resilience_crosscheck.cjs` (69). Оба запускаются с `--app-root <копия prototypes/city-evidence>`.
- Патчи `build_d865dd4_*` не применять: интеграция BUILD их заменила, и в них осталась гонка D1.
