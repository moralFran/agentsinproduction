#!/usr/bin/env python3
"""Trusted host controller for preparation (post-collection hardening).
Only Git/file operations run here. Repository builds run in per-case Kata pods in ci-prep, with no secret directory,
other cases, host network, lab checkout or credentials. Broken and fixed dependency outputs are kept separate.
usage: prep.py '<candidate json line>'
"""
import hashlib, json, os, pathlib, re, shlex, shutil, subprocess, sys, time

ROOT = pathlib.Path('/srv/ci')
TESTFILE = re.compile(r'(^|/)(tests?|testdata|testing|__snapshots__|golden|fixtures)(/|$)|_test\.go$|(^|/)test_[^/]*\.py$|_test\.py$|(^|/)conftest\.py$|\.snap$|\.golden$')

def command(args, cwd=None):
    return subprocess.run([str(a) for a in args], cwd=cwd, check=True, capture_output=True, text=True, timeout=1200).stdout

def git(repo, *args):
    return command(['git', '-c', 'core.hooksPath=/dev/null', '-c', 'core.fsmonitor=false', *args], cwd=repo)

def snapshot(source, destination):
    for path in source.rglob('*'):
        if '.git' in path.relative_to(source).parts: continue
        if path.is_symlink() and not path.resolve().is_relative_to(source.resolve()):
            raise ValueError('source symlink escapes the checkout')
    command(['rsync', '-rl', '--exclude', '.git', str(source)+'/', str(destination)+'/'])
    git(destination, 'init', '-q'); git(destination, 'add', '-A')
    git(destination, '-c', 'user.name=snapshot', '-c', 'user.email=snapshot@example.invalid', 'commit', '-qm', 'snapshot')

def writable_directories(root):
    # Go marks module directories read-only. Pods have finished before this host-side operation;
    # never follow output symlinks when making a copied cache writable or removing worker scratch space.
    for directory, _, _ in os.walk(root, followlinks=False):
        path = pathlib.Path(directory)
        if not path.is_symlink(): path.chmod(path.stat().st_mode | 0o700)

def case_meta(c, cid, repo, hidden):
    meta = {k: c[k] for k in ('repo', 'language', 'broken_sha', 'workflow', 'failed_job')}
    meta['id'] = cid
    if c['language'] == 'Go':
        mods = {}
        for gm in sorted(repo.rglob('go.mod')):
            if 'vendor' in gm.parts or 'testdata' in gm.parts: continue
            m = re.search(r'^module\s+(\S+)', gm.read_text(), re.M)
            if m: mods[m.group(1)] = gm.parent.relative_to(repo)
        if not mods: raise ValueError('no go.mod')
        pkgs = c.get('go_pkgs', [])
        best = max((m for m in mods if any(p == m or p.startswith(m+'/') for p in pkgs)), key=len, default=None) if pkgs else min(mods, key=len)
        if best is None: raise ValueError('failing packages outside every module')
        wd = mods[best]; targets = [p for p in pkgs if p == best or p.startswith(best+'/')] if pkgs else ['./...']
        hidden_targets = set(targets)
        for h in hidden:
            d = (repo / h).parent
            while d != repo and not any(d.glob('*.go')): d = d.parent
            if d.is_relative_to(repo / wd): hidden_targets.add('./' + str(d.relative_to(repo / wd)))
        meta.update(workdir=str(wd), test_cmd='go test -count=1 ' + shlex.join(targets), targets=targets)
        hidden_cmd = 'go test -count=1 ' + shlex.join(sorted(hidden_targets)) if hidden else ''
    else:
        found = []
        for f in sorted({t.split('::')[0] for t in c['py_tests']}):
            p = repo / f
            if not pathlib.PurePosixPath(f).is_absolute() and '..' not in pathlib.PurePosixPath(f).parts and p.exists():
                found.append(f); continue
            parts = [x for x in pathlib.PurePosixPath(f).parts if x not in ('..', '.', '/')]
            candidates = [q for q in repo.rglob(parts[-1]) if '.git' not in q.parts] if parts else []
            for k in range(len(parts), 0, -1):
                hits = [q for q in candidates if q.relative_to(repo).parts[-k:] == tuple(parts[-k:])]
                if len(hits) == 1: found.append(str(hits[0].relative_to(repo))); break
                if len(hits) > 1: break
        if not found: raise ValueError('failing test files not found')
        def project(f):
            d = (repo/f).parent
            while d != repo and not any((d/m).exists() for m in ('pyproject.toml','setup.py','setup.cfg','requirements.txt')): d = d.parent
            return d
        project_dir = max(sorted({project(f) for f in found}), key=lambda d: sum(project(f) == d for f in found))
        rel = [str((repo/f).relative_to(project_dir)) for f in found if (repo/f).is_relative_to(project_dir)]
        hp = [str((repo/h).relative_to(project_dir)) for h in hidden if re.search(r'(^|/)test_[^/]*\.py$|_test\.py$', h) and (repo/h).is_relative_to(project_dir)]
        version = c.get('py_version') or '3.12'
        if version.count('.') == 2: version = version.rsplit('.', 1)[0]
        meta.update(workdir=str(project_dir.relative_to(repo)), python=version, test_cmd='python -m pytest -q -p no:cacheprovider ' + shlex.join(rel))
        hidden_cmd = 'python -m pytest -q -p no:cacheprovider ' + shlex.join(sorted(set(rel) | set(hp))) if hidden else ''
    return meta, hidden_cmd

