"""Meaningful integrity, semantic and scoring regressions; no mock claims of live audits."""
import base64
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from independent_verification.implementation_library import library,scoring,witnesses,recipes


class SemanticTests(unittest.TestCase):
    def observation(self,output,before=None,after=None,exit_code=0):
        return {'status':'completed','exit_code':exit_code,'output_b64':base64.b64encode(output).decode(),'before':before or {},'after':after or {}}

    def test_csv_equivalent_line_endings_and_multiline_quotes(self):
        c={'expected':[['a@b','name, "quoted"\nline']]}
        for ending in ('\n','\r\n'):
            raw=('email,name'+ending+'a@b,"name, ""quoted""\nline"'+ending).encode()
            self.assertTrue(all(witnesses.checks('csv','original',c,self.observation(raw)).values()))

    def test_json_equivalent_formatting_and_large_integer(self):
        expected=[{'service':'文','level':'INFO','count':2,'total_duration_ms':2**80+1}]
        for indent in (None,2):
            raw=json.dumps(expected,indent=indent,ensure_ascii=indent is None).encode()
            self.assertTrue(all(witnesses.checks('jsonl','original',{'expected':expected},self.observation(raw)).values()))

    def test_bool_is_not_integer_and_extra_fields_are_rejected(self):
        good={'service':'a','level':'INFO','count':1,'total_duration_ms':1}
        for bad in ({**good,'count':True},{**good,'extra':0}):
            checks=witnesses.checks('jsonl','original',{'expected':[good]},self.observation(json.dumps([bad]).encode()))
            self.assertFalse(checks['R1'])

    def test_input_damage_is_detected_with_correct_output(self):
        c={'expected':[]}; observed=self.observation(b'[]',{'input':'before'},{'input':'after'})
        self.assertEqual(witnesses.checks('jsonl','original',c,observed),{'R1':True,'R2':True,'R3':True,'R4':False})

    def test_csv_fixtures_exercise_encoding_under_both_retention_policies(self):
        for variant in ('original','variant'):
            expected=[rows for data,rows in scoring.fixture_cases('csv',variant)]
            corrupted=[[[k,v.encode('ascii','replace').decode()] for k,v in rows] for rows in expected]
            self.assertNotEqual(expected,corrupted)

    def test_parser_limits_are_exercised_in_current_witness_protocol(self):
        csv_cases=witnesses.cases('csv','original')
        large=next(c for c in csv_cases if c['id']=='field-over-131072-bytes')
        self.assertEqual(len(large['data'][0]['name']),200000)
        raw=b'email,name\nlarge@example.com,'+b'x'*200000+b'\n'
        self.assertTrue(all(witnesses.checks('csv','original',large,self.observation(raw)).values()))
        json_cases=witnesses.cases('jsonl','variant')
        huge=next(c for c in json_cases if c['id']=='decimal-over-4300-digits')
        self.assertEqual(huge['expected'][0]['total_duration_ms'],10**5000+3)
        roots=witnesses.cases('manifest','original')
        self.assertTrue(any(c.get('input_name')=='input [literal]?*' for c in roots))

    def test_manifest_grouping_checks_membership_beyond_path_coverage(self):
        case={'expected':[{'sha256':hashlib.sha256(b'a').hexdigest(),'size':1,'paths':['a']},
                          {'sha256':hashlib.sha256(b'b').hexdigest(),'size':1,'paths':['b']}]}
        wrong=[{'sha256':'0'*64,'size':1,'paths':['a','b']}]
        observed=self.observation(json.dumps(wrong).encode())
        checked=witnesses.checks('manifest','variant',case,observed)
        self.assertTrue(checked['R1']); self.assertFalse(checked['R2']); self.assertFalse(checked['R3'])
        self.assertTrue(witnesses.checks('manifest','variant',case,observed,protocol=3)['R2'])

    def test_manifest_anchors_and_domain_boundaries(self):
        all_cases=witnesses.cases('manifest','variant')
        anchor=next(c for c in all_cases if c['id']=='digest-anchors')
        self.assertEqual({r['sha256'] for r in anchor['expected']},{hashlib.sha256(b'').hexdigest(),hashlib.sha256(b'abc').hexdigest()})
        largest=next(c for c in all_cases if c['id']=='limit-1mib')
        self.assertEqual(len(base64.b64decode(largest['data']['large.bin'])),1048576)
        self.assertEqual(len(next(c for c in all_cases if c['id']=='limit-100-files')['data']),100)

    def test_missing_and_duplicate_observations_cannot_confirm(self):
        entry={'task_id':'csv-original'}
        for raw in ([],[{'id':'a'},{'id':'a'}]):
            with self.assertRaises(ValueError): library.classify_entry(entry,[{'id':'a'}],raw)

    def test_failed_expected_label_is_unresolved(self):
        e={'id':'x','family':'jsonl','variant':'original','task_id':'jsonl-original','role':'invalid','group':'holdout',
           'review':{'requirements':{'R1':{'expected':'violated','rationale':'deliberate fixture'}}}}
        result=library.classify_entry(e,[{'id':'a','expected':[]}],[{'id':'a',**self.observation(b'[]')}])
        self.assertEqual(result['confirmation'],'unresolved')

    def test_timeout_never_confirms_a_label(self):
        e={'id':'x','family':'jsonl','variant':'original','task_id':'jsonl-original','role':'invalid','group':'holdout',
           'review':{'requirements':{'R1':{'expected':'violated','rationale':'deliberate fixture'}}}}
        result=library.classify_entry(e,[{'id':'a','expected':[]}],[{'id':'a','status':'timeout','before':{},'after':{}}])
        self.assertEqual(result['confirmation'],'unresolved')


class IntegrityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory(); cls.root=Path(cls.temp.name)/'library'
        library.build(cls.root)

    @classmethod
    def tearDownClass(cls): cls.temp.cleanup()

    def test_build_has_84_distinct_reviewed_sources_and_fixed_splits(self):
        data=library.validate(self.root)
        self.assertEqual(len(data['entries']),84)
        self.assertEqual(sum(e['role']=='correct' for e in data['entries']),30)
        self.assertEqual(sum(e['origin']=='controlled-mutation' for e in data['entries']),54)
        self.assertTrue(all(e['review']['status']=='pending-execution' for e in data['entries']))

    def test_frozen_library_validation_does_not_depend_on_live_examples(self):
        with patch.object(library,'PROJECT',self.root/'unavailable-live-project'):
            self.assertEqual(len(library.validate(self.root)['entries']),84)

    def test_mutations_have_different_ast(self):
        for family in ('csv','jsonl','manifest'):
            for variant in ('original','variant'):
                for i,(defect,_,_) in enumerate(recipes.DEFECTS):
                    design=0 if i<5 else 2
                    good=recipes.program(family,variant,design); bad=recipes.mutate(good,family,variant,defect)
                    self.assertNotEqual(recipes.normalized_digest({'x.py':good}),recipes.normalized_digest({'x.py':bad}))

    def test_evidence_deletion_modification_and_addition_are_detected(self):
        for mode in ('delete','modify','add'):
            with tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp); (root/'record.json').write_text('{}'); library.seal(root)
                if mode=='delete': (root/'record.json').unlink()
                elif mode=='modify': (root/'record.json').write_text('{"changed":true}')
                else: (root/'new.json').write_text('{}')
                with self.assertRaises(ValueError): library.verify_seal(root)

    def test_validation_rejects_wrong_requirement_and_stale_digest(self):
        data=library.read(self.root/'library.json')
        for field,value in [('contract_digest','bad'),('source_digest','bad')]:
            changed=copy.deepcopy(data); changed['entries'][0][field]=value
            original=library.read
            def read(path):
                return changed if Path(path)==self.root/'library.json' else original(path)
            with patch.object(library,'read',side_effect=read):
                with self.assertRaises(ValueError): library.validate(self.root)

    def test_requirement_ids_and_lineage_are_validated(self):
        data=library.read(self.root/'library.json')
        for mode in ('requirement','duplicate','lineage'):
            changed=copy.deepcopy(data)
            if mode=='requirement':
                entry=changed['entries'][0]
                entry['review']['requirements']['R9']=entry['review']['requirements'].pop('R1')
            elif mode=='duplicate':
                changed['entries'][1]={**copy.deepcopy(changed['entries'][0]),'id':changed['entries'][1]['id']}
            else: changed['entries'][4]['group']='feedback'
            original=library.read
            def read(path):
                if Path(path)==self.root/'library.json': return changed
                if mode=='requirement' and Path(path)==(self.root/data['entries'][0]['source']).parent/'review.json': return changed['entries'][0]['review']
                return original(path)
            with patch.object(library,'read',side_effect=read):
                with self.assertRaises(ValueError): library.validate(self.root)

    def test_wrong_input_snapshot_is_not_a_semantic_witness(self):
        case=witnesses.cases('jsonl','original')[0]
        case['input_b64']=''
        entry={'family':'jsonl','variant':'original'}
        with self.assertRaisesRegex(ValueError,'observed input'):
            library.classify_entry(entry,[case],[{'id':case['id'],'before':{}}])

    def test_export_keeps_large_counterexample_outside_native_manifest(self):
        # Synthetic execution records exercise serialization only, never label evidence.
        data=library.validate(self.root)
        selected=[e for e in data['entries'] if e['task_id']=='csv-original']
        cases=library.read(self.root/'witnesses/csv-original.json')
        with tempfile.TemporaryDirectory() as tmp:
            audit=Path(tmp)/'audit'; eligible=[]
            for entry in selected:
                folder=audit/'implementations'/entry['id']; folder.mkdir(parents=True)
                case=next(c for c in cases if c['id']==('limit-1000' if entry['defect']=='limit' else 'retention-order-unicode'))
                raw=[{'id':case['id'],'argv':['python3','/app/clean.py','/tmp/input','/tmp/output'],'output_b64':'SYNTHETIC'}]
                library.write_json(folder/'observations.json',raw); library.write_json(folder/'execution.json',{'synthetic':True})
                eligible.append({'id':entry['id'],'confirmation':'confirmed','checks':[{'case':case['id'],'checks':{'R2':False}}]})
            out=Path(tmp)/'export'
            with patch.object(library,'report',return_value={'results':eligible}):
                library.export_panel(self.root,audit,'csv-original',out)
            from synthesis_agent.files import read_json
            manifest=read_json(out/'manifest.json')  # Native default size budget, no override.
            self.assertLess((out/'manifest.json').stat().st_size,256000)
            entry=next(e for e in manifest['controls'] if e['source'].endswith('invalid-limit'))
            path=out/entry['review']['counterexample']['fixture_path']
            self.assertEqual(len(library.read(path)['fixture']['data']),1000)
            self.assertIn(path.relative_to(out).as_posix(),entry['review']['evidence_paths'])
            self.assertNotIn('fixtures',entry['review']['counterexample'])

    def test_metrics_keep_errors_in_planned_denominator(self):
        rows=[{'role':'invalid','group':'holdout','outcome':o} for o in ('fail','pass','error','timeout','not_run')]
        groups=scoring.metrics(rows); row=next(g for g in groups if g['group']=='holdout' and g['role']=='invalid')
        self.assertEqual((row['planned'],row['normal_scores'],row['rejected'],row['missed']),(5,2,1,1))
        self.assertEqual((row['normal_success_rate'],row['planned_success_rate']),(0.5,0.2))


