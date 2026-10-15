# R07 · раунд 15 · STATUS

Роль: R07
Ветка роли: claude/birge-r07-round-15-zjp4ob (push в claude/r15-R07 средой запрещён — работаю в ветке сессии)
Начато: 2026-10-15 16:25 Астана (11:25 UTC)
База: origin/claude/clever-hypatia-q6ts4g @ e91acb69 (FINAL-4 a4937462 + пакет раунда 15)
restored_from: fe209c56 (claude/r14-R07, круги 5–6): web/civic/heat/heat.css, heat.js, ui/civic_heat/devserver.py,
  tests/civic/R07/test_r07_devserver.py. Тесты r13 и новый test_r07_http_ui.py из FINAL-4 оставлены как есть.
Продолжение: scheduled task trig_01BezaALZvqcGSXFgjjsxQpg (раз в час, :25) — удалить после 17 окт 23:59 Астаны.

**Каждый круг: сначала читать AMENDMENTS.md из ветки пакета**
(`git fetch origin claude/clever-hypatia-q6ts4g && git show origin/claude/clever-hypatia-q6ts4g:research/round-15/AMENDMENTS.md`).
Прочитано: П1 (15 окт 17:05, «Без ИИ-слопа») — применено к R07, см. «Сделано».

## План (prompts/R07.txt, по порядку)
1. [готово] Один источник: CIVIC_DEMO=1 + CIVIC_DEMO_WORLD=1 → карта только из базы R09 (world.py, demo_seed → []).
2. [готово] GET heat/replay — кадры по дням той же формулой (replay.py), компактно, кэш, отметки (marks.py: R17 + мир).
3. [в работе] web/civic/replay/ — «Хроника» (BirgeReplay.mount): 7/30, ▶/❚❚, скорость, дата, шкала с «Буран», клавиши, reduced-motion.
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

- (12:00 UTC) tests/civic/R07/test_r07_replay.py — 23 теста: последний кадр = /heat (демо и мир, 7/30 дней), прошлый
  кадр = /heat в конце того дня, компактные кадры = полные, as_of (статус, «Я тоже», раунды ремонта), одна цель
  (красная → зелёная 7 дней → ушла), пустой период, буран (Нура краснеет и остывает), отметка «Буран» из мира и id сцены 9,
  засев идемпотентен, R17 главнее копии мира, падение R17 не ломает хронику, демо-мир: числа у цели и по районам =
  «Обращения» R09, шлюз R01 в демо-мире без примеров R07, ошибки параметров 400, город за 30 дней < 1 с.
- ui/civic_heat/world_fixture.py — мини-мир R07 (буран в Нуре 6–3 дня назад) и city_world (1 000 целей для замера);
  стенд `python -m ui.civic_heat.devserver --world` / `--world city1000`.
- web/civic/heat/heat.js: replay.begin/frame/end — хроника рисует теми же значками и слоями: цвет и вес (ореол, толщина
  участка) перетекают через feature-state, числа на значках считают, ушедшие цели гаснут, панель — горячие места дня;
  закрытие возвращает «сегодня» тем же перетеканием (проверено: значки не пропадают ни на кадр). CivicHeat.current.
- web/civic/replay/replay.js + replay.css — «Хроника города»: дата крупно, «Сообщили N · M мест исправлено», шкала с
  графиком жалоб по дням и полосой «Буран», 7/30 дней, ▶/❚❚, 1×/2×, ×; Пробел, ← →, Home/End, Esc; reduced-motion —
  шагами; 375 — упрощённо (неделя). BirgeReplay.open / attach (кнопка у кнопок карты, ?replay=7|30, birge:replay-open).
- Скорость значков (1 000 целей): смена дня 410 → ~50 мс в облаке (замеры пачкой, размер по виду значка, скрытые
  дорисовываются при показе, запись атрибутов только при изменении); код перетекания ~1 мс на кадр.
  FPS в облаке упирается в программный WebGL: сама карта при easeTo — 11–12 к/с; хроника районов — 42 к/с,
  мест (981 цель) — 11 к/с. Настоящий замер 60 к/с — LOCAL (ноутбук), скрипт в RUN.txt.
- П1 «Без ИИ-слопа»: пустое состояние и ошибка карты — значок R11 ≤ 48 px + текст + одна кнопка (было: рисунок 96×80 и
  две кнопки); иконки хроники — из спрайта ui-kit, где он есть; без эмодзи и декоративных градиентов.
- Регресс: волна 2 в браузере 38/38 (стенд R07), pytest tests/civic/R07 200/0, R01 198/0, R08 263/0.

## Дальше
- Браузерный тест хроники tests/civic/R07/browser/replay.cjs (открыть, клавиши, неделя 10–20 с, Esc без мигания,
  ошибка/503/пусто, reduced-motion, 375/1366 × ru/kk) + кадры для R14/R10 (начало, буран, после).
- Ctrl+K «Хроника города» в commands(); кнопка в колонке кнопок карты — патч R01 в INTEGRATION.
- Задача 4 (кластеры, появление, фокус, легенда) и 5 (слои соседей), DELIVERY/RUN/INTEGRATION.

## Соседи (15 окт 11:50 UTC — проверить заново на следующем круге)
- R02 (claude/affectionate-shannon-jm6ws5): только STATUS; образец мира обещан к 18:30 Астаны — жду SCHEMA.md.
- R17: ветки нет — работаю на фикстуре §5.5. R09: ветки нет. R01 (claude/brave-fermi-nhzetj): только STATUS.
- R11 (claude/gracious-mendel-eopem6): только STATUS — IA_ROUND15 ещё нет.

## Вопросы владельцу
- (пока нет)
