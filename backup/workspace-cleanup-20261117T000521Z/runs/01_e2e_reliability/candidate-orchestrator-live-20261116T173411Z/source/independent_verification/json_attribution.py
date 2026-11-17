"""Compatibility exports for the isolated finite JSON proof adapter."""
from .repair_proofs.json_doubling import (INPUT, OUTPUT, REQUIREMENT, assertion,
                                        diagnosis, patch, supported_diagnoses)
from .repair_proofs.json_doubling import supported as _supported


def supported(candidate):
    return _supported(candidate.contract)
