"""Task-neutral evidence envelopes. Payloads are observations, never verdicts.

Consumers supply an already permission-filtered projection; this module does
not follow paths or read logs from disk.
"""
import copy
import hashlib
import json


POLICY = 'execution-feedback-v1'


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def envelope(*, version, stage, status, requirements, evidence, changes=(), visibility='development'):
    if visibility not in {'development', 'private', 'evaluation'}:
        raise ValueError('invalid evidence visibility')
    rows = copy.deepcopy(list(evidence))
    ids = [row['id'] for row in rows]
    if len(set(ids)) != len(ids):
        raise ValueError('duplicate evidence IDs')
    return {'schema_version': 1, 'task_version': version, 'stage': stage,
            'status': status, 'visibility': visibility, 'requirements': copy.deepcopy(requirements),
            'evidence': rows, 'changed_paths': list(changes)}


def execution_feedback(projection, *, version=None):
    """Normalize public runner feedback without reading any implementation files."""
    evidence = copy.deepcopy(projection.get('evidence', []))
    for row in evidence:
        row.setdefault('type', 'test_result' if 'nodeid' in row else 'execution_outcome')
        row.setdefault('visibility', 'development')
    for trial in projection.get('trials', []):
        evidence.append({'id': trial['label'] + ':process', 'type': 'command_result',
                         'visibility': 'development',
                         **{k: trial.get(k) for k in ('command', 'cwd', 'exit_code', 'error_kind')}})
        if trial.get('artifact_manifest'):
            evidence.append({'id': trial['label'] + ':artifacts', 'type': 'file_manifest',
                             'visibility': 'development', 'manifest': trial['artifact_manifest']})
        for stream in ('stdout', 'stderr'):
            if trial.get(stream):
                evidence.append({'id': trial['label'] + ':' + stream, 'type': 'text',
                                 'visibility': 'development', 'content': trial[stream]})
    return envelope(version=version or projection.get('tests_digest'), stage='independent_execution',
                    status=projection['status'], requirements=projection.get('requirements', {}),
                    evidence=evidence)


def self_check_feedback(report, contract):
    evidence = [{'id': 'self-check:' + key, 'type': 'execution_result', 'content': report[key],
                 'visibility': 'private'} for key in ('initial', 'solution_execution', 'repaired', 'error')
                if key in report]
    return envelope(version=report.get('digest'), stage='self_check', status=report['status'],
                    requirements=contract['requirements'], evidence=evidence,
                    changes=report.get('changed_paths', ()), visibility='private')


def read_evidence(packet, evidence_id, offset=0, limit=4000):
    """Chunk one authorized in-memory observation; no arbitrary path access."""
    if packet.get('visibility') != 'development':
        raise ValueError('only development evidence may enter diagnosis')
    row = next((e for e in packet['evidence'] if e['id'] == evidence_id), None)
    if row is None or row.get('visibility', 'development') != 'development':
        raise ValueError('evidence is not authorized')
    content = json.dumps(row, ensure_ascii=False)
    if type(offset) is not int or not 0 <= offset <= len(content):
        raise ValueError('invalid evidence offset')
    return {'content': content[offset:offset + limit], 'next_offset': min(offset + limit, len(content)),
            'total_chars': len(content), 'truncated': offset + limit < len(content)}
