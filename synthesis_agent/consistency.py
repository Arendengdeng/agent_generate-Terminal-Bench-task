"""Finite, offline checks for explicit instruction restrictions; not an NLP proof."""
import hashlib
import json
import re

MARKER = '## 完成标准（Contract 原文）'


def check_instruction(contract, instruction, *, rules=()):
    """Detect only supported explicit rules; no findings is not semantic approval."""
    findings = []
    body = instruction
    if MARKER in instruction:
        body, appendix = instruction.split(MARKER, 1)
        try:
            match = re.fullmatch(r'\s*```json\s*\n(.*?)\n```\s*', appendix, re.S)
            if match is None or json.loads(match[1]) != contract:
                raise ValueError('Contract appendix differs')
        except (ValueError, TypeError):
            findings.append({'code': 'CONTRACT_APPENDIX_MISMATCH', 'line': body.count('\n') + 1,
                             'instruction_quote': MARKER, 'contract_field': 'contract',
                             'contract_quote': 'The appended Contract must equal the immutable Contract.'})
    from .format_rules import RULE_NAMES, check_csv
    from .errors import SynthesisError
    if isinstance(rules, str) or not isinstance(rules, (tuple, list)) or any(not isinstance(r, str) or r not in RULE_NAMES for r in rules):
        raise SynthesisError('unknown consistency rule selection')
    if rules:
        findings.extend(check_csv(contract, body, rules))
    return {'status': 'blocked' if findings else 'no_findings', 'findings': findings,
            'contract_digest': hashlib.sha256(json.dumps(contract, sort_keys=True, ensure_ascii=False).encode()).hexdigest(),
            'instruction_digest': hashlib.sha256(instruction.encode()).hexdigest(),
            'enabled_rules': list(rules),
            'limitations': 'Appendix equality and explicitly selected finite rules only; ambiguous scopes are not proved.'}
