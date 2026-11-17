"""Private, version-bound Self-check records; no task semantics or host path tools."""
import copy
import json

from .errors import SynthesisError
from .files import FileSet
from .trace import redact, provenance, run_identity


def repaired_passes(report):
    rows = report.get('repaired', {}).get('results', [])
    return (report.get('status') in {'passed', 'failed'}
            and report.get('solution_execution', {}).get('exit_code') == 0
            and report.get('repaired', {}).get('status') == 'completed'
            and bool(rows) and all(row['status'] == 'pass' for row in rows))


class SelfCheckJournal:
    def __init__(self, root, config, contract):
        self.root, self.config, self.contract = root, config, contract
        self.checks, self.attempts, self.hypotheses, self.evidence = [], [], [], {}
        self.protected = None

    def save(self, path, value):
        target = self.root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open('x', encoding='utf-8') as stream:
            json.dump(redact(value, self.config.api_key), stream, ensure_ascii=False, indent=2)

    def snapshot(self, path, files):
        snapshot = FileSet(self.config)
        snapshot.files = copy.deepcopy(files.files)
        snapshot.export(self.root / path)

    def record_check(self, files, report):
        check_id = f'check-{len(self.checks) + 1:04d}'
        report['check_id'] = check_id
        report['task_version'] = report['digest']
        path = f'self-check/{check_id}'
        self.snapshot(path + '/files', files)
        requirements = {r['id']: r for r in self.contract['requirements']}
        index = []
        for stage in ('initial', 'solution_execution', 'repaired', 'protected_repaired', 'error'):
            if stage not in report:
                continue
            value = report[stage]
            rows = value.get('results', []) if isinstance(value, dict) else []
            entries = [(row['id'], row) for row in rows]
            entries.append(('process', {k: v for k, v in value.items() if k != 'results'}
                            if isinstance(value, dict) else value))
            for suffix, content in entries:
                evidence_id = f'{check_id}:{stage}:{suffix}'
                row = {'id': evidence_id, 'task_version': report['digest'], 'visibility': 'private',
                       'stage': stage, 'requirement': requirements.get(suffix), 'content': copy.deepcopy(content)}
                self.evidence[evidence_id] = redact(row, self.config.api_key)
                index.append({'id': evidence_id, 'stage': stage, 'requirement_id': suffix,
                              'status': content.get('status') if isinstance(content, dict) else 'error'})
        report['evidence_index'] = index
        self.save(path + '/report.json', report)
        self.checks.append({'check_id': check_id, 'digest': report['digest'], 'status': report['status'],
                            'report': path + '/report.json'})
        return self.view(report)

    def view(self, report):
        # Direct locations and error text, with large input/output/locals available by ID.
        view = {k: copy.deepcopy(report[k]) for k in ('status', 'digest', 'check_id', 'error', 'evidence_index') if k in report}
        for stage in ('initial', 'repaired', 'protected_repaired'):
            if stage in report:
                view[stage] = {'status': report[stage]['status'], 'results': []}
                for row in report[stage].get('results', []):
                    item = {k: row[k] for k in ('id', 'status', 'message') if k in row}
                    item['locations'] = [{k: frame[k] for k in ('path', 'line', 'function', 'source')}
                                         for frame in row.get('exception', {}).get('frames', [])]
                    view[stage]['results'].append(item)
        view['solution_execution'] = {k: report.get('solution_execution', {}).get(k) for k in ('exit_code',)}
        view['protected_solution_version'] = self.protected['digest'] if self.protected else None
        return view

    def read(self, evidence_id, offset):
        if evidence_id not in self.evidence:
            raise SynthesisError('unknown private evidence ID')
        text = json.dumps(self.evidence[evidence_id], ensure_ascii=False)
        if type(offset) is not int or not 0 <= offset <= len(text):
            raise SynthesisError('invalid evidence offset')
        return {'content': text[offset:offset + 4000], 'next_offset': min(len(text), offset + 4000),
                'total_chars': len(text), 'truncated': offset + 4000 < len(text)}

    def hypothesis(self, args, digest):
        if not isinstance(args['hypothesis'], str) or not args['hypothesis'].strip():
            raise SynthesisError('nonempty hypothesis required')
        if not isinstance(args['next_check'], str) or not args['next_check'].strip():
            raise SynthesisError('next_check required')
        rids = args['requirement_ids']
        if not isinstance(rids, list) or not rids or any(type(r) is not str for r in rids):
            raise SynthesisError('requirement_ids must be a nonempty string list')
        if not set(rids) <= {r['id'] for r in self.contract['requirements']}:
            raise SynthesisError('unknown Requirement')
        ids = args['evidence_ids']
        if not isinstance(ids, list) or not ids or any(type(e) is not str or e not in self.evidence for e in ids):
            raise SynthesisError('known evidence IDs required')
        if not any(self.evidence[e]['task_version'] == digest for e in ids):
            raise SynthesisError('hypothesis needs evidence for current candidate version')
        row = {**copy.deepcopy(args), 'id': f'hypothesis-{len(self.hypotheses) + 1:04d}',
               'task_version': digest, 'status': 'provisional'}
        self.save('self-check/' + row['id'] + '.json', row)
        self.hypotheses.append(row)
        return row

    def summary(self):
        return {'schema_version': 1, 'checks': self.checks, 'attempts': self.attempts,
                'hypotheses': self.hypotheses,
                'protected_solution_version': self.protected['digest'] if self.protected else None,
                'provenance': provenance(), 'config': self.config.public(), **run_identity(self.root),
                'network_mode': {'self_check': 'none', 'investigation': 'none'},
                'independent_validation': False}
