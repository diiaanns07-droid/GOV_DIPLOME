"""R13 · «Вопрос акиму» (раунд 14, волна 2 п. 9): вопросы жителей, модерация, голоса, ответы акима.

    from ui.civic_qa import make_service
    service = make_service(".runtime/civic.sqlite3")          # та же база, что у шлюза R01 (таблицы qa_*)
    service.handle("GET", "/api/civic/v2/questions", "tab=top", None, principal=None, context={...})
      -> {"status": 200, "headers": {}, "body": {"items": [...], "counts": {...}, ...}}

Подключение к шлюзу R01 (V2Handler kind="service"), маршруты и лимиты — research/round-14-results/R13/INTEGRATION.txt §8.
Экран — web/civic/qa/qa.js (window.BirgeAsk, раздел оболочки #questions).
"""

from .service import QuestionService, make_service
from .store import QuestionStore

__all__ = ["QuestionService", "QuestionStore", "make_service"]
