"""Opt-in finite format checks; never infer a format from task text."""
import re

RULE_NAMES = frozenset({'csv-line-endings', 'csv-email-domain'})
LINE_ENDING = re.compile(
    r'(?:行尾|换行符?|line[ -]?endings?|line terminators?)[^。；;\n]{0,48}?(?P<cn>CRLF|LF|\\r\\n|\\n)'
    r'|(?P<en>\b(?:CRLF|LF))[ -]?(?:only|line endings?)'
    r'|(?:must use|use only)\s+(?P<use>CRLF|LF)\b', re.I)
EMPTY_EMAIL = re.compile(
    r'(?:空行或邮箱为空|归一化后为空|空邮箱|邮箱为空)[^。；;\n]{0,24}(?:跳过|丢弃|忽略)'
    r'|(?:skip|discard|ignore)[^.;\n]{0,32}(?:empty|blank)[^.;\n]{0,12}(?:email|e-mail)'
    r'|(?:empty|blank)[^.;\n]{0,12}(?:email|e-mail)[^.;\n]{0,32}(?:skip|discard|ignore)', re.I)



def clauses(text):
    return re.split(r'[。；;\n]|\.\s+', text)


def scope(text, default=None):
    inputs = bool(re.search(r'输入|\binput\b', text, re.I))
    outputs = bool(re.search(r'输出|\boutput\b', text, re.I))
    if inputs and outputs:
        return None  # Mixed or ambiguous scope cannot authorize a blocking rule.
    return 'input_spec' if inputs else 'output_spec' if outputs else default


def endings(text):
    return {('CRLF' if value.upper() in ('CRLF', r'\R\N') else 'LF')
            for hit in LINE_ENDING.finditer(text)
            for value in [hit['cn'] or hit['en'] or hit['use']]}


def check_csv(contract, body, rules):
    findings = []
    authorized = {'input_spec': set(), 'output_spec': set()}
    for field in authorized:
        for clause in clauses(contract.get(field, '')):
            target = scope(clause, field)
            if target is not None:
                authorized[target].update(endings(clause))
    for req in contract.get('requirements', []):
        for clause in clauses(req['description']):
            target = scope(clause)
            if target is not None:
                authorized[target].update(endings(clause))
    inputs = contract.get('input_spec', '')
    nonempty = bool(re.search(r'email[^。；;\n]{0,40}非空|(?:email|e-mail)[^.;\n]{0,40}(?:non[ -]?empty|not empty)', inputs, re.I))
    blank_policy = bool(EMPTY_EMAIL.search(inputs + '\n' + contract.get('output_spec', '') + '\n' + '\n'.join(
        r['description'] for r in contract.get('requirements', []))))
    for line, text in enumerate(body.splitlines(), 1):
        for clause in clauses(text):
            if re.search(r'不要求|无需|不得|不必|must not|do not|not required|need not', clause, re.I):
                continue
            checks = []
            target = scope(clause)
            if 'csv-line-endings' in rules and target is not None and endings(clause) - authorized[target]:
                checks.append(('UNSUPPORTED_CSV_LINE_ENDING', target))
            if 'csv-email-domain' in rules and nonempty and not blank_policy and EMPTY_EMAIL.search(clause):
                checks.append(('OUT_OF_DOMAIN_EMPTY_EMAIL_POLICY', 'input_spec'))
            for code, field in checks:
                findings.append({'code': code, 'line': line, 'instruction_quote': clause,
                                 'contract_field': field, 'contract_quote': contract.get(field, '')})
    return findings
