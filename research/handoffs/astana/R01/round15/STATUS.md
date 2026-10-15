# R01 · раунд 15 · STATUS

Роль: R01 (интегратор и оболочка)
Ветка роли: claude/brave-fermi-nhzetj
Начато: 2026-10-15 16:22 по Астане (11:22 UTC)
База: origin/claude/clever-hypatia-q6ts4g @ e91acb69 (код FINAL-4 a4937462 + пакет раунда 15)
Push в claude/r15-R01 средой не предусмотрен — работаю в ветке сессии, find_branches.py находит её по этому файлу.
Продолжение: часовой триггер этой сессии `trig_01QbRVYt7xvyTzaxvwGwMEBw` (каждый час в :24 UTC) — «Продолжи роль R01 по
своему STATUS.md и research/round-15/prompts/R01.txt». **Удалить после 17 окт 23:59 по Астане (18:59 UTC).**

## Каждый круг: сначала читать AMENDMENTS.md из ветки пакета
```
git fetch origin claude/clever-hypatia-q6ts4g
git show origin/claude/clever-hypatia-q6ts4g:research/round-15/AMENDMENTS.md
```
Где поправка расходится с промптом R01, COMMON, IDEA или VISUAL_BRIEF — права поправка. Прочитанные поправки: **П1**
(15 окт 17:05, «Без ИИ-слопа») — применена 15 окт 17:18, см. ниже.

### П1 «Без ИИ-слопа» — что это значит для R01
- В B1 / B2 / FINAL-5 **не брать модели ориентиров** (процедурные Байтерек, Хан Шатыр, Ак Орда, «Нур Алем», Дворец
  мира и согласия, ЭКСПО), даже если они есть в ветке R05 или другой роли. При сборке R05 — брать пути выборочно и
  проверять, что в `web/civic/build3d/` нет моделей ориентиров (`git grep -i "baiterek\|khan.shatyr\|nur.alem\|akorda"`).
- Правила П1 1–7 — часть приёмки каждой сборки: перед BUILD.json просмотреть кадры 1366/1024/375 × ru/kk каждого
  нового экрана; нарушение (нарисованное здание/логотип, большая иллюстрация, эмодзи, свечение/градиент «для красоты»,
  украшение пустой карты) — не брать в сборку или записать роли с точным местом.
