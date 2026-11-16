"""Zero-model, zero-container syntax/import/CLI and example input checks."""
import ast
import importlib
import json
from pathlib import Path
import subprocess
import sys

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))


def main():
    modules = []
    for package in ('synthesis_agent', 'independent_verification'):
        for path in sorted((PROJECT / package).rglob('*.py')):
            ast.parse(path.read_text(encoding='utf-8'), filename=str(path))
            parts = path.relative_to(PROJECT).with_suffix('').parts
            name = '.'.join(parts[:-1] if parts[-1] == '__init__' else parts)
            importlib.import_module(name)
            modules.append(name)
    from synthesis_agent.inputs import validate_inputs, instruction_appendix
    from synthesis_agent.consistency import check_instruction
    from independent_verification.candidate import CandidateTask, check_candidate
    examples = []
    for family in ('csv', 'jsonl', 'manifest'):
        root = PROJECT / 'examples' / (family + '-repair')
        plan = json.loads((root / 'plan.json').read_text())
        contract = json.loads((root / 'contract.json').read_text())
        validate_inputs(plan, contract)
        report = check_instruction(contract, instruction_appendix(contract))
        assert report['status'] == 'no_findings', report
        examples.append(family)
    frozen = check_candidate(CandidateTask.load(PROJECT / 'examples/frozen-csv/candidate'))
    assert frozen['status'] == 'passed', frozen
    commands = [[sys.executable, '-m', name, '--help'] for name in
                ('synthesis_agent', 'independent_verification', 'synthesis_agent.candidate_batch')]
    commands += [[sys.executable, str(PROJECT / 'scripts/challenge_agent/run_e2e.py'), '--help'],
                 [sys.executable, str(PROJECT / 'scripts/run_frozen_example.py'), '--help']]
    for command in commands:
        subprocess.run(command, cwd=PROJECT, check=True, capture_output=True, text=True)
    print(json.dumps({'imported_modules': len(modules), 'cli_help_passed': len(commands),
                      'example_input_and_appendix_checks': examples, 'frozen_candidate_static': frozen['status'],
                      'model_calls': 0, 'docker_calls': 0,
                      'limitation': 'Plan/Contract checks are not generated task execution or semantic coverage.'}, indent=2))


if __name__ == '__main__':
    main()
