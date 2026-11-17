import csv,json,subprocess,tempfile
from pathlib import Path

def test_independent_control_audit():
    for data,expected in [([{'service': '服务', 'level': 'WARN', 'duration_ms': 0}, {'service': 'api', 'level': 'INFO', 'duration_ms': 3}, {'service': 'api', 'level': 'INFO', 'duration_ms': 7}, {'service': 'api', 'level': 'ERROR', 'duration_ms': 2}], [{'service': 'api', 'level': 'ERROR', 'count': 1, 'total_duration_ms': 2}, {'service': 'api', 'level': 'INFO', 'count': 2, 'total_duration_ms': 10}, {'service': '服务', 'level': 'WARN', 'count': 1, 'total_duration_ms': 0}]), ([], [])]:
        with tempfile.TemporaryDirectory() as work:
            t=Path(work)
            source=t/'input.jsonl'; target=t/'output.json'
            source.write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in data),encoding='utf-8')
            before=source.read_bytes()
            p=subprocess.run(['python3','/app/summarize.py',str(source),str(target)],capture_output=True,timeout=10)
            assert p.returncode==0
            assert json.loads(target.read_text(encoding='utf-8'))==expected
            assert source.read_bytes()==before
