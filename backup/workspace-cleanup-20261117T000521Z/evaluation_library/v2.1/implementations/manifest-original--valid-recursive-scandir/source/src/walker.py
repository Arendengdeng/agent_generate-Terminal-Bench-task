import os
from pathlib import Path

def enumerate_files(root):
    files=[]
    def visit(folder):
        with os.scandir(folder) as entries:
            for e in entries:
                if e.is_dir(): visit(e.path)
                else: files.append(Path(e.path))
    visit(root)
    return files
