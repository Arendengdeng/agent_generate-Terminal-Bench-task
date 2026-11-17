"""Serial live-model batch runner. A blocked specification is never a candidate."""
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import time

from synthesis_agent.agent import SynthesisAgent
from synthesis_agent.config import Config
from synthesis_agent.files import read_json
from synthesis_agent.trace import redact
from independent_verification.candidate import CandidateTask
from independent_verification.common import new_directory, write_json
from independent_verification.harbor import Harbor, execute
from independent_verification.pipeline import preflight, verify
from independent_verification.sandbox import VERIFIER_IMAGE
from .controls import prepare_controls
from .specs import default_specs, validate_specs

PHASES = ('synthesis', 'controls', 'independent_test', 'challenge', 'repair', 'reverification')


def hashes(root):
    result = {}
    for path in sorted(Path(root).rglob('*')):
        if path.is_file() and not path.is_symlink():
            digest = hashlib.sha256()
            with path.open('rb') as stream:
                for chunk in iter(lambda: stream.read(65536), b''):
                    digest.update(chunk)
            result[str(path.relative_to(root))] = digest.hexdigest()
    return result


def initial_record(spec):
    return {'id': spec['id'], 'family': spec['family'], 'variant': spec['variant'],
            'outcome': 'unresolved', 'detail': 'not_run', 'failure_stage': None,
            'responsible_module': 'unknown', 'candidate_generated': False,
            'stages': {p: {'status': 'not_run', 'reason': 'upstream_not_completed'} for p in PHASES},
            'cost': {'model_calls': 0, 'tool_calls': 0, 'wall_sec': 0}, 'repair_count': 0}


def verification_record(root, result, record):
    """Project native evidence without converting errors or missing stages to passes."""
    stages = record['stages']
    tests = root / 'verification/test-agent/tests.json'
    if tests.exists():
        generated = read_json(tests)
        stages['independent_test'] = {'status': 'passed' if generated.get('status') == 'tests_generated' else 'error',
                                      'evidence': str(tests)}
    loop = result.get('test_loop')
    if loop:
        stages['independent_test'].update(status=loop['status'], evidence=str(root / 'verification/run_result.json'))
    challenge = result.get('challenge')
    if challenge:
        evidence = result['challenge_report_path']
        stages['challenge'] = {'status': 'completed' if challenge.get('search_status') == 'completed' else challenge['status'],
                               'evidence': evidence,
                               'confirmed_violations': sum(s.get('violation_status') == 'confirmed' for s in challenge['samples']),
                               'already_rejected': sum(s.get('status') == 'rejected' for s in challenge['samples']),
                               'review_queue': challenge.get('review_queue', [])}
        record['repair_count'] = (loop or {}).get('repairs', 0) + challenge.get('repairs', 0)
        stages['repair'] = {'status': ('passed' if record['repair_count'] else 'not_needed')
                            if challenge['status'] == 'passed' else challenge['status'],
                            'attempts': record['repair_count'], 'evidence': evidence}
        if challenge.get('review_queue') or challenge.get('unresolved'):
            stages['repair']['status'] = 'needs_review'
    elif loop and loop.get('repairs'):
        record['repair_count'] = loop['repairs']
        stages['repair'] = {'status': loop['status'], 'attempts': loop['repairs'],
                            'evidence': str(root / 'verification/run_result.json')}
    decision = result.get('controller_decision', {}).get('decision')
    record['controller_decision'] = decision
    record['native_stage'] = result.get('stage')
    record['error'] = result.get('error')
    if result.get('holdout_started'):
        stages['reverification'] = {'status': 'passed' if decision == 'accept' else result['status'],
                                    'evidence': str(root / 'verification/run_result.json')}
    queue = challenge and (challenge.get('review_queue') or challenge.get('unresolved'))
    full = all(stages[p]['status'] in {'passed', 'completed', 'not_needed'} for p in PHASES)
    if (decision == 'accept' and result.get('end_to_end_validated') is True
            and result.get('evidence_sufficient') is True and result.get('panel_validated') is True
            and full and not queue):
        record.update(outcome='accepted', detail='accepted', failure_stage=None, responsible_module=None)
        return
    stage = result.get('stage', 'unknown')
    module = {'preflight': 'infrastructure', 'test_generation': 'test_agent',
              'test_execution': 'unknown', 'challenge': 'unknown',
              'export': 'exporter', 'lint': 'unknown', 'execution': 'unknown', 'static_check': 'unknown'}.get(stage, 'unknown')
    explicit_owner = result.get('controller_decision', {}).get('responsible_module')
    if explicit_owner:
        module = explicit_owner
    record.update(outcome='rejected' if stage == 'static_check' and result.get('status') == 'failed' else 'unresolved',
                  detail='needs_review' if queue or decision in {'accept', 'needs_review', 'repair'} else result.get('status', 'error'),
                  failure_stage='challenge' if queue else stage, responsible_module='unknown' if queue else module)


