R17 · сверка табло на демо-мире R02 (сцена 8: «числа совпадают с «Обращениями»») · 15 окт ~22:00 по Астане

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