class BatchParserTests(unittest.TestCase):
    def test_selector_keeps_task_identity_and_rejects_path_escape(self):
        from independent_verification.harbor import parse_result,HARBOR_VERSION
        from independent_verification.wrapper import classify
        node='test_cli.py::test_output'
        phases=[{'nodeid':node,'when':stage,'outcome':'passed'} for stage in ('setup','call','teardown')]
        report=classify(0,[node],phases,[],[node])
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); tasks={}
            for label in ('one','two'):
                task=root/('task-'+label); tasks[label]=task
                trial=root/'job'/label; (trial/'verifier').mkdir(parents=True)
                native={'agent_info':{'name':'oracle'},'config':{'agent':{'name':'oracle'},'task':{'path':str(task)}},'finished_at':'SYNTHETIC',
                    'verifier_environment_mode':'separate','exception_info':None,'verifier_result':{'rewards':{'reward':1}}}
                (trial/'result.json').write_text(json.dumps(native)); (trial/'verifier/execution.json').write_text(json.dumps(report)); (trial/'verifier/reward.txt').write_text('1')
            process={'exit_code':0,'stdout_path':'SYNTHETIC','error':None}
            self.assertEqual(parse_result(root/'job',tasks['one'],'oracle',HARBOR_VERSION,process,[node])['status'],'error')
            self.assertEqual(parse_result(root/'job',tasks['one'],'oracle',HARBOR_VERSION,process,[node],trial_name='one')['status'],'completed')
            for selector in ('../one','one/../two','..','one\\two'):
                self.assertEqual(parse_result(root/'job',tasks['one'],'oracle',HARBOR_VERSION,process,[node],trial_name=selector)['status'],'error')
            self.assertEqual(parse_result(root/'job',tasks['two'],'oracle',HARBOR_VERSION,process,[node],trial_name='one')['status'],'error')


if __name__=='__main__': unittest.main()