def run_one(spec, root, config, *, harbor_python=None, max_attempts=4, max_repairs=2):
    record = initial_record(spec)
    started = time.monotonic()
    synthesis_budget = {'model_calls': 0, 'tool_calls': 0}
    verification_budget = {'model_calls': 0, 'tool_calls': 0}
    phase = 'synthesis'
    try:
        record['stages'][phase] = {'status': 'running'}
        generated = SynthesisAgent(config).generate(spec['plan'], spec['contract'], root / 'candidate', budget=synthesis_budget)
        record['stages'][phase] = {'status': 'passed' if generated['status'] == 'candidate_generated' else generated['status'],
                                   'evidence': str(root / 'candidate/synthesis.json')}
        if generated['status'] == 'cancelled':
            raise KeyboardInterrupt
        if generated['status'] != 'candidate_generated':
            record.update(detail=generated['status'], error=generated.get('error'),
                          failure_stage=phase, responsible_module='synthesis_agent')
            return record
        record['candidate_generated'] = True
        candidate = CandidateTask.load(root / 'candidate', config)
        phase = 'controls'
        record['stages'][phase] = {'status': 'running'}
        manifest = prepare_controls(candidate, spec, root / 'controls', config)
        record['stages'][phase] = {'status': 'passed', 'evidence': str(manifest)}
        phase = 'independent_test'
        result = verify(root / 'candidate', root / 'verification', config=config, stage='all',
                        controls_manifest=manifest, harbor_python=harbor_python,
                        repair_tests=True, challenge=True, max_test_repairs=max_repairs,
                        max_challenge_attempts=max_attempts, _budget=verification_budget)
        verification_record(root, result, record)
        if result.get('status') == 'cancelled':
            raise KeyboardInterrupt
        return record
    except KeyboardInterrupt:
        record.update(outcome='unresolved', detail='cancelled', failure_stage=phase, responsible_module='unknown')
        record['stages'][phase].update(status='cancelled')
        raise
    except Exception as exc:
        record.update(detail='error', failure_stage=phase,
                      responsible_module='unknown',
                      error={'type': type(exc).__name__, 'message': str(exc)})
        record['stages'][phase].update(status='error')
        return record
    finally:
        record['cost'] = {'model_calls': synthesis_budget['model_calls'] + verification_budget['model_calls'],
                          'tool_calls': synthesis_budget['tool_calls'] + verification_budget['tool_calls'],
                          'wall_sec': round(time.monotonic() - started, 3),
                          'synthesis': synthesis_budget, 'verification': verification_budget}
        write_json(root / 'result.json', redact(record, config.api_key))
        write_json(root / 'evidence-manifest.json', hashes(root))


