"""Verify bundle SHA-256 and every payload member without extracting files."""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import tarfile


def digest(stream):
    h=hashlib.sha256()
    for block in iter(lambda: stream.read(1024*1024),b''): h.update(block)
    return h.hexdigest()


def verify(path,expected_sha=None):
    path=Path(path)
    with path.open('rb') as stream: actual_sha=digest(stream)
    if expected_sha and actual_sha!=expected_sha: raise ValueError('archive digest mismatch: '+path.name)
    with tarfile.open(path,'r:gz') as archive:
        manifest=json.load(archive.extractfile('ARCHIVE-MANIFEST.json'))
        expected=manifest['files']; seen=set()
        for member in archive:
            p=PurePosixPath(member.name)
            if p.is_absolute() or '..' in p.parts or not member.isfile(): raise ValueError('unsafe member: '+member.name)
            if member.name=='ARCHIVE-MANIFEST.json': continue
            if member.name in seen or member.name not in expected: raise ValueError('unexpected or duplicate member: '+member.name)
            if digest(archive.extractfile(member))!=expected[member.name]: raise ValueError('member digest mismatch: '+member.name)
            seen.add(member.name)
        if seen!=set(expected): raise ValueError('archive is missing payload files')
    return {'archive':path.name,'sha256':actual_sha,'files':len(seen),'payload_bytes':manifest['payload_bytes']}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('archive',nargs='?')
    args=parser.parse_args()
    root=Path(__file__).resolve().parent
    if args.archive: results=[verify(Path(args.archive))]
    else:
        index=json.loads((root/'index.json').read_text())
        results=[verify(root/item['archive'],item['sha256']) for item in index['archives']]
    print(json.dumps(results,ensure_ascii=False,indent=2))


if __name__=='__main__': main()