def worker_spec(cid, name, source, output, meta, phase=None):
    """The only writable host directory is this worker's output. No parent of /srv/ci is mounted."""
    case = f'/srv/ci/cases/{cid}'
    env = {'HOME':'/tmp', 'CASE_ID':cid, 'TASK':json.dumps(meta), 'UV_PYTHON_INSTALL_DIR':'/srv/ci/uv/python',
           'UV_CACHE_DIR':'/tmp/uvcache', 'UV_LINK_MODE':'copy', 'GOMODCACHE':case+'/gomod', 'GOCACHE':'/tmp/gocache',
           'GOPATH':'/tmp/gopath', 'GOTOOLCHAIN':'auto', 'GOFLAGS':'-mod=mod', 'GOTELEMETRY':'off'}
    if phase: env['PREP_PHASE'] = phase   # "broken": a failed compile is recorded, not fatal (prep_worker.py)
    # Network gate (2026-11-13, cases/pod.py): no repository code starts before the policy is seen to refuse the metadata
    # endpoint, the node and the Kubernetes API. Public 80/443 stays allowed here, so it is not a canary.
    import importlib.util   # pod.py sits beside this file; loaded by path so it works whatever the caller's sys.path is
    _spec = importlib.util.spec_from_file_location('netgate_pod', pathlib.Path(__file__).resolve().parent/'pod.py')
    _pod = importlib.util.module_from_spec(_spec); _spec.loader.exec_module(_pod)
    security = {'allowPrivilegeEscalation':False,'capabilities':{'drop':['ALL']}}
    gate = [_pod.netgate_container('aip-ci-box:1', security, _pod.PRIVATE_CANARIES)] if _pod.netgate_enabled() else []
    return {'apiVersion':'v1', 'kind':'Pod', 'metadata':{'name':name,'namespace':'ci-prep'}, 'spec':{
        **({'initContainers':gate} if gate else {}),
        'runtimeClassName':'kata-qemu','automountServiceAccountToken':False,'enableServiceLinks':False,
        'restartPolicy':'Never','activeDeadlineSeconds':2400,
        'securityContext':{'runAsNonRoot':True,'runAsUser':os.getuid(),'runAsGroup':os.getgid(),'seccompProfile':{'type':'RuntimeDefault'}},
        'containers':[{'name':'c','image':'aip-ci-box:1','imagePullPolicy':'Never',
            'command':['python3','-u','/code/prep_worker.py'],'env':[{'name':k,'value':v} for k,v in env.items()],
            'securityContext':{'allowPrivilegeEscalation':False,'capabilities':{'drop':['ALL']}},
            'resources':{'requests':{'cpu':'2','memory':'4Gi'},'limits':{'cpu':'3','memory':'8Gi'}},
            'volumeMounts':[{'name':'source','mountPath':'/input','readOnly':True},
                           {'name':'output','mountPath':case}, {'name':'output','mountPath':'/srv/ci/uv','subPath':'uv'},
                           {'name':'tmp','mountPath':'/tmp'}, {'name':'code','mountPath':'/code','readOnly':True}]}],
        'volumes':[{'name':'source','hostPath':{'path':str(source),'type':'Directory'}},
                   {'name':'output','hostPath':{'path':str(output),'type':'Directory'}},
                   {'name':'tmp','emptyDir':{'sizeLimit':'8Gi'}}, {'name':'code','configMap':{'name':'ci-prep-code'}}]}}

def run_worker(cid, phase, source, output, meta, seed=None):
    if os.getuid() == 0: raise ValueError('run the preparation controller as the non-root lab user')
    output.mkdir(parents=True); (output/'uv').mkdir()
    if seed is not None:
        if seed.is_symlink(): raise ValueError('invalid module-cache root')
        shutil.copytree(seed, output/'gomod', symlinks=True)
        writable_directories(output/'gomod')
    name = f'prep-{cid[:44]}-{phase}'
    spec = worker_spec(cid,name,source,output,meta,phase)
    command(['kubectl','-n','ci-prep','delete','pod',name,'--ignore-not-found','--wait=true'])
    subprocess.run(['kubectl','apply','-f','-'],input=json.dumps(spec),text=True,check=True,capture_output=True)
    try:
        deadline = time.monotonic()+2520
        while time.monotonic() < deadline:
            phase_status = command(['kubectl','-n','ci-prep','get','pod',name,'-o','jsonpath={.status.phase}'])
            if phase_status in ('Succeeded','Failed'): break
            time.sleep(2)
        gate = subprocess.run(['kubectl','-n','ci-prep','logs',name,'-c','netgate'],capture_output=True,text=True).stdout if 'initContainers' in spec['spec'] else ''
        if '"ok": false' in gate: raise ValueError(f'{phase} preparation: infrastructure error, network gate: {gate[-300:]}')
        log = command(['kubectl','-n','ci-prep','logs',name])
        if phase_status != 'Succeeded': raise ValueError(f'{phase} preparation failed: {log[-300:]}')
        return log
    finally: command(['kubectl','-n','ci-prep','delete','pod',name,'--ignore-not-found','--wait=true'])

