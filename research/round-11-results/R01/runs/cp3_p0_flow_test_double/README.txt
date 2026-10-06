Прогон tests/civic/R01/browser/p0_flow.cjs --backend=double (2026-10-06 ~15:58Z).
Backend: ТЕСТОВЫЙ ДУБЛЁР tests/civic/R01/contract_double.py (в памяти, НЕ R02/R06, не рабочий backend).
UI: оболочка R01 + резервные модули R01 (R03/R04/R06 ещё не импортированы).
Код: рабочее дерево поверх 341c554 (+ правки CSS/fallback этого checkpoint).
Итог: 37 PASS / 0 FAIL / 2 NOT_RUN (подложка OpenFreeMap и attribution — хост недоступен).
Скриншоты — реальные кадры страницы в Chromium (swiftshader), офлайн-фон без улиц.
Проверка restart здесь невозможна по определению (данные в памяти) — будет на SQLite R02.
