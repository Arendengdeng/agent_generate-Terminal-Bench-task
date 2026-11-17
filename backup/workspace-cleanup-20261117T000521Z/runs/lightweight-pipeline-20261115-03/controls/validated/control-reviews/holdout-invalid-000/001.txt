import csv,json,subprocess,tempfile
from pathlib import Path

def test_independent_control_audit():
    for data,expected in [([{'email': ' z@EXAMPLE.com ', 'name': ' First, 姓名 '}, {'email': 'a@example.com', 'name': ' A "quoted" '}, {'email': 'Z@example.com', 'name': ' Last '}], [{'email': 'z@example.com', 'name': 'First, 姓名'}, {'email': 'a@example.com', 'name': 'A "quoted"'}]), ([], [])]:
        with tempfile.TemporaryDirectory() as work:
            t=Path(work)
            source=t/'input.csv'; target=t/'output.csv'
            with source.open('w',encoding='utf-8',newline='') as f:
                w=csv.DictWriter(f,fieldnames=['email','name']); w.writeheader(); w.writerows(data)
            before=source.read_bytes()
            p=subprocess.run(['python3','/app/clean.py',str(source),str(target)],capture_output=True,timeout=10)
            assert p.returncode==0
            with target.open(encoding='utf-8',newline='') as f:
                reader=csv.DictReader(f); assert reader.fieldnames==['email','name']; actual=list(reader)
            assert actual==expected
            assert source.read_bytes()==before
