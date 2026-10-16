R17 · сверка табло на демо-мире R02 (сцена 8: «числа совпадают с «Обращениями»») · 15 окт ~21:50 по Астане

Сборка (облако, без интернета), CIVIC_DEMO=1 и CIVIC_DEMO_WORLD=1:
  ветка R01 @ c9069723 (B0.2: шлюз, seed_world всех модулей)
  + R09 @ dfaee97e (ui/civic_feedback, web/civic/feedback — жалоба v2.1, части служб, передачи, seed_world)
  + R02 @ ac75f3a8 (data/civic/astana/demo-world/*, ml/datasets/demo_world_*.py)
  + R16 @ fbd9e247 (ui/civic_together), R10 @ c7f64223 (tests/civic/R10)
  + R17 — код checkpoint 8 (ui/civic_agencies, web/civic/agencies).
  Журнал засева: «civic-world: R09 743, R16 42, R17 3, R13 24, R12 39».
Инструмент R10: python3 tests/civic/R10/consistency.py --root <сборка> --out <папка> → CONSISTENCY.md / .json (здесь).

Итог для R17:
  C1 PASS  «Просрочено» (срок исправления): «Картина дня» R08 = табло R17 overdue_fix — 5 = 5 (Нура)
  C2 PASS  «Просрочено» (срок ответа): «Обращения» R09 = табло R17 overdue — 2 = 2
  D  PASS  открытые у каждой службы: табло R17 = «Обращения» R09 — все 10 служб с открытыми (у совместных — части)
  C4 FAIL  ложный для R17: проверка читает подпись табло по ключу agencies.kpi.overdue (в словаре R11 «просрочено»),
           а экран R17 показывает agencies.kpi.overdue_answer («ответ просрочен») и agencies.kpi.overdue_fix
           («не исправлено в срок»). Просьба R10: читать ["agencies.kpi.overdue_answer", "agencies.kpi.overdue"] —
           как ["inbox.tab.overdue_answer", "inbox.tab.overdue"] у R09. R17 к тому же сменил текст старого ключа
           agencies.kpi.overdue на «ответ просрочен» / «жауап мерзімі өтті» (R11 подтянет при синхронизации).
  C5 FAIL  не R17 («Картина дня» и «Картина недели» R08 — два окна «за неделю», R10 B-122).
Город (табло без района): открыто 132, ответ просрочен 5, не исправлено в срок 35 (= Ситуационный центр R08 35),
совместных 18. Кадры: screens/world-*.png (1366 ru/kk, 375 kk; «Совместные», «Передачи», кризис «Буран в Нуре»).

Повтор 16 окт ~05:30 по Астане — на сборке R01 B0.14 (aebb9f0a: мир R02, R09, R16, R10 eb0876cf, R11 4b8f0d62) с кодом
R17 D12 + checkpoint 18 (CSS вкладок), CIVIC_DEMO=1, CIVIC_DEMO_WORLD=1 — CONSISTENCY_B014.md / .json:
  PASS 16 · FAIL 0 · NOT_RUN 0. Для R17: C1 «Картина дня» R08 = табло overdue_fix 5 = 5; C2 «Обращения» R09 = табло
  overdue 2 = 2; C4 подписи разные («Не исправлено в срок» / «Ответ просрочен», ru и kk); D открытые у каждой службы
  (10 служб) = «Обращения»; C3 город 35 = 35. Прежние C4 и C5 FAIL (ключ подписи у R10, окно недели у R08) закрыты соседями.
  Кадры screens/world-*.png пересняты на этой же сборке B0.14 (табло, «Совместные», «Передачи», «Буран в Нуре»).

Повтор 16 окт ~08:40 по Астане — на сборке R01 B0.17 (9f44429e) с кодом R17 D15 (двор жителя у R16), тот же мир:
  CONSISTENCY_B017.md / .json — PASS 16 · FAIL 0 · NOT_RUN 0 (C1 5 = 5, C2 2 = 2, C4, D по 10 службам, C3 35 = 35).
  Там же: браузер R17 206/206; житель двора в Нуре («Я живу здесь» R16) — incidents/updates 3, лента R06 3, баннер
  1366 ru / 375 kk; двор в Есиле — 0 (checks/e2e_yard_feed.py, checks/e2e_yard_banner.cjs).
