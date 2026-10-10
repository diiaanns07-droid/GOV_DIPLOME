"""Ошибки ML-API в форме, которую понимает шлюз R01 (ui/web_server.py, INTEGRATION R01 §1).

ValueError -> 400; исключение с атрибутами status/code/message -> этот код.
"""


class MLServiceUnavailable(RuntimeError):
    """503: часть сервиса не подключена (например, /similar без хранилища жалоб R09)."""

    status = 503

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message
