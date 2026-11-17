"""Opt-in real Docker/Harbor smoke; live repair is a separate explicit option."""
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import unittest
import uuid

from independent_verification.agent import TestAgent
from independent_verification.candidate import CandidateTask
from independent_verification.common import digest, write_json
from independent_verification.controller import review_run
from independent_verification.panel import fingerprint
from independent_verification.repair import RepairDispatcher
from independent_verification.repair_proofs import select_adapter
from synthesis_agent.config import Config
from synthesis_agent.files import load_seed
from tests.general_repair_fixtures import fixture, ScriptedClient, call, script, source, NODE


def smoke_inputs(root, config):
    candidate = fixture(root / 'candidate')
    contract = candidate.contract
    contract.update(objective='Print the product of six and seven.', input_spec='No input.',
                    output_spec='ASCII decimal product of six and seven followed by LF.',
                    requirements=[{'id': 'R1', 'description': 'Write the decimal product of six and seven followed by LF and exit successfully.'}])
    (candidate.source / 'contract.json').write_text(json.dumps(contract))
    probe = ("# PRIVATE_PROBE_SENTINEL\nimport subprocess\n"
             "def check(requirement_id):\n"
             "    if requirement_id != 'R1':\n        raise ValueError(requirement_id)\n"
             "    result = subprocess.run(['python3', '/app/clean.py'], capture_output=True, timeout=COMMAND_TIMEOUT_SEC)\n"
             "    assert result.returncode == 0\n    assert result.stdout == b'42\\n'\n")
    (candidate.source / 'checks/probe.py').write_text(probe)
    metadata = candidate.metadata
    metadata['manifest'].update(digest({'checks/probe.py': probe}))
    (candidate.source / 'synthesis.json').write_text(json.dumps(metadata))
    candidate = CandidateTask.load(candidate.source)
    assert select_adapter(contract) is None
    for name, value in [('development', 43), ('acceptance', 42)]:
        result = TestAgent(config, ScriptedClient(script(contract, source(value)))).generate(
            candidate.test_input(), root / name)
        if result['status'] != 'tests_generated':
            raise AssertionError(result.get('error'))
    rows = []
    for group, role, code, expected in [
            ('feedback', 'correct', 'print(42)', '42\n'),
            ('feedback', 'invalid', 'print(43)', '43\n'),
            ('holdout', 'correct', 'print(7 * 6)', '42\n'),
            ('holdout', 'invalid', 'print(6 * 6)', '36\n')]:
        path = root / ('control-' + group + '-' + role)
        path.mkdir()
        (path / 'solve.sh').write_text("#!/bin/sh\nset -eu\ncat > /app/clean.py <<'PY'\n" + code + '\nPY\n')
        review_path = root / (group + '-' + role + '-review.txt')
        review_path.write_text('Host source review of handwritten arithmetic smoke fixture.\n'
            + 'solve.sh writes this exact Python source: ' + code + '\n'
            + 'Python integer arithmetic gives stdout ' + repr(expected) + ', exit 0.\n'
            + 'The Contract requires decimal 6*7 followed by LF, which is 42 followed by LF.\n'
            + ('This satisfies R1.\n' if role == 'correct' else 'This violates R1.\n'))
        rows.append({'source': str(path.absolute()), 'group': group, 'role': role,
            'implementation_digest': fingerprint(load_seed(path, config).files), 'contract_digest': fingerprint(contract),
            'review': {'status': 'confirmed', 'reviewer': 'Host review of handwritten arithmetic smoke controls',
                       'method': 'contract-source-review', 'rationale': review_path.read_text(),
                       'requirement_ids': ['R1'], 'evidence_paths': [str(review_path.absolute())],
                       'counterexample': {'argv': ['python3', '/app/clean.py'], 'stdin': '',
                                          'expected': '42\n', 'observed': expected}}})
    write_json(root / 'controls.json', {'controls': rows})
    return candidate


@unittest.skipUnless(os.getenv('GENERAL_REPAIR_DOCKER') == '1', 'opt-in real Docker/Harbor smoke')
class RealGeneralRepairTests(unittest.TestCase):
    def test_native_repair_and_offline_replay(self):
        live = os.getenv('GENERAL_REPAIR_LIVE') == '1'
        config = Config.from_env(max_model_calls=int(os.getenv('GENERAL_REPAIR_MAX_MODEL_CALLS', '16')),
                                 max_tool_calls=int(os.getenv('GENERAL_REPAIR_MAX_TOOL_CALLS', '40')))
        run_id = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '_' + uuid.uuid4().hex[:8]
        root = Path(__file__).resolve().parents[1] / 'runs/02_general_repair' / run_id
        root.mkdir(parents=True)
        write_json(root / 'smoke.json', {'experiment_id': '02_general_repair', 'run_id': run_id,
            'kind': 'fault_injection_smoke', 'model': 'live' if live else 'scripted',
            'network_mode': {'docker': 'none', 'harbor': 'public'}})
        candidate = smoke_inputs(root, config)
        proposal = {'requirement_id': 'R1', 'contract_quote': candidate.contract['requirements'][0]['description'],
                    'test_path': 'tests/test_behavior.py', 'line': '6', 'evidence_id': 'known-000:' + NODE + ':call',
                    'explanation': 'The development assertion expects 43; the Contract specifies 6*7, which is 42.',
                    'components': 'tests', 'expected_change': 'Correct the assertion without removing checks.',
                    'validation_plan': 'Rerun development controls, frozen acceptance, Docker and Harbor.'}
        client = None if live else ScriptedClient([
            call('propose_repair', **proposal), call('write_file', path='tests/test_behavior.py', content=source(42)),
            call('collect'), call('finish', coverage=[{'requirement_id': 'R1', 'test_names': [NODE]}])])
        result = RepairDispatcher(config, client).run(candidate.source, root / 'verification',
            tests_output=root / 'development', acceptance_tests=root / 'acceptance',
            controls_manifest=root / 'controls.json', harbor_python=os.getenv('HARBOR_PYTHON'), max_repairs=2)
        write_json(root / 'outcome.json', {'experiment_id': '02_general_repair', 'run_id': run_id,
            'decision': result['controller_decision']['decision'], 'model': 'live' if live else 'scripted',
            'stop_reason': result['repair_workflow']['stop_reason']})
        self.assertEqual(result['controller_decision']['decision'], 'accept', str(root))
        self.assertEqual(review_run(root / 'verification', root / 'replay')['decision'], 'accept', str(root))
