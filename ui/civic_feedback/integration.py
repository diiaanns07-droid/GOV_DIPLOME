"""Стыковка R06 с R02/R01: object_lookup поверх CivicService и порядок диспетчеризации.

R01 подключает так (ui/web_server.py, после сборки context HTTP-адаптером R02):

    from ui.civic_store import CivicService
    from ui.civic_feedback.integration import build_feedback_service, dispatch_civic

    civic = CivicService(db_path)
    feedback = build_feedback_service(db_path, civic)
    ...
    result = dispatch_civic(feedback, civic, method, path, query, body, context)
    if result is None: 404 JSON

Здесь нет HTTP-кода и общих файлов: только функции, которые R01 может вызвать.
"""

from __future__ import annotations

from .classifier_adapter import load_r08_classifier
from .service import FeedbackService

_MISSING_NAMES = {"NotFound", "BadRequest"}


def object_lookup_from_civic_service(civic):
    """Служебное чтение объекта R02 (включая draft/archived — их фильтрует R06).

    Возвращает civic-v1 item или None, если объекта нет или ID недопустим.
    Прочие ошибки (БД недоступна) пробрасываются: R06 ответит 503, а не «не найден».
    """
    try:  # точные классы R02, если модуль есть; иначе — по имени класса
        from ui.civic_store.objects import BadRequest, NotFound
        missing = (BadRequest, NotFound)
    except ImportError:  # pragma: no cover - вне интегрированной ветки
        missing = ()

    def lookup(object_id: str):
        try:
            result = civic.objects.get_staff(object_id)
        except Exception as exc:
            if isinstance(exc, missing) or type(exc).__name__ in _MISSING_NAMES:
                return None
            raise
        return result.get("item") if isinstance(result, dict) else None

    return lookup


def build_feedback_service(db_path, civic, *, classifier="auto", clock=None, **options) -> FeedbackService:
    """FeedbackService на той же SQLite-базе, что и R02 (свои таблицы feedback_*).

    classifier="auto" — подключить R08 (ml.civic_classifier.classify), если модуль есть;
    None — без классификатора; либо готовая функция classify(text, language).
    """
    if classifier == "auto":
        classifier = load_r08_classifier()
    return FeedbackService(db_path, object_lookup_from_civic_service(civic), clock or getattr(civic, "clock", None),
                           classifier=classifier, **options)


def dispatch_civic(feedback: FeedbackService, civic, method, path, query, body, context):
    """Эталонный порядок: сначала маршруты R06, затем R02.

    GET /objects/{id}/feedback принадлежит R06 и не должен попасть в GET /objects/{id}.
    (CivicService R02 сам возвращает None для трёхсегментного пути, так что обратный
    порядок тоже безопасен, но явный порядок защищает от будущих шаблонов маршрутов.)
    principal вычисляется только сервером R02 из cookie — никогда из тела запроса.
    """
    principal = civic.resolve_principal(context) if civic is not None else None
    result = feedback.handle(method, path, query, body, principal, context)
    if result is not None:
        return result
    return civic.handle(method, path, query, body, context) if civic is not None else None
