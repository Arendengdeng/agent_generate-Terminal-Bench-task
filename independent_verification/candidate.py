"""Read Synthesis artifacts without treating its self-check as verification."""
import copy
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re

from synthesis_agent.config import Config
from synthesis_agent.errors import SynthesisError
from synthesis_agent.files import load_seed, read_json, read_regular, relative_path, safe_ancestors
from synthesis_agent.consistency import check_instruction
from synthesis_agent.inputs import validate_inputs
from .common import digest


@dataclass(frozen=True)
class CandidateTask:
    source: Path
    contract: dict
    instruction: str
    environment: dict
    reference_solution: dict
    metadata: dict

    @classmethod
    def load(cls, source, config=None):
        config = config or Config()
        root = safe_ancestors(Path(source).absolute())
        metadata = read_json(root / 'synthesis.json')
        if metadata.get('status') != 'candidate_generated':
            raise SynthesisError('candidate must have status candidate_generated')
        expected = {'instruction_path': 'draft/instruction.md',
                    'environment_dir': 'draft/environment',
                    'dockerfile_path': 'draft/environment/Dockerfile',
                    'solution_dir': 'draft/solution',
                    'solution_entrypoint': 'draft/solution/solve.sh'}
        if any(metadata.get(k) != v for k, v in expected.items()):
            raise SynthesisError('unsupported candidate layout or metadata paths')
        manifest = metadata.get('manifest')
        if not isinstance(manifest, dict) or not manifest or len(manifest) > config.max_files:
            raise SynthesisError('missing or oversized candidate manifest')
        verified = {}
        for name, sha in manifest.items():
            relative_path(name)
            if not (name.startswith(('draft/environment/', 'draft/solution/'))
                    or name in {'draft/instruction.md', 'checks/probe.py'}):
                raise SynthesisError('unsupported manifest path: ' + name)
            raw = read_regular(root / name, config.max_file_bytes)
            if hashlib.sha256(raw).hexdigest() != sha:
                raise SynthesisError('candidate manifest mismatch: ' + name)
            verified[name] = raw.decode('utf-8')
            if sum(len(s.encode()) for s in verified.values()) > config.max_total_bytes:
                raise SynthesisError('candidate exceeds total byte budget')
        # Detect unmanifested files as well as missing/modified files.
        draft = load_seed(root / 'draft', config).files
        if digest({'draft/' + p: s for p, s in draft.items()}) != {
                p: h for p, h in manifest.items() if p.startswith('draft/')}:
            raise SynthesisError('draft contains unmanifested or missing files')
        contract = read_json(root / 'contract.json')
        validate_inputs({'title': 'candidate', 'category': 'cli_repair', 'goal': 'verify',
                         'scenario': 'verify', 'skills': ['testing']}, contract)
        return cls(root, contract, draft.get('instruction.md', ''),
                   {p[len('environment/'):]: s for p, s in draft.items() if p.startswith('environment/')},
                   {p[len('solution/'):]: s for p, s in draft.items() if p.startswith('solution/')}, metadata)

    def test_input(self):
        # Deliberate projection: never serialize the CandidateTask into model messages.
        return copy.deepcopy({'contract': self.contract, 'instruction': self.instruction,
                              'initial_environment': self.environment})

    def input_manifest(self):
        return digest({'inputs/contract.json': json.dumps(self.contract, ensure_ascii=False),
                       'inputs/instruction.md': self.instruction,
                       **{'inputs/environment/' + p: s for p, s in self.environment.items()}})


def check_candidate(candidate, config=None):
    """Conservative checks for the existing single-container stdlib CLI format.

    This is not a semantic specification checker or proof of absence of leakage.
    """
    consistency = check_instruction(candidate.contract, candidate.instruction,
                                    rules=(config or Config()).consistency_rules)
    errors = [{'path': 'instruction.md', 'message': f['code'], **f}
              for f in consistency['findings']]
    def fail(path, message):
        errors.append({'path': path, 'message': message})
    if not candidate.instruction.strip():
        fail('instruction.md', 'missing instruction')
    solution = candidate.reference_solution
    if not solution.get('solve.sh', '').strip():
        fail('solution/solve.sh', 'missing reference entrypoint')
    for p, content in solution.items():
        if p.endswith('.sh') and '\r' in content:
            fail('solution/' + p, 'shell scripts must use LF line endings')
    env = candidate.environment
    for p in env:
        if p != 'Dockerfile' and not p.startswith('app/'):
            fail('environment/' + p, 'only Dockerfile and app/ are supported')
        if any(part.lower() in {'solution', 'solutions', 'checks', 'tests', '.git', '.env'}
               for part in Path(p).parts):
            fail('environment/' + p, 'reserved private/test material in initial environment')
    for artifact in candidate.contract['deliverables']['artifact_paths']:
        p = artifact.lstrip('/')
        if p not in env and not any(k.startswith(p + '/') for k in env):
            fail(artifact, 'declared repair artifact absent from initial environment')
    # Only accept the trusted Dockerfile shape emitted by Synthesis. Do not run
    # arbitrary candidate build instructions or external build contexts.
    dockerfile = env.get('Dockerfile', '')
    lines = dockerfile.splitlines()
    image = lines[0][5:] if lines and lines[0].startswith('FROM ') else ''
    expected_tail = [
        'ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 HOME=/tmp',
        'RUN mkdir -p /app && chown 65532:65532 /app',
        'COPY --chown=65532:65532 app/ /app/', 'USER 65532:65532',
        'WORKDIR /app', 'CMD ["/bin/sh"]']
    if (not re.fullmatch(r'[a-zA-Z0-9][a-zA-Z0-9_./:@-]*', image)
            or lines[1:] != expected_tail):
        fail('environment/Dockerfile', 'unsupported Dockerfile; expected trusted Synthesis template')
    if image != candidate.metadata.get('image_reference'):
        fail('environment/Dockerfile', 'base image differs from Synthesis metadata')
    for p, content in env.items():
        if p != 'Dockerfile' and content.strip() and any(content == s for s in solution.values()):
            fail('environment/' + p, 'identical reference-solution file in initial environment')
    return {'status': 'failed' if errors else 'passed', 'errors': errors,
            'instruction_consistency': consistency,
            'source': str(candidate.source), 'input_manifest': candidate.input_manifest(),
            'candidate_manifest': candidate.metadata['manifest'],
            'independent_validation': False,
            'limitations': ['Static checks do not prove semantic coverage or absence of all answer leakage.',
                           'Synthesis self-check is not independent verification.']}
