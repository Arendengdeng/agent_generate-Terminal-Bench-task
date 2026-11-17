"""Finite, offline checks for explicit instruction restrictions; not an NLP proof."""
import hashlib
import json
import re

MARKER = '## 完成标准（Contract 原文）'
LINE_ENDING = re.compile(
    r'(?:行尾|换行符?|line[ -]?endings?|line terminators?)[^。；;\n]{0,48}?(?P<cn>CRLF|LF|\\r\\n|\\n)'
    r'|(?P<en>\b(?:CRLF|LF))[ -]?(?:only|line endings?)'
    r'|(?:must use|use only)\s+(?P<use>CRLF|LF)\b', re.I)
EMPTY_EMAIL = re.compile(
    r'(?:空行或邮箱为空|归一化后为空|空邮箱|邮箱为空)[^。；;\n]{0,24}(?:跳过|丢弃|忽略)'
    r'|(?:skip|discard|ignore)[^.;\n]{0,32}(?:empty|blank)[^.;\n]{0,12}(?:email|e-mail)'
    r'|(?:empty|blank)[^.;\n]{0,12}(?:email|e-mail)[^.;\n]{0,32}(?:skip|discard|ignore)', re.I)


def check_instruction(contract, instruction):
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
    output = contract.get('output_spec', '')
    inputs = contract.get('input_spec', '')
    # Rules are enabled only for CSV specifications; never infer other formats.
    csv = 'csv' in (inputs + output).lower()
    def endings(text):
        return {('CRLF' if m.upper() in ('CRLF', r'\R\N') else 'LF')
                for hit in LINE_ENDING.finditer(text) for m in [hit['cn'] or hit['en'] or hit['use']]}
    explicit = endings(output + '\n' + '\n'.join(r['description'] for r in contract.get('requirements', [])))
    nonempty = bool(re.search(r'email[^。；;\n]{0,40}非空|(?:email|e-mail)[^.;\n]{0,40}(?:non[ -]?empty|not empty)', inputs, re.I))
    blank_policy = bool(EMPTY_EMAIL.search(inputs + '\n' + output + '\n' + '\n'.join(
        r['description'] for r in contract.get('requirements', []))))
    for line, text in enumerate(body.splitlines(), 1):
        for clause in re.split(r'[。；;]|\.\s+', text):
            # Negation applies only to its own clause, not later requirements.
            if re.search(r'不要求|无需|不得|不必|must not|do not|not required|need not', clause, re.I):
                continue
            checks = []
            if csv and endings(clause) - explicit:
                checks.append(('UNSUPPORTED_CSV_LINE_ENDING', 'output_spec', output))
            if csv and nonempty and not blank_policy and EMPTY_EMAIL.search(clause):
                checks.append(('OUT_OF_DOMAIN_EMPTY_EMAIL_POLICY', 'input_spec', inputs))
            for code, field, quote in checks:
                findings.append({'code': code, 'line': line, 'instruction_quote': clause,
                                 'contract_field': field, 'contract_quote': quote})
    return {'status': 'blocked' if findings else 'no_findings', 'findings': findings,
            'contract_digest': hashlib.sha256(json.dumps(contract, sort_keys=True, ensure_ascii=False).encode()).hexdigest(),
            'instruction_digest': hashlib.sha256(instruction.encode()).hexdigest(),
            'limitations': 'Finite explicit CSV rules and appendix equality only; not general semantic consistency.'}
