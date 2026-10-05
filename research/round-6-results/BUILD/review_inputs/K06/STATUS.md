# K06 round 5 — REVIEW: числа и подписи в демо

Роль: REVIEW, слот K06. Ветка: claude/ecstatic-curie-hzfzn0 (начало раунда от 33684f94607cb11faf25b408ac71289ded699629;
этап 1 запушен как 380f16acf95da23ac78c1f034b2a03d46829951d).
Задание: origin/codex/research-import-2026-10-05 @ 2883aeb, research/round-5/review/K06.txt.
Статус: done в объёме задания (аудит + тесты + проверка отрисованной страницы на baseline). Исправления только предложены.

Входы:
- BUILD: claude/beautiful-clarke-sbzomj @ 0bf27deb8549b325b34a9610402613d745544edb, prototypes/city-evidence/
  (57 файлов; git blob id каждого пересчитан по записанным байтам).
- geo_oracle.py: K06 раунд 4 @ 33684f94607cb11faf25b408ac71289ded699629 (sha256 94fa2654…).

Реально выполнено (Python 3.11.15, Node 22, Playwright 1.56 Chromium):
- audit_numbers.py --app-root → 12 PASS, 4 WARN, 0 FAIL; --url (локальный serve.py) → 10 PASS, 4 WARN, 2 SKIP (N8 без inputs).
- test_audit_numbers.py --app-root → 11 OK (8 внедрённых дефектов дают FAIL, честная подпись PASS, режим --url).
- rendered_check.py --app-root (file://) → 12 PASS; --url → 12 PASS; мутант (убрана пометка края, «в срезе»→«в городе») → 4 FAIL.

Находки (baseline 0bf27de):
- WARN N5: road_km_full_geometry (125,54 / 156,18 км) включает 17,07 / 15,77 км за краем; в UI не показан — скрытый риск.
- WARN N6: длина подписана «геодезическая, K10», K10 считает по сфере; числа в допуске.
- Карточка дороги за краем показывает всю линию (2,83 км при 308 м внутри); пометка есть, длины внутри нет — предложение.
- Количества, null вместо 0, расстояния по прямой и отсутствие минут — PASS по коду и по отрисованному тексту.

Ограничения: проверен только baseline; новая версия BUILD не проверялась. Windows не проверялся.
Следующий шаг: сборщику при новой версии — extract_build.py <dir> <SHA>, затем audit_numbers.py / test_audit_numbers.py /
rendered_check.py с --app-root <dir>; WARN N5/N6 закрываются подписью, а не изменением чисел.