- Патч R05 для `web/civic/shell/basemap-style.js` (ориентир — «белый макет», тон чуть светлее соседей + подпись, без
  отдельной краски) — применить, когда придёт в INTEGRATION R05. Сейчас 3D-здания подложки уже светло-серые
  (#ECE9E2 → #D2CDC4), ориентиры — #E6DCC8.
- Оболочка: пустые состояния «Картины дня» и экранов разделов — маленькая монохромная иконка набора R11 (40 px,
  `i-clock` / `i-wifi-off`) + текст + одна кнопка вместо больших линейных иллюстраций `ill-*` (сделано 17:18).

## Последняя сборка

**FINAL-4.1 = `bd3800d8`** (15 окт, 17:12 по Астане) — `research/round-15-results/R01/BUILD.json`.
R07 fe209c56 + патч оболочки R07, R09 D0 e494026e, дефекты оболочки VISUAL_BRIEF §3. Журнал — BUILD_LOG.md.

## Сделано
- 16:24 роль занята, триггер продолжения поставлен.
- 16:49 FINAL-4.1 шаг 1 (`0b76f9ed`): R07 fe209c56 + патч оболочки; «Ещё» под кнопкой; один знак Birge; телефон — поиск
  во всю ширину; 1024 — поля 12; одна шторка на телефоне; аватар — круг фоном (точка ui-kit видна).
- 17:08 FINAL-4.1 шаг 2 (`bd3800d8`): R09 D0 e494026e. **FINAL-4.1 = bd3800d8** (BUILD.json).
- 17:17 `d987a112`: маршруты раунда 15 (все строки CONTRACT §7, вход сотрудника → форма параметров → модуль, лимиты),
  демо-мир (CIVIC_DEMO_WORLD=1, seed_world всех модулей, строка civic-world, без синтетики R07), GET /demo/scenes,
  оболочка по IA_ROUND15 R11 (слоты, «Ещё» группами ≤ 7, PARENT, #раздел/путь, opts.map/path/navigate/setLayer,
  alertSlot, Esc → карта, CSRF и в GET), режим показа ?show=1, сцены 7–9 в Ctrl+K.
- 17:18 поправка П1 (`4dd0c8e6`): пустые состояния оболочки — маленькая иконка 40 px вместо иллюстраций; правило чтения
  AMENDMENTS.md; приёмка сборок без моделей ориентиров.
- 17:25 `c2df555a`: браузерная проверка меню раунда 15 — r15_ia.cjs 25/0 (новый, в run_checks), r14_wave2 42/0
  (?screens=r14 — регресс меню FINAL-4). DELIVERY / RUN / INTEGRATION раунда 15 — `2bd5bb5e`.

## Дальше (по порядку промпта)
1. Колокольчик R06 (BirgeNotify.attach) и чип «▶ Хроника» R07 (BirgeReplay.mount) — по их INTEGRATION, когда придут.
2. DEMO_SCRIPT.md v2 (шаги 1–9, ҚАЗ и РУС, «Перед показом») — черновик до B1, уточнить по сценам R10/R14.
3. B1 — 16 окт 14:00 по Астане (09:00 UTC): поставки ролей по find_branches.py (DELIVERY code_sha), только пути ролей,
   CIVIC_ASSETS и теги, run_checks + r15_ia + R10 demo_flow часть 1, проверка П1 по кадрам, BUILD.json.
4. Флаг демо-мира в run-city.bat / run.sh — после seed_world модулей и зелёного регресса R10.

## Роли → ветки → поставки (для истории)
| Роль | Ветка раунда 15 | Поставка (DELIVERY code_sha) | Взято в сборку |
|---|---|---|---|
| R02 | claude/affectionate-shannon-jm6ws5 | 907bfc9d (демо-мир world_v1) | B0: 907bfc9d |
| R03 | claude/modest-mccarthy-lrl98u | 7724787e («Спросить Birge») | B0: 7724787e + патчи ассетов и палитры |
| R04 | claude/gifted-maxwell-i66wwi | c5383235 (route, reply-draft, moderate) | B0: c5383235 |
| R05 | claude/bold-cray-dopshy | — (П1: модели ориентиров отменены) | — |
| R06 | claude/eloquent-einstein-wvuyje | — | — |
| R07 | claude/birge-r07-round-15-zjp4ob | (раунд 14: fe209c56) | FINAL-4.1: fe209c56 |
| R08 | **claude/laughing-euler-iv3on3** (первая заявка) · вторая сессия claude/inspiring-johnson-j7wksj | 6cd8f2be | B0: 6cd8f2be (из первой ветки целиком) |
| R09 | claude/quirky-ptolemy-k3z2mj | D0 e494026e | FINAL-4.1: e494026e |
| R10 | claude/zen-wozniak-69d41q | 95de8b99 (тесты) | B0: 95de8b99 |
| R11 | claude/gracious-mendel-eopem6 | b6ced41d (ui-kit r15, IA, ключи) | B0: b6ced41d |
| R12 | claude/great-newton-8k3474 | 1c8d171d (календарь работ) | B0: 1c8d171d |
| R13 | claude/gifted-mayer-p86myv | 74903b7a (встречи, прогноз недели) | B0: 74903b7a |
| R14 | (не начата на 18:40) | — | — |
| R15 | claude/practical-fermi-c58v1u | тесты — голова ветки | B0: 4995f2bf (tests/civic/R15) |
| R16 | claude/youthful-johnson-6nz5mp | — | — |
| R17 | claude/sweet-euler-5tiu5b | 75300896 (штаб ведомств) | B0: 75300896 |

## Просьбы соседям
- **R08 (вторая сессия claude/inspiring-johnson-j7wksj)**: роль R08 по COMMON ведёт claude/laughing-euler-iv3on3 (заявка на
  7 с раньше, см. её STATUS). R01 берёт R08 только из неё. Свои находки — патчем в её INTEGRATION или строкой в её STATUS.
- **R08**: tests/civic/R08/test_r08_board.py::test_forecast_week_preferred_month_fallback в сборке B0 падает: тест ждёт, что
  у R13 нет прогноза на неделю (FINAL-4), а в B0 у R13 есть week_block — R08 верно показывает r13-week. Сделайте первую
  часть теста независимой от R13 (подмена ui.civic_forecast без недельной функции).
- **R15**: S42 исправлен полностью (R01 28893ffc: любой raw-маршрут с staff=True проверяет шлюз) —
  test_gateway_enforces_staff_on_raw_routes теперь XPASS(strict); снимите xfail.
- **R10 / R12 / R07**: pytest пакета e91acb69 — 2 FAIL `tests/civic/R10/test_r10_accuracy.py` [c24-R12], [c28-R07]
  «объекты = точки OSM» (сдвиг 2–18 м). Причина — новые файлы LOCAL-10 пакета
  `data/civic/astana/osm-objects/raw/crossings.json.gz`, `traffic_signals.json.gz` (другой снимок OSM, чем у объектов
  R12/R07). Нужна сверка с одним снимком или правка проверки R10. Код оболочки ни при чём.
- **R15**: POST /moderate (R04, предпросмотр для всех) в таблице — ключ `ml.text_check` (не «moderate»: это не решение
  сотрудника, ничего не меняет); лимит 60/мин по адресу.

## Вопросы владельцу
- (решено по умолчанию) Телефон: «ҚАЗ · РУС» — в шторке «Рядом с вами» (эталон), а когда шторки нет (акимат, карточка,
  мастер жалобы) — в поле поиска рядом с аватаром.
