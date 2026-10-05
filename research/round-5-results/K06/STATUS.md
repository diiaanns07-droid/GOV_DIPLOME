# K06 round 5 — REVIEW: числа и подписи в демо

Роль: REVIEW, слот K06. Ветка: claude/ecstatic-curie-hzfzn0 (начало раунда от 33684f94607cb11faf25b408ac71289ded699629).
Задание: origin/codex/research-import-2026-10-05 @ 2883aeb, research/round-5/review/K06.txt.
Статус: partial — аудит, тесты и baseline готовы; браузерная проверка отрисованных подписей — следующий этап.

Входы:
- BUILD: claude/beautiful-clarke-sbzomj @ 0bf27deb8549b325b34a9610402613d745544edb, prototypes/city-evidence/
  (57 файлов, git blob id каждого пересчитан по записанным байтам).
- geo_oracle.py: собственный K06 раунд 4 @ 33684f94607cb11faf25b408ac71289ded699629 (sha256 94fa2654…).

Реально выполнено:
- python3 audit_numbers.py --app-root <baseline> → 12 PASS, 4 WARN, 0 FAIL (out/baseline_0bf27de.json).
- python3 test_audit_numbers.py --app-root <baseline> → 11 OK (включая режим --url на локальном HTTP-сервере).
- Исправлен собственный ложный FAIL N6 (округление координат в data.js до 1e-6°); после исправления — WARN по подписи.

Ограничения: аудит читает код и данные (web/*.js, index.html), а не отрисованную страницу; новая версия BUILD не проверялась;
исправления только предложены (README), ничего не FIXED.
Следующий шаг: Playwright-проверка отрисованных подписей (сводка среза, карточка дороги за краем, «расстояние от точки»).
