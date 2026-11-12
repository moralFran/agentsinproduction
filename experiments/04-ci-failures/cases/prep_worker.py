#!/usr/bin/env python3
"""Untrusted dependency/build stage, inside a per-case Kata pod. /input is read-only; no reference diffs are mounted.
Only broken-tree output is published to the agent's case directory. Fixed-tree Go output stays with the controller.
"""
import json, os, pathlib, shutil, subprocess

def main():
    m=json.loads(os.environ['TASK']); case=pathlib.Path('/srv/ci/cases')/os.environ['CASE_ID']; repo=case/'repo'
    subprocess.run(['rsync','-rl','--no-perms','--chmod=u+rwX','--omit-dir-times','/input/',str(repo)+'/'],check=True)
    wd=repo/m['workdir']
    def run(args, check=False):
        ok = subprocess.run(args,cwd=wd,check=check).returncode == 0
        if not ok: print('PREP_OPTIONAL_FAILED '+json.dumps(args),flush=True)
        return ok
    if m['language']=='Go':
        (case/'gomod').mkdir(exist_ok=True)
        run(['go','version'],True); run(['go','mod','download'])
        # Bulk download may include unused modules. On the maintainer's fixed tree the selected packages must still
        # compile/start. The broken tree may be red BECAUSE it does not compile: there the result is recorded and the
        # case goes on; freeze.py then asks for a reasoned decision (the commit's own error, or a missing module?).
        phase=os.environ.get('PREP_PHASE','fixed')
        compiled=run(['go','test','-count=1','-run','^$',*m['targets']],phase!='broken')
        print('PREP_COMPILE '+json.dumps({'phase':phase,'ok':compiled}),flush=True)
    else:
        venv=case/'venv'; run(['uv','venv','-q','--python',m['python'],str(venv)],True)
        pip=['uv','pip','install','-q','--python',str(venv/'bin/python')]
        reqs=[q for pattern in ('requirements.txt','requirements*dev*.txt','requirements*test*.txt','dev-requirements.txt',
              'test-requirements.txt','requirements/base*.txt','requirements/test*.txt','requirements/dev*.txt','tests/requirements*.txt') for q in wd.glob(pattern)]
        installed=[run(pip+['-r',str(q)]) for q in reqs]; ok=False
        if any((wd/f).exists() for f in ('pyproject.toml','setup.py','setup.cfg')):
            ok=run(pip+['-e','.[test,tests,testing,dev]']) or run(pip+['-e','.'])
            for group in ('test','tests','dev'): run(pip+['--group',group,'-e','.'])
        run(pip+['pytest'],True)
        if not ok and not any(installed): raise RuntimeError('project could not be installed')
    overlay=case/'overlay'; listed=[]
    for f in repo.rglob('*'):
        rel=f.relative_to(repo)
        if '.git' in rel.parts or f.is_dir() or (pathlib.Path('/input')/rel).exists(): continue
        (overlay/rel).parent.mkdir(parents=True,exist_ok=True); shutil.copy2(f,overlay/rel,follow_symlinks=False); listed.append(str(rel))
    (case/'overlay.list').write_text(''.join('/'+p+'\n' for p in sorted(listed)))
    print('PREP_WORKER_DONE',flush=True)

if __name__=='__main__': main()
