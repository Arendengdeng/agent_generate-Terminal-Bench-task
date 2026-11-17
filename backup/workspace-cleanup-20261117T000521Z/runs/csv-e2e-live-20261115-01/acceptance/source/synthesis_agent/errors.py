class SynthesisError(Exception):
    """A reported input, generation, or infrastructure failure."""


class BudgetExceeded(SynthesisError):
    pass


class SandboxError(SynthesisError):
    pass
