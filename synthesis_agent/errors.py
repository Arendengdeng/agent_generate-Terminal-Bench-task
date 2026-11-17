class SynthesisError(Exception):
    """A reported input, generation, or infrastructure failure."""


class BudgetExceeded(SynthesisError):
    """A resource limit, with a stable machine-readable reason."""

    def __init__(self, message, *, code='budget_exhausted'):
        super().__init__(message)
        self.code = code

    def report(self):
        return {'type': type(self).__name__, 'message': str(self), 'code': self.code}


class SandboxError(SynthesisError):
    pass
