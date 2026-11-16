"""Deterministic export; lint and execution remain separate, evidenced stages."""
import json
from pathlib import Path, PurePosixPath
import shlex

from synthesis_agent.config import Config
from synthesis_agent.errors import SynthesisError
from synthesis_agent.files import FileSet, load_seed, read_json
from .candidate import check_candidate
from .common import new_directory, test_path, validate_coverage, write_json
from .sandbox import base_dockerfile, wrapper_source


HARBOR_NETWORK_MODE = "public"


def artifact_policy(candidate, config):
    return {'paths': candidate.contract['deliverables']['artifact_paths'],
            'file_limit': config.max_file_bytes, 'total_limit': config.max_total_bytes,
            'count_limit': config.max_files}


def load_tests(candidate, tests_output, config=None, *, check_static=True):
    """Read and verify a frozen test version without creating an export."""
    config = config or Config()
    tests_output = Path(tests_output)
    if check_static:
        static = check_candidate(candidate, config)
        if static['status'] != 'passed':
            raise SynthesisError('candidate failed static checks: ' + json.dumps(static['errors']))
    metadata = read_json(tests_output / 'tests.json')
    if metadata.get('status') != 'tests_generated':
        raise SynthesisError('tests have not been generated successfully')
    if metadata.get('input_manifest') != candidate.input_manifest():
        raise SynthesisError('tests are not bound to this candidate input snapshot')
    tests = load_seed(tests_output / 'tests', config)
    if tests.manifest() != metadata.get('manifest') or tests.digest() != metadata.get('digest'):
        raise SynthesisError('test files differ from frozen generation result')
    for p in tests.files:
        test_path(p)
    validate_coverage(candidate.contract, metadata.get('coverage'), metadata.get('nodeids'))
    return metadata, tests


def export_task(candidate, tests_output, output, config=None):
    config = config or Config()
    metadata, tests = load_tests(candidate, tests_output, config)
    files = FileSet(config)
    files.put('instruction.md', candidate.instruction)
    for folder, contents in [('environment', candidate.environment),
                             ('solution', candidate.reference_solution), ('tests', tests.files)]:
        for p, content in contents.items():
            files.put(folder + '/' + p, content)
    artifacts = candidate.contract['deliverables']['artifact_paths']
    parents = sorted({'/app', *(str(PurePosixPath(p).parent) for p in artifacts)})
    files.put('tests/Dockerfile', base_dockerfile() +
              'RUN mkdir -p /tests /logs/verifier ' + ' '.join(shlex.quote(p) for p in parents) + '\n' +
              'COPY . /tests/\nWORKDIR /tests\n')
    files.put('tests/test.sh', '#!/bin/sh\nset -eu\nexec python3 -I /tests/run_tests.py\n')
    files.put('tests/run_tests.py', wrapper_source())
    files.put('tests/expected.json', json.dumps({'nodeids': metadata['nodeids'], 'artifact_policy': artifact_policy(candidate, config)}))
    files.put('task.toml', 'schema_version = "1.3"\nartifacts = ' + json.dumps(artifacts) + '\n' +
              '[agent]\ntimeout_sec = 300\n' +
              '[verifier]\ntimeout_sec = 120\nenvironment_mode = "separate"\n' +
              '[verifier.environment]\nnetwork_mode = "public"\nbuild_timeout_sec = 600\ncpus = 1\nmemory_mb = 512\n' +
              '[environment]\nnetwork_mode = "public"\nbuild_timeout_sec = 600\ncpus = 1\nmemory_mb = 512\n')
    root = new_directory(output)
    files.export(root / 'task')
    report = {'task_dir': 'task', 'status': 'exported', 'structure_valid': None,
              'lint': {'status': 'not_run'}, 'network_mode': HARBOR_NETWORK_MODE, 'manifest': files.manifest(),
              'nodeids': metadata['nodeids'], 'errors': [], 'independent_validation': False}
    write_json(root / 'package.json', report)
    return report