def compile_result(log):
    """The worker's last PREP_COMPILE line: True/False, or None when it printed none (not a Go case, or an old worker)."""
    for line in reversed((log or '').splitlines()):
        if line.startswith('PREP_COMPILE '):
            try: return json.loads(line[len('PREP_COMPILE '):]).get('ok') is True
            except (ValueError, AttributeError): return None
    return None

def publish(output, name, destination):
    source = output/name
    if not source.exists(): return
    if source.is_symlink(): raise ValueError(f'invalid output root: {name}')
    if source.is_dir(): shutil.copytree(source, destination, symlinks=True)
    else: shutil.copyfile(source, destination)

def prepare(c):
    if not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', c['repo']): raise ValueError('invalid repository')
    for field in ('broken_sha','fix_sha'):
        if not re.fullmatch(r'[0-9a-f]{40}', c[field]): raise ValueError('invalid commit')
    cid = re.sub(r'[^a-z0-9]+','-',c['repo'].lower()).strip('-')[:40]+'-'+c['broken_sha'][:8]
    case, secret, work = (ROOT/p/cid for p in ('cases','secret','work'))
    if any(p.exists() for p in (case,secret,work)): raise ValueError('case already exists; use reset-case.sh explicitly')
    for p in (case,secret,work): p.mkdir(parents=True)
    secret.chmod(0o700)
    clone = work/'control'
    command(['git','-c','core.hooksPath=/dev/null','clone','-q','--filter=blob:none',f"https://github.com/{c['repo']}.git",clone])
    git(clone,'checkout','-q',c['broken_sha'])
    diff = git(clone,'diff','--binary','--no-ext-diff','--no-textconv',c['broken_sha'],c['fix_sha'])
    hidden = [f for f in c['fix_files'] if TESTFILE.search(f)]
    (secret/'fix.diff').write_text(diff)
    (secret/'hidden.diff').write_text(git(clone,'diff','--binary','--no-ext-diff','--no-textconv',c['broken_sha'],c['fix_sha'],'--',*hidden) if hidden else '')
    (secret/'fix.json').write_text(json.dumps({'fix_sha':c['fix_sha'],'fix_files':c['fix_files'],'hidden_files':hidden}))
    snap = case/'snapshot'; snapshot(clone,snap)
    meta, hidden_cmd = case_meta(c,cid,snap,hidden)
    broken_output = work/'broken-output'
    broken_log = run_worker(cid,'broken',snap,broken_output,meta)
    if c['language'] == 'Go':
        # Says only whether the BROKEN tree's selected packages compiled; the agent can find that out by itself.
        meta['broken_compiles'] = compile_result(broken_log)
        git(clone,'checkout','-q',c['fix_sha']); fixed_source = work/'fixed-source'; snapshot(clone,fixed_source)
        fixed_output = work/'fixed-output'
        run_worker(cid,'fixed',fixed_source,fixed_output,meta,seed=broken_output/'gomod')
        publish(fixed_output,'gomod',secret/'gomod')
    for name in ('gomod','venv','overlay','overlay.list','uv'): publish(broken_output,name,case/name)
    (case/'repo').mkdir()  # mount point for the disposable working tree inside runtime pods
    (case/'meta.json').write_text(json.dumps(meta,indent=1))
    (secret/'meta.json').write_text(json.dumps({**meta,'hidden_cmd':hidden_cmd,'fix_sha':c['fix_sha'],'hidden_files':hidden},indent=1))
    # Keep worker directories for diagnosis on failures; successful preparation no longer needs the full-history clone.
    writable_directories(work)
    shutil.rmtree(work)
    return {'id':cid,'prep':'ok','test_cmd':meta['test_cmd'],'hidden_cmd':hidden_cmd,
            **({'broken_compiles':meta['broken_compiles']} if 'broken_compiles' in meta else {})}

def main():
    if pathlib.Path('ARCHIVE').exists() and os.environ.get('ALLOW_ARCHIVE_WRITE') != '1': sys.exit('historical record: start a fresh run')
    c = json.loads(sys.argv[1])
    cid = re.sub(r'[^a-z0-9]+','-',c['repo'].lower()).strip('-')[:40]+'-'+c['broken_sha'][:8]
    try: result = prepare(c)
    except (ValueError,OSError,subprocess.SubprocessError) as e: result = {'id':cid,'prep':'fail','why':str(e)[-500:]}
    print(json.dumps(result),flush=True)

if __name__ == '__main__': main()
