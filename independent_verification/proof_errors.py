"""Shared fail-closed repair proof errors (independent of adapter dispatch)."""
from synthesis_agent.errors import SynthesisError


class UnconfirmedAttribution(SynthesisError):
    pass
