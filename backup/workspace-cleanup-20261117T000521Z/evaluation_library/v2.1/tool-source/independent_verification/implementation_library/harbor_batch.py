"""One native Harbor dataset job, with strict per-task identity and image evidence."""
import json
import os
from pathlib import Path
import subprocess
import threading

from independent_verification.harbor import parse_result
from .library import read,write_json,hashes


class BatchImages:
    def __init__(self,job,tasks):
        self.job=Path(job); self.tasks={str(Path(p).resolve()):label for label,p in tasks.items()}
        self.roles={label:{} for label in tasks}; self.errors=[]; self.done=threading.Event()
        self.thread=threading.Thread(target=self.watch,daemon=True)

    def start(self): self.thread.start()

    def stop(self):
        self.done.set(); self.thread.join(timeout=25)
        if self.thread.is_alive(): raise RuntimeError('batch image observer did not stop')

    def watch(self):
        env={k:v for k,v in os.environ.items() if k in {'PATH','HOME','DOCKER_HOST','DOCKER_CONTEXT','DOCKER_CONFIG','DOCKER_TLS_VERIFY','DOCKER_CERT_PATH','XDG_RUNTIME_DIR'}}
        while not self.done.is_set():
            try:
                prefixes={}
                for config in self.job.glob('*/config.json'):
                    task=str(Path(read(config)['task']['path']).resolve())
                    if task in self.tasks:
                        label=self.tasks[task]
                        if set(self.roles[label])!={'task','verifier'}: prefixes[config.parent.name.lower()+'__']=label
                if prefixes:
                    proc=subprocess.run(['docker','ps','-a','--filter','label=com.docker.compose.project','--filter','label=com.docker.compose.service=main','--format','{{.ID}} {{.Names}}'],capture_output=True,text=True,timeout=10,env=env,check=True)
                    for line in proc.stdout.splitlines():
                        ident,name=line.split(maxsplit=1)
                        labels=[label for prefix,label in prefixes.items() if name.lower().startswith(prefix)]
                        if len(labels)!=1: continue
                        label=labels[0]; role='verifier' if '__verifier' in name.lower() else 'task'
                        if role in self.roles[label]: continue
                        inspected=subprocess.run(['docker','inspect','--format','[{{json .Name}},{{json .Image}},{{json .Config.Image}}]',ident],capture_output=True,text=True,timeout=10,env=env)
                        if inspected.returncode==0:
                            actual,image_id,reference=json.loads(inspected.stdout)
                            self.roles[label][role]={'container':actual.lstrip('/'),'id':image_id,'reference':reference}
                if all(set(v)=={'task','verifier'} for v in self.roles.values()): return
            except Exception as exc:
                self.errors.append(type(exc).__name__+': '+str(exc)[:200])
            self.done.wait(0.5)

    def results(self):
        return {label:{'status':'recorded' if set(roles)=={'task','verifier'} else 'partial' if roles else 'unavailable','roles':roles,'observation_errors':self.errors[:5]} for label,roles in self.roles.items()}


def run_batch(harbor,tasks,root,nodeids,config,concurrency=3):
    if not tasks or type(concurrency)!=int or not 1<=concurrency<=3: raise ValueError('invalid Harbor batch')
    root=Path(root).absolute(); parent={Path(p).absolute().parent for p in tasks.values()}
    if len(parent)!=1: raise ValueError('batch tasks must share one dataset directory')
    dataset=next(iter(parent))
    if {p.resolve() for p in dataset.iterdir() if p.is_dir()}!={Path(p).resolve() for p in tasks.values()}: raise ValueError('dataset contains unrequested task directories')
    before={label:hashes(p) for label,p in tasks.items()}
    job=root/'jobs/panel'; watcher=BatchImages(job,tasks); watcher.start()
    try:
        process=harbor.cli(['run','-p',str(dataset),'-a','oracle','-k','1','-r','0','-n',str(concurrency),'--env','docker','-o',str(root/'jobs'),'--job-name','panel'],root,root/'harbor-panel',timeout=1800)
    finally:
        watcher.stop()
    images=watcher.results(); write_json(root/'harbor-images.json',images)
    found={label:[] for label in tasks}; unexpected=[]
    task_labels={str(Path(p).resolve()):label for label,p in tasks.items()}
    for path in job.glob('*/result.json'):
        native=read(path); task=str(Path(native['config']['task']['path']).resolve())
        if task in task_labels: found[task_labels[task]].append(path.parent.name)
        else: unexpected.append(str(path))
    if unexpected: raise ValueError('unexpected tasks in Harbor job')
    rows=[]
    for label,task in tasks.items():
        if len(found[label])!=1:
            trial={'status':'error','reward':None,'error':{'type':'BATCH_MATRIX','message':'Expected exactly one native trial, got '+str(len(found[label]))}}
        else:
            trial=parse_result(job,Path(task).absolute(),'oracle',harbor.version,process,nodeids,trial_name=found[label][0])
        if hashes(task)!=before[label]: raise ValueError('frozen Harbor task changed')
        rows.append({'label':label,**trial,'images':images[label],'images_path':str(root/'harbor-images.json')})
    write_json(root/'harbor-trials.json',rows)
    return rows