def build_report(root):
    """Rebuild the summary from per-task records, checking all recorded evidence bytes."""
    root = Path(root).absolute()
    protocol = read_json(root / 'protocol.json')
    rows = []
    for spec in protocol['tasks']:
        task = root / 'tasks' / spec['id']
        row = read_json(task / 'result.json')
        manifest = read_json(task / 'evidence-manifest.json')
        current = hashes(task)
        changes = [p for p, digest in manifest.items() if current.get(p) != digest]
        changes.extend('unmanifested: ' + p for p in sorted(current.keys() - manifest.keys() - {'evidence-manifest.json'}))
        required = {'result.json', 'inputs/plan.json', 'inputs/contract.json', 'inputs/spec.json'}
        if not required <= manifest.keys():
            changes.append('missing required evidence manifest entries')
        if row['outcome'] == 'accepted':
            required_final = {'candidate/synthesis.json', 'verification/run_result.json',
                              'verification/decision.json', 'verification/challenge/challenge-report.json'}
            if not required_final <= manifest.keys():
                changes.append('missing accepted-run evidence')
            elif not changes and (read_json(task / 'verification/decision.json').get('decision') != 'accept'
                  or read_json(task / 'verification/run_result.json').get('end_to_end_validated') is not True
                  or read_json(task / 'candidate/synthesis.json').get('status') != 'candidate_generated'):
                changes.append('native reports do not confirm acceptance')
        if changes:
            row.update(outcome='unresolved', detail='evidence_changed', failure_stage='audit',
                       responsible_module='unknown', evidence_errors=changes)
        rows.append(row)
    counts = Counter(r['outcome'] for r in rows)
    summary = {'status': 'completed' if all(r['candidate_generated'] and r['detail'] not in {'blocked','cancelled','not_run'} for r in rows) else 'incomplete',
               'planned': len(rows), 'generated': sum(r['candidate_generated'] for r in rows),
               'accepted': counts['accepted'], 'rejected': counts['rejected'], 'unresolved': counts['unresolved'],
               'all_accepted': counts['accepted'] == len(rows),
               'cancelled': any(r['detail'] == 'cancelled' for r in rows),
               'model_calls': sum(r['cost']['model_calls'] for r in rows),
               'tool_calls': sum(r['cost']['tool_calls'] for r in rows), 'tasks': rows,
               'limitation': 'Finite task/control evidence; blocked input specifications are not generated task packages.'}
    text = ['# 六候选 CLI 修复批次', '',
            f"计划 {len(rows)}；实际生成 {summary['generated']}；接受 {counts['accepted']}；拒绝 {counts['rejected']}；未决 {counts['unresolved']}。",
            f"模型调用 {summary['model_calls']}；工具调用 {summary['tool_calls']}。", '',
            '|任务|生成|结果|失败阶段|责任模块|修复次数|记录|', '|---|---|---|---|---|---:|---|']
    for row in rows:
        ident = row['id']
        text.append(f"|{ident}|{row['candidate_generated']}|{row['outcome']} / {row['detail']}|{row['failure_stage'] or '—'}|"
                    f"{row['responsible_module'] or '—'}|{row['repair_count']}|[记录](tasks/{ident}/result.json)|")
    text.extend(['', 'Repair=not_needed 表示无需实际修改，仍须最终复验。执行异常、超时、null 和未执行不算成功拒绝。',
                 '未决样本不归为失败已确认；无法确定责任时记录 unknown。'])
    # These two derived files belong to the report builder and may be rebuilt.
    for name, content in [('summary.json', json.dumps(summary, ensure_ascii=False, indent=2) + '\n'),
                          ('report.md', '\n'.join(text) + '\n')]:
        temp = root / (name + '.tmp')
        with temp.open('x', encoding='utf-8') as stream:
            stream.write(content)
        temp.replace(root / name)
    return summary


