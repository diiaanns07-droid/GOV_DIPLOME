"""R15 раунд 15: тесты безопасности и приватности новых функций (R16, R17, R09, R13, R06, R03, R04 и шлюз R01).

Модель угроз — research/round-15-results/R15/THREATS_R15.md; ID угрозы (T-R16-05 …) — в имени или docstring теста.
Правила те же, что у тестов R15 раунда 14 (../conftest.py):
- нет модуля роли в проверяемой сборке — skip с причиной «NOT_RUN: …» (не FAIL);
- модуль есть, а маршрута ещё нет в шлюзе R01 — сервис проверяется напрямую (make_service(db).handle(...)),
  а HTTP-проверка — NOT_RUN;
- открытая находка — xfail(strict) с ID S42… из r15_common.FINDINGS; исправленная — обычный тест-регрессия.
Проверить ветку роли без сборки: R15_ROOT=<рабочая копия ветки> python3 -m pytest tests/civic/R15/round15 -q
"""

from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
for path in (HERE, HERE.parent):  # r15_round15 (здесь) и r15_common (тесты R15 раунда 14)
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))
