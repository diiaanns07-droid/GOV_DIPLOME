"""R06: сообщения жителей и очередь модерации (civic-v1)."""

from .service import (API_PREFIX, CATEGORIES, CATEGORY_LABELS, MODERATION_LABELS,
                      PUBLIC_NOTICE, RECEIPT_NOTICE, FeedbackService)

__all__ = ["API_PREFIX", "CATEGORIES", "CATEGORY_LABELS", "MODERATION_LABELS",
           "PUBLIC_NOTICE", "RECEIPT_NOTICE", "FeedbackService"]