def run_batch(output, *, project, config=None, specs=None, harbor_python=None, max_attempts=4, max_repairs=2):
    config = config or Config.from_env()
    if type(max_attempts) is not int or not 1 <= max_attempts <= 100:
        raise ValueError('max challenge attempts must be between 1 and 100')
    if type(max_repairs) is not int or not 0 <= max_repairs <= 2:
        raise ValueError('max repairs must be between 0 and 2')
    canonical = default_specs(project)
    specs = validate_specs(specs if specs is not None else canonical)
    recipes = {(s['family'], s['variant']): s['contract'] for s in canonical}
    if any(s['contract'] != recipes[(s['family'],s['variant'])] for s in specs):
        raise ValueError('custom Contracts require a separately source-reviewed control recipe; use the bundled six Contracts')
    root = new_directory(output)
    protocol = {'schema_version': 1, 'started_at': datetime.now(timezone.utc).isoformat(),
                'tasks': specs, 'config': config.public(), 'max_challenge_attempts': max_attempts,
                'max_repairs': max_repairs, 'repair_policy': 'only_controller_confirmed_defects; otherwise not_needed',
                'budget_policy': 'Synthesis and verification each use Config call limits; verification shares its budget across all stages.',
                'execution': 'serial; live model only; no fallback to scripted generation; holdouts terminal-only'}
    write_json(root / 'protocol.json', protocol)
    for package in ('synthesis_agent', 'independent_verification'):
        shutil.copytree(Path(project) / package, root / 'source' / package,
                        ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
    write_json(root / 'source-manifest.json', hashes(root / 'source'))
    git = {}
    for label, args in [('head',['rev-parse','HEAD']), ('status',['status','--short']), ('diff',['diff','HEAD'])]:
        proc = subprocess.run(['git', *args], cwd=project, capture_output=True, text=True)
        git[label] = {'exit_code': proc.returncode, 'output': proc.stdout, 'error': proc.stderr}
    write_json(root / 'git-provenance.json', redact(git, config.api_key))
    for spec in specs:
        inputs = root / 'tasks' / spec['id'] / 'inputs'
        inputs.mkdir(parents=True)
        for name in ('plan', 'contract'):
            write_json(inputs / (name + '.json'), spec[name])
        write_json(inputs / 'spec.json', spec)
    ready = None
    cancelled = False
    try:
        ready = preflight(root, Harbor(harbor_python))
        if any(ready.get(name, {}).get('process', {}).get('cancelled') for name in ('docker', 'harbor_network')):
            raise KeyboardInterrupt
        missing = [] if config.model else ['SYNTHESIS_MODEL']
        if not config.api_key:
            missing.append('SYNTHESIS_API_KEY/OPENAI_API_KEY')
        images = {}
        if ready['docker']['status'] == 'available':
            for label, image in [('task', config.image), ('verifier', VERIFIER_IMAGE)]:
                proc = execute(['docker','image','inspect',image], root, root / (label + '-image'), 30)
                if proc.get('cancelled'):
                    raise KeyboardInterrupt
                images[label] = {'image': image, 'status': 'available' if proc['exit_code'] == 0 and not proc['error'] else 'unavailable', 'process': proc}
        write_json(root / 'batch-preflight.json', {'dependencies': ready, 'missing_configuration': missing, 'images': images})
        available = ready['status'] == 'ready' and not missing and all(i['status'] == 'available' for i in images.values())
        for spec in specs:
            task = root / 'tasks' / spec['id']
            if not available:
                record = initial_record(spec)
                record.update(detail='blocked', failure_stage='preflight', responsible_module='configuration' if missing else 'infrastructure',
                              evidence=str(root / 'batch-preflight.json'))
                write_json(task / 'result.json', record)
                write_json(task / 'evidence-manifest.json', hashes(task))
                continue
            print('Running ' + spec['id'], flush=True)
            run_one(spec, task, config, harbor_python=harbor_python, max_attempts=max_attempts, max_repairs=max_repairs)
    except KeyboardInterrupt:
        cancelled = True
    except Exception as exc:
        write_json(root / 'batch-error.json', redact({'type': type(exc).__name__, 'message': str(exc)}, config.api_key))
    finally:
        for spec in specs:
            task = root / 'tasks' / spec['id']
            if not (task / 'result.json').exists():
                record = initial_record(spec)
                record.update(detail='cancelled' if cancelled else 'blocked', failure_stage='preflight' if ready is None else 'batch',
                              responsible_module='unknown', reason='batch interrupted before this task')
                write_json(task / 'result.json', record)
                write_json(task / 'evidence-manifest.json', hashes(task))
        summary = build_report(root)
    summary['cancelled'] = cancelled
    return summary
