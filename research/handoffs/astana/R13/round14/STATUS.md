# R13 · раунд 14 · handoff

Задача: R13 — прогноз проблемных кварталов (прототип), prompts/R13.txt.
Агент / город: Claude Code (облачная сессия), Астана, Birge.
Статус: partial (checkpoint 1)
Рабочая ветка: claude/r14-R13 (от claude/round-14-package @ 46f2308)
Назначенные пути: ml/civic_forecast/, ui/civic_forecast/, tests/civic/R13/, research/round-14-results/R13/, этот файл.

## Сделано
- [x] targets.py + data/targets.json: 2334 реальные территории OSM из данных R12 (claude/tender-brahmagupta-ef5ztl @ d13f49a).
- [x] weather.py: загрузчик LOCAL-9 (оба вида CSV Open-Meteo) + синтетическая фикстура data/weather_fixture.csv (пометка SYNTHETIC).
- [x] history.py: синтетическая история 2024-01…2026-10 (сезонность от погоды, горячие места, всплески, стройки), seed 2026.
- [ ] features.py, model.py, backtest.py, RESULTS.md
- [ ] ui/civic_forecast forecast(), причины ru/kk, тесты, DELIVERY/RUN/INTEGRATION

## Следующий шаг
features.py + model.py (HistGradientBoosting + запасная модель без зависимостей), затем backtest.
