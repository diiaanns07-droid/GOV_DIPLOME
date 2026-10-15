# R07 · раунд 15 · STATUS

Роль: R07
Ветка роли: claude/birge-r07-round-15-zjp4ob (push в claude/r15-R07 средой запрещён — работаю в ветке сессии)
Начато: 2026-10-15 16:25 Астана (11:25 UTC)
База: origin/claude/clever-hypatia-q6ts4g @ e91acb69 (FINAL-4 a4937462 + пакет раунда 15)
restored_from: fe209c56 (claude/r14-R07, круги 5–6): web/civic/heat/heat.css, heat.js, ui/civic_heat/devserver.py,
  tests/civic/R07/test_r07_devserver.py. Тесты r13 и новый test_r07_http_ui.py из FINAL-4 оставлены как есть.
Продолжение: scheduled task trig_01BezaALZvqcGSXFgjjsxQpg (раз в час, :25) — удалить после 17 окт 23:59 Астаны.

## План (prompts/R07.txt, по порядку)
1. [в работе] Один источник: CIVIC_DEMO=1 + CIVIC_DEMO_WORLD=1 → карта только из базы R09 (world.py, demo_seed → []).
2. [в работе] GET heat/replay — кадры по дням той же формулой (replay.py), компактно, кэш, отметки (marks.py: R17 + мир).
3. web/civic/replay/ — «Хроника» (BirgeReplay.mount): 7/30, ▶/❚❚, скорость, дата, шкала с «Буран», клавиши, reduced-motion.
4. Красота карты: кластеры с числом, мягкое появление, фокус, легенда = heat_states, FPS при 1 000 целей.
5. Значки поверх слоёв R16/R17/R12 — проверка, замечания соседям.
6. Тесты, кадры 1366/375 × ru/kk, DELIVERY/RUN/INTEGRATION.

## Сделано
- 11:25 UTC роль занята. Восстановлены пути из fe209c56 (см. restored_from).
- ui/civic_heat/world.py — world_mode(), seed_world(db_path, world, now) (отметки шкалы в своей таблице
  heat_replay_marks_v1), stored_marks(); demo_seed.demo_records() → [] в демо-мире.
- ui/civic_heat/replay.py — as_of (жалоба «как была» в момент t) + тот же HeatService._compute на каждый день;
  первый кадр полный, дальше changed/removed; кэш прошлых дней. Демо R07: 30 дней — 0,22 с, 7 дней (кэш) — 0,01 с;
  последний кадр (format=full) == /heat.
- ui/civic_heat/marks.py — отметки из R17 (list_incidents / make_service GET incidents) и своих (мир).
- api.py: GET /api/civic/v2/heat/replay; meta.replay/meta.world.
- pytest tests/civic/R07: 177 passed (до новых тестов).

## Дальше
- Тесты replay/world (паритет с /heat, пустой период, одна цель, R09-источник = «Обращения»).
- Фронтенд web/civic/replay/.

## Соседи (15 окт 11:50 UTC)
- R02 (claude/affectionate-shannon-jm6ws5): только STATUS; образец мира обещан к 18:30 Астаны — жду SCHEMA.md.
- R17: ветки нет — работаю на фикстуре §5.5. R09: ветки нет. R01 (claude/brave-fermi-nhzetj): только STATUS.
- R11 (claude/gracious-mendel-eopem6): только STATUS — IA_ROUND15 ещё нет.

## Вопросы владельцу
- (пока нет)
