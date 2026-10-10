"""R02 civic_store: серверное хранение объектов civic-v1, публикация и доступ редактора.

Публичный экспорт по CONTRACT.txt раунда 11:
    CivicService(db_path, clock=None)
        .handle(method, path, query, body, context) -> None | {status, headers, body}
        .resolve_principal(context) -> Principal | None
        .require_staff(context, unsafe=bool) -> (Principal, None) | (None, ответ-ошибка)
    CivicHttpAdapter(service, extra_handlers=(), bind_host="127.0.0.1") — для ui/web_server.Handler.
Подробно: research/round-11-results/R02/INTEGRATION.txt.
"""

from .auth import Principal
from .db import DEFAULT_DB_PATH, SCHEMA_VERSION, Database, StorageError
from .http_adapter import CivicHttpAdapter
from .service import PREFIX, CivicService
from .v2 import PREFIX_V2, CivicV2

__all__ = ["CivicHttpAdapter", "CivicService", "CivicV2", "PREFIX_V2", "DEFAULT_DB_PATH", "Database", "PREFIX", "Principal",
           "SCHEMA_VERSION", "StorageError"]
