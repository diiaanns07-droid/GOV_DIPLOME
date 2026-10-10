"""R15 (раунд 14): тесты ревью безопасности.

Тесты проверяют ту сборку, в которой лежат (обычно — сборку R01). Чтобы проверить другую рабочую
копию (ветку роли), не копируя тесты, задайте её путь:

    R15_ROOT=/путь/к/рабочей/копии python -m pytest tests/civic/R15 -q

Правила:
- находка, которая ещё не исправлена, помечена xfail(strict=True) с ID из SECURITY_REVIEW.md;
  когда владелец исправит — тест станет XPASS и упадёт: это сигнал снять пометку и обновить статус;
- нет модуля роли в этой сборке — тест пропускается (skip) с именем модуля, а не падает;
- всё только локально: временная SQLite в tmp_path, сервер на 127.0.0.1 со случайным портом.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

R15_ROOT = Path(os.environ.get("R15_ROOT") or Path(__file__).resolve().parents[3]).resolve()
if str(R15_ROOT) not in sys.path:
    sys.path.insert(0, str(R15_ROOT))
