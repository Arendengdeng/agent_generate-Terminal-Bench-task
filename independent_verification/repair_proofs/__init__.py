"""Explicit, finite proof adapters; capability is never authorization to patch."""
import ast
from types import SimpleNamespace
from ..proof_errors import UnconfirmedAttribution
from . import literal_stdout, json_doubling

ADAPTERS = (literal_stdout, json_doubling)


def select_adapter(contract):
    return next((adapter for adapter in ADAPTERS if adapter.supported(contract)), None)


def repair_capability(contract, metadata=None, files=None):
    adapter = select_adapter(contract)
    eligible = adapter is not None
    if eligible and metadata is not None and files is not None:
        eligible = False
        candidate = SimpleNamespace(contract=contract)
        for path, source in files.items():
            if not path.startswith('test_') or not path.endswith('.py'):
                continue
            try:
                tree = ast.parse(source)
            except SyntaxError:
                continue
            for node in ast.walk(tree):
                if not isinstance(node, ast.Assert):
                    continue
                for req in contract['requirements']:
                    proposed = {'requirement_id': req['id'], 'contract_quote': req['description'],
                                'test_path': 'tests/' + path, 'line': str(node.lineno)}
                    try:
                        adapter.assertion(candidate, metadata, files, proposed)
                    except (UnconfirmedAttribution, ValueError, TypeError, KeyError, IndexError, SyntaxError):
                        continue
                    eligible = True
    return {'supported': eligible, 'rule': adapter.RULE if adapter else None,
            'reason': None if eligible else 'unsupported_proof_rule',
            'scope': 'contract_and_test_shape' if metadata is not None else 'contract',
            'limitation': 'Eligibility only; execution evidence and patch still require strict host verification.'}


def require_adapter(contract):
    adapter = select_adapter(contract)
    if adapter is None:
        raise UnconfirmedAttribution('unsupported_proof_rule')
    return adapter


def supported_diagnoses(candidate, tests_output, execution, config):
    adapter = require_adapter(candidate.contract)
    # Location discovery is an optional adapter capability, not a generic JSON rule.
    discover = getattr(adapter, 'supported_diagnoses', None)
    return discover(candidate, tests_output, execution, config) if discover else []
