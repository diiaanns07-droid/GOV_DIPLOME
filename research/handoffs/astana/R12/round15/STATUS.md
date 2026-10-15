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
- (старт) роль занята, база перенесена на ветку пакета.

## Дальше
- Читаю IDEA / CONTRACT (§5.6, §7, §8) / VISUAL_BRIEF / UX_BRIEF раунда 14, свою передачу раунда 14.

## Вопросы владельцу
- (пока нет)

## SHA
- старт: e91acb69 (основа)
