class OperationError(Exception):
    def __init__(self, code: str, message_tr: str, status: int = 409, retryable: bool = False):
        super().__init__(code)
        self.code = code
        self.message_tr = message_tr
        self.status = status
        self.retryable = retryable


class EvaluationError(Exception):
    def __init__(self, code: str = "PROVIDER_FAILURE", retryable: bool = True, status: int = 502):
        super().__init__(code)
        self.code = code
        self.retryable = retryable
        self.status = status
