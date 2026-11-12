class AppError(Exception):
    def __init__(self, code: str, message: str, status: int = 422, *, retryable: bool | None = None,
                 provider_status: int | None = None, agent: str | None = None):
        super().__init__(message)
        self.code, self.message, self.status = code, message, status
        self.retryable, self.provider_status, self.agent = retryable, provider_status, agent

    def details(self) -> dict:
        fields = {'code': self.code, 'message': self.message, 'retryable': self.retryable,
                  'providerStatus': self.provider_status, 'agent': self.agent}
        return {key: value for key, value in fields.items() if value is not None}

    def payload(self) -> dict:
        return {'error': self.details()}
