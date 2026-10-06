"""Ошибки валидации сценарного движка R07 (civic-scenario-v1).

Каждая ошибка несёт машинный code, понятное сообщение и рекомендуемый HTTP-статус
для адаптера /api/civic/v1 (CONTRACT.txt, раздел 2: validation 400/422, stale 409, too large 413).
"""


class ScenarioError(Exception):
    HTTP = {
        "invalid_payload": 422,
        "invalid_graph": 422,
        "unknown_node": 422,
        "unknown_edge": 422,
        "city_mismatch": 422,
        "mode_mismatch": 422,
        "graph_mismatch": 422,
        "graph_digest_mismatch": 409,
        "unknown_graph": 404,
        "too_large": 413,
    }

    def __init__(self, code, message, fields=None):
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message
        self.fields = fields or {}

    @property
    def http_status(self):
        return self.HTTP.get(self.code, 422)

    def to_error(self):
        err = {"code": self.code, "message": self.message}
        if self.fields:
            err["fields"] = self.fields
        return err
