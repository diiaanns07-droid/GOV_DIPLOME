# R12 · раунд 15 · STATUS

Роль: R12
Ветка роли: claude/great-newton-8k3474
Начато: 2026-10-15 16:25 по Астане (UTC+5), 11:25 UTC
Основа: origin/claude/clever-hypatia-q6ts4g @ e91acb69 (FINAL-4 a4937462 + пакет round-15)
Прошлая передача: claude/tender-brahmagupta-ef5ztl (раунд 14; в FINAL-4 — 016c93b5)
Режим: автопилот до 17 окт 2026 23:59 (Астана). Push в claude/r15-R12 средой не разрешён — работаю в ветке сессии.

## План (prompts/R12.txt, по порядку)
1. engine/civic_geo/works.py — привязка работ к рёбрам графа OSM, конфликты dig_after_surface / same_segment_overlap /
   parallel_closures, советы ru/kk, детерминированно.
2. Маршруты GET works-calendar и GET works-conflicts (raw, strip_prefix); записи — функцией R06, пока нет — фикстура §5.6.
3. web/civic/works-calendar/ — «Календарь работ» (BirgeWorksCalendar.mount), слой «Конфликты работ» (registerLayer, выкл.).
4. Редактор: служба и вид работы при создании.
5. Реальные работы nura-real/records.csv (LOCAL-5) — если есть; нет — NOT_RUN.
6. Тесты: ≤ 5 м от формы ребра, три вида конфликтов, пустой период, регресс QR и целей; < 300 мс на 60 работ.

## Сделано
- (старт) роль занята, база перенесена на ветку пакета. Пути R12 в пакете = поставка раунда 14 016c93b5 (восстанавливать нечего).
- Продолжение: scheduled task trig_01V2KWEBnxYDj6ipNAbV6TLJ — раз в час в эту сессию (удалить после 17 окт 23:59 Астаны = 18:59 UTC).
- Чекпойнт 1 (11:45 UTC): engine/civic_geo/works.py — привязка работ к рёбрам OSM (segments / улица + 2 точки / линия
  редактора / точка = «примерное место»), конфликты dig_after_surface (18 мес.), same_segment_overlap, parallel_closures
  (≤ 400 м по графу, ≤ 30°, бок о бок ≥ 50 м, поперёк ≥ 25 м), советы ru/kk без денег, id = хэш (детерминированно).
  works_calendar.py — источники (R06 → демо-мир R02 → фикстура R12 в демо), строки по улицам, фильтры, ответы маршрутов.
  api.handle(path, query, staff=None): /works-calendar, /works-conflicts — только staff=True (иначе 401).
  Фикстура data/civic/astana/geo/works_fixture.json — 15 синтетических работ на настоящих улицах Нуры, 5 конфликтов
  (сцена 8: ул. Сыганак, асфальт 4–20 мая → водопровод с 20 июля, «через 2 месяца»).
  tests/civic/R12/test_works.py 35/0; весь tests/civic/R12 83/0. 60 работ: 43 мс (9 мс из кэша).

## Дальше
- Экран web/civic/works-calendar/ (BirgeWorksCalendar.mount) + слой «Конфликты работ» (registerLayer, выкл.).
- INTEGRATION для R01 (маршруты staff_view=True, CIVIC_ASSETS, registerScreen) и R06 (функция works_v2), ключи R11.

## Вопросы владельцу
- (пока нет)

## SHA
- старт: e91acb69 (основа)
