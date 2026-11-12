#!/usr/bin/env python3
"""Post-collection security/regression controls. Synthetic repositories and temporary files only; no provider or cluster.
Manifest checks establish mount contracts, not proof of isolation on a live Kata node. Run: python3 -B infra/test_security.py
"""
import contextlib, csv, email.message, hashlib, importlib.util, io, json, os, pathlib, shlex, shutil, subprocess, sys, tempfile, types, unittest, warnings
from unittest.mock import patch
R=pathlib.Path(__file__).resolve().parents[1]
def module(name,path):
    spec=importlib.util.spec_from_file_location(name,R/path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
ex=module('security_executor','executor/executor.py');pods=module('security_pods','cases/pod.py')
val=module('security_validate','cases/validate.py');prep=module('security_prep','cases/prep.py')
tally=module('security_tally','results/analyze.py');judge=module('security_judge','judge/server.py');rounds=module('security_rounds','cases/check-round.py')

class Contracts(unittest.TestCase):
    def test_validation_and_agent_mounts_have_no_reference_fix(self):
        for language in ('Go','Python'):
            for role,action in [('agent',[]),('exec',['validate','suite']),('exec',['validate','hidden']),('exec',['repro','fixed','3']),
                                ('exec',['repro','fixed-agent-cache','3'])]:
                with self.subTest(language=language,role=role,action=action):
                    cmd=['python3','/code/agent.py'] if role=='agent' else ['python3','-u','/code/executor.py',*action]
                    spec=pods.build_spec(role,'fixture','pod',900,cmd,{'language':language},secret_meta={'hidden_cmd':'hidden-test','fix_sha':'DO_NOT_EXPOSE'})
                    mounts=spec['spec']['containers'][0]['volumeMounts']; paths={m['mountPath'] for m in mounts}
                    self.assertEqual(any(v['name']=='fixed-gomod' for v in spec['spec']['volumes']),
                                     language=='Go' and action[:2]==['repro','fixed'])
                    self.assertNotIn('/in/secret',paths);self.assertNotIn('DO_NOT_EXPOSE',json.dumps(spec))
                    fix_control=action[:2] in (['repro','fixed'],['repro','fixed-agent-cache'])
                    self.assertEqual('/in/fix.diff' in paths,fix_control)
                    self.assertEqual('/in/hidden.diff' in paths,fix_control)
                    if action[:1]==['validate']:
                        self.assertFalse(any(p.startswith('/in/') for p in paths))
                        init=spec['spec']['initContainers'][0]
                        init_paths={m['mountPath'] for m in init['volumeMounts']}
                        self.assertEqual('/in/hidden.diff' in init_paths,action==['validate','hidden'])
                        self.assertIn('validate-prepare',init['command'])
                        self.assertIn('validate-run',spec['spec']['containers'][0]['command'])
                    if role=='agent' or action==['validate','suite']:
                        self.assertNotIn('/srv/ci/secret',json.dumps(spec))
                    self.assertEqual(spec['spec']['securityContext']['seccompProfile']['type'],'RuntimeDefault')
                    self.assertFalse(spec['spec']['automountServiceAccountToken'])
    def test_preparation_can_only_write_its_own_output(self):
        for phase in ('broken','fixed'):
            spec=prep.worker_spec('fixture','worker',f'/work/fixture/{phase}-source',f'/work/fixture/{phase}-output',{'language':'Go'})['spec']
            paths={v['name']:v['hostPath']['path'] for v in spec['volumes'] if 'hostPath' in v}
            self.assertEqual(paths,{'source':f'/work/fixture/{phase}-source','output':f'/work/fixture/{phase}-output'})
            for mount in spec['containers'][0]['volumeMounts']:
                if mount['name']=='source':self.assertTrue(mount['readOnly'])
            self.assertEqual(spec['runtimeClassName'],'kata-qemu');self.assertFalse(spec.get('hostNetwork',False))
            self.assertNotIn('/srv/ci/secret',json.dumps(spec));self.assertNotIn('/lab',json.dumps(spec))
    def test_all_pytest_config_names_are_forbidden(self):
        for name in ('pytest.ini','.pytest.ini','pytest.toml','.pytest.toml'):
            self.assertEqual(ex.bad_paths([name]),[name])
    def test_hidden_sampling_and_flakiness(self):
        for results,expected in [([0,0,0],'green_passes_hidden'),([1,1,1],'green_fails_hidden'),([0,1,0],'hidden_tests_flaky')]:
            names=[];hidden=iter(results)
            def run(cid,patch,name,phase):
                names.append((name,phase));rc=next(hidden) if phase=='hidden' else 0
                return {'outcome':'sampled','files':['core.py'],'run':{'rc':rc}}, {'phase':'Succeeded/'}
            result=val.validate_case('fixture','patch','x'*80,True,run)
            self.assertEqual(result['outcome'],expected);self.assertEqual(len(names),6)
            self.assertEqual(len({n for n,p in names}),6);self.assertTrue(all(len(n)<=63 for n,p in names))
            self.assertEqual([p for n,p in names],['suite']*3+['hidden']*3)
    def test_suite_failure_does_not_run_hidden_tests(self):
        phases=[]
        def run(cid,patch,name,phase):
            phases.append(phase);return {'outcome':'sampled','run':{'rc':1}},{'phase':'Succeeded/'}
        self.assertEqual(val.validate_case('case','patch','name',True,run)['outcome'],'ci_still_red')
        self.assertEqual(phases,['suite']*3)
    def test_missing_executor_result_is_infrastructure_error(self):
        self.assertEqual(val.validate_case('case','patch','name',True,lambda *a:({},{}))['outcome'],'infra_error')
    def test_last_result_wins(self):
        self.assertEqual(val.last_record('RESULT {"value": 1}\nRESULT {"value": 2}\n','RESULT '),{'value':2})
    def test_no_blind_key_needed_for_non_green_outcomes(self):
        for outcome in ('ci_still_red','did_not_apply','rejected_by_validator','test_changed_tree','ci_flaky_after_patch','hidden_tests_did_not_apply','hidden_tests_flaky','infra_error','timeout',None):
            self.assertIsInstance(tally.final({'executor':{'outcome':outcome},'agent':{}},{},{}),str)
        expected={'finished':'desistiu','timeout':'parou por tempo','max_tool_calls':'parou por limite de ferramentas','error':'erro do agente','budget_exhausted':'parou por orçamento','gateway_unavailable':'erro de infraestrutura'}
        for outcome,label in expected.items():
            self.assertEqual(tally.final({'executor':{'outcome':'no_patch'},'agent':{'outcome':outcome}},{},{}),label)
        self.assertIsNone(tally.spent({'gateway':{'spent_usd':None}}))
    def test_incomplete_or_duplicate_round_fails(self):
        cases=[{'case_id':'case'}];rows=[{'run':f'run{i}','round':'v1','case':'case','rep':i} for i in (1,2,3)]
        self.assertEqual(rounds.check('v1',cases,rows),3)
        for bad in (rows[:2],rows+[rows[0]],[dict(row,run='same') for row in rows]):
            with self.assertRaises(ValueError):rounds.check('v1',cases,bad)

class RuntimeControls(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix='ci-security-');self.addCleanup(self.tmp.cleanup);self.root=pathlib.Path(self.tmp.name)
        self.repo=self.root/'repo';self.repo.mkdir();(self.repo/'core.py').write_text('value = 0\n')
        for args in [('init','-q'),('add','.'),('-c','user.name=test','-c','user.email=test@example.invalid','commit','-qm','base')]:
            subprocess.run(['git',*args],cwd=self.repo,check=True,capture_output=True)
    def test_second_edit_of_already_modified_source_is_detected(self):
        (self.repo/'core.py').write_text('value = 1\n')
        command=f'{sys.executable} -B -c '+__import__('shlex').quote("open('core.py','w').write('value = 2\\n')")
        result=ex.checked_run(command,str(self.repo),str(self.repo))
        self.assertEqual(result['outcome'],'test_changed_tree');self.assertIn('core.py',result['why'])
    def test_git_metadata_changes_are_detected_without_running_modified_git_config(self):
        marker=self.root/'monitor-ran';hook=self.root/'monitor.sh'
        hook.write_text('#!/bin/sh\ntouch '+shlex.quote(str(marker))+'\n');hook.chmod(0o755)
        mutations={
            '.git/config':f"with open('.git/config','a') as f: f.write({('[core]'+chr(10)+'fsmonitor = '+str(hook)+chr(10))!r})",
            '.git/info/exclude':"with open('.git/info/exclude','a') as f: f.write('hidden.txt\\n')\nPath('hidden.txt').write_text('hidden output')",
            '.git/index':"Path('.git/index').write_bytes(b'invalid index')\nPath('core.py').write_text('value = 2\\n')",
            '.git/HEAD':"Path('.git/HEAD').write_text('invalid head\\n')",
            '.git':"import shutil\nshutil.rmtree('.git')\nPath('.git').write_text('gitdir: nowhere\\n')"}
        for i,(name,body) in enumerate(mutations.items()):
            with self.subTest(metadata=name):
                repo=self.root/f'tamper-{i}';shutil.copytree(self.repo,repo)
                script=self.root/f'tamper-{i}.py';script.write_text('from pathlib import Path\n'+body+'\n')
                result=ex.checked_run(shlex.join([sys.executable,'-B',str(script)]),str(repo),str(repo))
                self.assertEqual(result['outcome'],'test_changed_tree',result);self.assertIn(name,result['why'])
                self.assertFalse(marker.exists())
                if name=='.git/index':self.assertIn('core.py',result['why'])
    def test_integrity_retains_before_file_list_when_ignore_rules_change(self):
        report=self.repo/'report.txt';report.write_text('original')
        before=ex.tree_state(str(self.repo))
        (self.repo/'.gitignore').write_text('report.txt\n');report.write_text('changed')
        after=ex.tree_state(str(self.repo),baseline=before)
        self.assertIn('report.txt',after[1]);self.assertNotEqual(before[1]['report.txt'],after[1]['report.txt'])
    def test_checker_disables_fsmonitor_inherited_config_and_index_refresh(self):
        marker=self.root/'monitor-ran';hook=self.root/'monitor.sh'
        hook.write_text('#!/bin/sh\ntouch '+shlex.quote(str(marker))+'\n');hook.chmod(0o755)
        config='[core]\nfsmonitor = '+str(hook)+'\n'
        with (self.repo/'.git/config').open('a') as f:f.write(config)
        external=self.root/'gitconfig';external.write_text(config)
        index=(self.repo/'.git/index').read_bytes()
        inherited={'GIT_CONFIG_SYSTEM':str(external),'GIT_CONFIG_GLOBAL':str(external),
                   'GIT_CONFIG_COUNT':'1','GIT_CONFIG_KEY_0':'core.fsmonitor','GIT_CONFIG_VALUE_0':str(hook)}
        with patch.dict(os.environ,inherited):result=ex.checked_run('true',str(self.repo),str(self.repo))
        self.assertEqual(result['outcome'],'sampled',result);self.assertFalse(marker.exists())
        self.assertEqual((self.repo/'.git/index').read_bytes(),index)
    def test_suite_that_only_queries_git_is_not_reported_as_a_tree_change(self):
        # A copied checkout carries stale stat data in its index, so a plain Git query by the suite rewrites .git/index.
        # The checker refreshes the index before its baseline; without that, these read-only queries look like tampering.
        for i,query in enumerate(('git status','git describe --dirty --always','git diff --quiet')):
            with self.subTest(query=query):
                repo=self.root/f'query-{i}'
                subprocess.run(['rsync','-rl','--no-perms','--chmod=u+rwX','--omit-dir-times',str(self.repo)+'/',str(repo)+'/'],check=True)
                result=ex.checked_run(query+' >/dev/null',str(repo),str(repo))
                self.assertEqual(result['outcome'],'sampled',result)
                command=f'{sys.executable} -B -c '+shlex.quote("open('core.py','w').write('value = 2\\n')")
                result=ex.checked_run('git status >/dev/null && '+command,str(repo),str(repo))
                self.assertEqual(result['outcome'],'test_changed_tree',result);self.assertIn('core.py',result['why'])
    def test_ignore_file_in_home_cannot_hide_new_files(self):
        # Pods run with a writable HOME; Git reads $HOME/.config/git/ignore even when the global config is disabled.
        home=self.root/'home';home.mkdir()
        script=self.root/'hide.py';script.write_text('import os\nfrom pathlib import Path\n'
            "ignore=Path(os.environ['HOME'])/'.config/git/ignore';ignore.parent.mkdir(parents=True)\n"
            "ignore.write_text('*\\n');Path('leak.txt').write_text('new output')\n")
        env={k:v for k,v in os.environ.items() if k!='XDG_CONFIG_HOME'};env['HOME']=str(home)
        with patch.dict(os.environ,env,clear=True):
            result=ex.checked_run(shlex.join([sys.executable,'-B',str(script)]),str(self.repo),str(self.repo))
        self.assertTrue((home/'.config/git/ignore').exists())
        self.assertEqual(result['outcome'],'test_changed_tree',result);self.assertIn('leak.txt',result['why'])
    def test_new_gitignore_cannot_hide_new_files(self):
        # new/.gitignore with "*" hides new/ (itself included) from Git's listing; the checker finds ignore files on disk.
        script=self.root/'hide.py';script.write_text('from pathlib import Path\nPath("new/deep").mkdir(parents=True)\n'
            'Path("new/.gitignore").write_text("*\\n");Path("new/deep/output.txt").write_text("hidden output")\n')
        listed=subprocess.run(['git','status','--porcelain','--untracked-files=all'],cwd=self.repo,capture_output=True,text=True).stdout
        result=ex.checked_run(shlex.join([sys.executable,'-B',str(script)]),str(self.repo),str(self.repo))
        self.assertEqual(listed,'')
        after=subprocess.run(['git','status','--porcelain','--untracked-files=all'],cwd=self.repo,capture_output=True,text=True).stdout
        self.assertEqual(after,'')  # Git itself still shows nothing
        self.assertEqual(result['outcome'],'test_changed_tree',result);self.assertIn('new/.gitignore',result['why'])
        # An ignore file that was already there and does not change is not a finding; editing it is.
        result=ex.checked_run('true',str(self.repo),str(self.repo));self.assertEqual(result['outcome'],'sampled',result)
        edit=shlex.join([sys.executable,'-B','-c','open("new/.gitignore","a").write("# edited\\n")'])
        result=ex.checked_run(edit,str(self.repo),str(self.repo))
        self.assertEqual(result['outcome'],'test_changed_tree',result);self.assertIn('new/.gitignore',result['why'])
    def test_checker_works_when_the_checkout_belongs_to_another_user(self):
        # In the pods the working copy is a root-owned emptyDir and the tests run as uid 1000. The image allowed that in
        # the system Git config, which the checker disables; found on the cluster (2026-11-12), invisible locally.
        real=subprocess.run
        def other_owner(args,**kwargs):
            if isinstance(args,list) and args[:1]==['git'] and 'env' in kwargs:
                kwargs['env']={**kwargs['env'],'GIT_TEST_ASSUME_DIFFERENT_OWNER':'1'}  # Git's own switch for this situation
            return real(args,**kwargs)
        refused=real(['git','status','--porcelain'],cwd=self.repo,capture_output=True,text=True,
                     env={**os.environ,'GIT_TEST_ASSUME_DIFFERENT_OWNER':'1','GIT_CONFIG_GLOBAL':'/dev/null','GIT_CONFIG_NOSYSTEM':'1'})
        self.assertIn('dubious ownership',refused.stderr)  # the situation is real on this Git
        with patch.object(ex.subprocess,'run',side_effect=other_owner):
            clean=ex.checked_run('true',str(self.repo),str(self.repo))
            edit=shlex.join([sys.executable,'-B','-c','open("core.py","w").write("value = 5\\n")'])
            changed=ex.checked_run(edit,str(self.repo),str(self.repo))
        self.assertEqual(clean['outcome'],'sampled',clean)
        self.assertEqual(changed['outcome'],'test_changed_tree',changed);self.assertIn('core.py',changed['why'])
    def test_negative_control_early_exit_is_still_a_semantic_review_requirement(self):
        # Deliberately demonstrate the limit: no path rule proves that the test assertion actually ran.
        (self.repo/'core.py').write_text('import os\nos._exit(0)\n')
        (self.repo/'check.py').write_text('import core\nassert False, "this assertion must fail"\n')
        result=ex.checked_run(f'{sys.executable} -B check.py',str(self.repo),str(self.repo))
        self.assertEqual(result['outcome'],'sampled');self.assertEqual(result['run']['rc'],0)
    def test_executor_entry_point_aborts_without_a_reference_mount(self):
        case=self.root/'ci/cases/fixture';case.mkdir(parents=True);shutil.copytree(self.repo,case/'snapshot');(case/'repo').mkdir()
        (case/'meta.json').write_text(json.dumps({'id':'fixture','test_cmd':f'{sys.executable} -B core.py'}))
        inputs=self.root/'in';inputs.mkdir();(inputs/'patch.diff').write_text('invalid patch\n')
        script=self.root/'executor.py';script.write_text((R/'executor/executor.py').read_text().replace('/srv/ci',str(self.root/'ci')).replace('/in/',str(inputs)+'/'))
        run=subprocess.run([sys.executable,'-B',str(script),'validate','suite'],env={**os.environ,'CASE_ID':'fixture'},capture_output=True,text=True)
        self.assertEqual(run.returncode,0,run.stderr)
        record=val.last_record(run.stdout,'EXECUTOR ');self.assertEqual(record['outcome'],'rejected_by_validator')
        self.assertFalse((inputs/'fix.diff').exists());self.assertFalse((inputs/'secret').exists())
    def test_full_validation_runs_six_fresh_executor_processes(self):
        (self.repo/'check.py').write_text('import core\nassert core.value == 1\n')
        subprocess.run(['git','add','.'],cwd=self.repo,check=True,capture_output=True)
        subprocess.run(['git','-c','user.name=test','-c','user.email=test@example.invalid','commit','-qm','check'],cwd=self.repo,check=True,capture_output=True)
        (self.repo/'core.py').write_text('value = 1\n')
        diff=subprocess.run(['git','diff','--binary'],cwd=self.repo,check=True,capture_output=True,text=True).stdout
        (self.repo/'core.py').write_text('value = 0\n')
        hidden='diff --git a/hidden_check.py b/hidden_check.py\nnew file mode 100644\n--- /dev/null\n+++ b/hidden_check.py\n@@ -0,0 +1,2 @@\n+import core\n+assert core.value == 1\n'
        locations=[]
        def runner(cid,patch_file,name,phase):
            base=self.root/name;locations.append(base)
            case=base/'ci/cases/fixture';case.mkdir(parents=True);shutil.copytree(self.repo,case/'snapshot');(case/'repo').mkdir()
            (case/'meta.json').write_text(json.dumps({'id':'fixture','test_cmd':f'{sys.executable} -B check.py'}))
            inputs=base/'in';inputs.mkdir();(inputs/'patch.diff').write_text(diff)
            if phase=='hidden':(inputs/'hidden.diff').write_text(hidden)
            prepared=base/'validation';prepared.mkdir()
            script=base/'executor.py';script.write_text((R/'executor/executor.py').read_text().replace('/srv/ci',str(base/'ci')).replace('/in/',str(inputs)+'/').replace('/validation/',str(prepared)+'/'))
            env={**os.environ,'CASE_ID':'fixture','HIDDEN_COMMAND':f'{sys.executable} -B hidden_check.py'}
            initialized=subprocess.run([sys.executable,'-B',str(script),'validate-prepare',phase],env=env,capture_output=True,text=True)
            self.assertEqual(initialized.returncode,0,initialized.stderr)
            shutil.rmtree(inputs)  # the test container has no mounts for any diff
            command=subprocess.run([sys.executable,'-B',str(script),'validate-run',phase],env=env,capture_output=True,text=True)
            self.assertEqual(command.returncode,0,command.stderr)
            self.assertFalse((inputs/'fix.diff').exists())
            return val.last_record(command.stdout,'EXECUTOR '),{'phase':'Succeeded/'}
        result=val.validate_case('fixture','patch','phase',True,runner)
        self.assertEqual(result['outcome'],'green_passes_hidden',result)
        self.assertEqual(result['suite_pass'],3);self.assertEqual(result['hidden_pass'],3)
        self.assertEqual(len(set(locations)),6)
    def test_preparation_keeps_fixed_cache_private(self):
        (self.repo/'go.mod').write_text('module example.test/fixture\n\ngo 1.20\n')
        for args in [('add','.'),('-c','user.name=test','-c','user.email=test@example.invalid','commit','-qm','go')]:
            subprocess.run(['git',*args],cwd=self.repo,check=True,capture_output=True)
        broken=subprocess.run(['git','rev-parse','HEAD'],cwd=self.repo,check=True,capture_output=True,text=True).stdout.strip()
        (self.repo/'go.mod').write_text('module example.test/fixture\n\ngo 1.21\n')
        for args in [('add','.'),('-c','user.name=test','-c','user.email=test@example.invalid','commit','-qm','fix')]:
            subprocess.run(['git',*args],cwd=self.repo,check=True,capture_output=True)
        fixed=subprocess.run(['git','rev-parse','HEAD'],cwd=self.repo,check=True,capture_output=True,text=True).stdout.strip()
        original=prep.command;seen=[]
        def command(args,cwd=None):
            args=list(args)
            if 'clone' in args:args[-2]=str(self.repo)
            return original(args,cwd)
        def worker(cid,phase,source,output,meta,seed=None):
            seen.append(phase);output.mkdir();(output/'uv').mkdir()
            self.assertNotIn('hidden_cmd',meta);self.assertNotIn('fix_sha',meta)
            if seed is not None:shutil.copytree(seed,output/'gomod')
            else:(output/'gomod').mkdir()
            (output/'gomod'/phase).write_text('cached module')
            locked=output/'readonly';locked.mkdir();(locked/'module.go').write_text('cached data');locked.chmod(0o555)
            count=subprocess.run(['git','rev-list','--count','HEAD'],cwd=source,capture_output=True,text=True,check=True).stdout.strip()
            self.assertEqual(count,'1')
            return 'PREP_COMPILE {"ok": true}\nrepository output\nPREP_COMPILE '+json.dumps({'phase':phase,'ok':phase!='broken'})+'\nPREP_WORKER_DONE\n'
        candidate={'repo':'example/fixture','language':'Go','broken_sha':broken,'fix_sha':fixed,'workflow':'tests','failed_job':'go','go_pkgs':['example.test/fixture'],'fix_files':['go.mod']}
        ci=self.root/'ci'
        with patch.object(prep,'ROOT',ci),patch.object(prep,'command',side_effect=command),patch.object(prep,'run_worker',side_effect=worker):
            result=prep.prepare(candidate)
        self.assertEqual(seen,['broken','fixed'])
        agent_cache=ci/'cases'/result['id']/'gomod';control_cache=ci/'secret'/result['id']/'gomod'
        self.assertEqual({p.name for p in agent_cache.iterdir()},{'broken'})
        self.assertEqual({p.name for p in control_cache.iterdir()},{'broken','fixed'})
        self.assertFalse((ci/'cases'/result['id']/'fix.diff').exists())
        self.assertFalse((ci/'work'/result['id']).exists())
        self.assertIs(result['broken_compiles'],False)  # the last PREP_COMPILE line of the broken worker
        self.assertIs(json.loads((ci/'cases'/result['id']/'meta.json').read_text())['broken_compiles'],False)
        self.assertIsNone(prep.compile_result('no record'));self.assertIsNone(prep.compile_result(None))
        env=lambda phase:{e['name']:e['value'] for e in prep.worker_spec('fixture','w','/s','/o',{'language':'Go'},phase)['spec']['containers'][0]['env']}
        self.assertEqual(env('broken')['PREP_PHASE'],'broken');self.assertNotIn('PREP_PHASE',env(None))
    def test_preparation_requires_selected_go_packages_to_compile(self):
        for fail_compile in (False,True):
            with self.subTest(fail_compile=fail_compile):
                root=self.root/str(fail_compile);root.mkdir();source=root/'input';source.mkdir();(source/'main.go').write_text('package main\n')
                case=root/'ci/cases/fixture';case.mkdir(parents=True);bin_dir=root/'bin';bin_dir.mkdir()
                go=bin_dir/'go';go.write_text('#!'+sys.executable+'\nimport sys\n'
                    'sys.exit(7 if sys.argv[1:3]==["mod","download"] or ('+repr(fail_compile)+' and sys.argv[1]=="test") else 0)\n');go.chmod(0o755)
                worker=root/'worker.py';worker.write_text((R/'cases/prep_worker.py').read_text().replace('/srv/ci',str(root/'ci')).replace('/input',str(source)))
                result=subprocess.run([sys.executable,'-B',str(worker)],env={**os.environ,'CASE_ID':'fixture',
                    'TASK':json.dumps({'language':'Go','workdir':'.','targets':['./...']}),'PATH':str(bin_dir)+':'+os.environ['PATH']},capture_output=True,text=True)
                self.assertIn('PREP_OPTIONAL_FAILED',result.stdout)
                self.assertEqual(result.returncode!=0,fail_compile,result.stderr)
                self.assertEqual('PREP_WORKER_DONE' in result.stdout,not fail_compile)
                # The broken tree may be red because it does not compile: recorded, not fatal.
                shutil.rmtree(case);case.mkdir()
                broken=subprocess.run([sys.executable,'-B',str(worker)],env={**os.environ,'CASE_ID':'fixture','PREP_PHASE':'broken',
                    'TASK':json.dumps({'language':'Go','workdir':'.','targets':['./...']}),'PATH':str(bin_dir)+':'+os.environ['PATH']},capture_output=True,text=True)
                self.assertEqual(broken.returncode,0,broken.stderr);self.assertIn('PREP_WORKER_DONE',broken.stdout)
                self.assertEqual(prep.compile_result(broken.stdout),not fail_compile)
                self.assertIs(prep.compile_result(result.stdout),None if fail_compile else True)  # fatal there: no record
    def test_broken_reproduction_restores_checkout_for_every_sample(self):
        case=self.root/'ci/cases/fixture';case.mkdir(parents=True);shutil.copytree(self.repo,case/'snapshot');(case/'repo').mkdir()
        (case/'snapshot/check.py').write_text('from pathlib import Path\nassert not Path("seen").exists()\nPath("seen").write_text("state")\nraise SystemExit(7)\n')
        (case/'meta.json').write_text(json.dumps({'id':'fixture','test_cmd':shlex.join([sys.executable,'-B','check.py'])}))
        inputs=self.root/'in';inputs.mkdir();(inputs/'hidden.diff').write_text('diff --git a/hidden.py b/hidden.py\nnew file mode 100644\n--- /dev/null\n+++ b/hidden.py\n@@ -0,0 +1 @@\n+# hidden test\n')
        script=self.root/'executor.py';script.write_text((R/'executor/executor.py').read_text().replace('/srv/ci',str(self.root/'ci')).replace('/in/',str(inputs)+'/').replace('/tmp/run-output.txt',str(self.root/'run-output.txt')))
        for phase in ('broken','hidden-broken'):
            result=subprocess.run([sys.executable,'-B',str(script),'repro',phase,'3'],capture_output=True,text=True,
                env={**os.environ,'CASE_ID':'fixture','HIDDEN_COMMAND':shlex.join([sys.executable,'-B','check.py'])})
            self.assertEqual(result.returncode,0,result.stderr)
            record=val.last_record(result.stdout,'EXECUTOR ')
            self.assertEqual([s['rc'] for s in record['runs']],[7,7,7],record)
        # A mistyped tree must not run the command in the empty working directory and report "does not reproduce".
        (case/'snapshot/check.py').write_text('raise SystemExit(0)\n')
        typo=subprocess.run([sys.executable,'-B',str(script),'repro','brokn','3'],capture_output=True,text=True,env={**os.environ,'CASE_ID':'fixture'})
        self.assertNotEqual(typo.returncode,0);self.assertIn('unknown repro tree',typo.stderr);self.assertNotIn('EXECUTOR ',typo.stdout)
    def test_setup_restarts_gateway_and_waits_before_continuing(self):
        root=self.root/'setup';infra=root/'infra';infra.mkdir(parents=True);bin_dir=root/'bin';bin_dir.mkdir()
        ci=root/'ci';ci.mkdir();(ci/'admin-key').write_text('synthetic-admin')
        script=infra/'setup-lab.sh';script.write_text((R/'infra/setup-lab.sh').read_text().replace('/srv/ci',str(ci)))
        code=infra/'code-configmap.sh';code.write_text('#!/bin/sh\nexit 0\n');code.chmod(0o755)
        sudo=bin_dir/'sudo';sudo.write_text('#!/bin/sh\nexit 0\n');sudo.chmod(0o755)
        kubectl=bin_dir/'kubectl';kubectl.write_text('#!'+sys.executable+'\nimport json,os,sys\n'
            'with open("commands.jsonl","a") as f: f.write(json.dumps(sys.argv[1:])+"\\n")\n'
            'if "-f" in sys.argv and sys.argv[-1]=="-": sys.stdin.read()\n'
            'sys.exit(7 if "restart" in sys.argv and os.environ.get("FAIL_RESTART")=="1" else 0)\n');kubectl.chmod(0o755)
        for fail in ('0','1'):
            log=root/'commands.jsonl';log.write_text('')
            result=subprocess.run(['bash','infra/setup-lab.sh'],cwd=root,input='',capture_output=True,text=True,
                env={**os.environ,'PATH':str(bin_dir)+':'+os.environ['PATH'],'FAIL_RESTART':fail})
            commands=[json.loads(line) for line in log.read_text().splitlines()]
            restart=['-n','ci-gateway','rollout','restart','deploy/gateway']
            status=['-n','ci-gateway','rollout','status','deploy/gateway','--timeout=180s']
            self.assertIn(restart,commands)
            if fail=='1':self.assertNotEqual(result.returncode,0);self.assertNotIn(status,commands)
            else:self.assertEqual(result.returncode,0,result.stderr);self.assertLess(commands.index(restart),commands.index(status))
    def test_agent_shell_reports_pipeline_failure(self):
        case=self.root/'ci/cases/fixture';case.mkdir(parents=True);(case/'repo').mkdir()
        (case/'meta.json').write_text(json.dumps({'language':'Python'}));(case/'failure.txt').write_text('test failed')
        code=self.root/'code';code.mkdir();(code/'prompt-v1.txt').write_text('synthetic {language} case')
        script=self.root/'agent.py';script.write_text((R/'agent/agent.py').read_text().replace('/srv/ci',str(self.root/'ci')).replace('/code/',str(code)+'/'))
        with warnings.catch_warnings(),patch.dict(sys.modules,{'anthropic':types.ModuleType('anthropic')}),patch.dict(os.environ,{'CASE_ID':'fixture','RUN_ID':'fixture','RUN_TOKEN':'synthetic-token'}):
            warnings.simplefilter('ignore',ResourceWarning)
            agent=module('security_agent',script)
            # Repository code run by the tool must not find the model token in its environment.
            self.assertEqual(agent.RUN_TOKEN,'synthetic-token');self.assertNotIn('RUN_TOKEN',os.environ)
            rc,out,_=agent.bash('printenv RUN_TOKEN; env | grep -c synthetic-token',5)
            self.assertNotEqual(rc,0);self.assertNotIn('synthetic-token',out)
        rc,_,_=agent.bash('false | tail -1',5)
        self.assertNotEqual(rc,0)
    def test_agent_uses_token_for_model_auth_and_public_id_for_result(self):
        case=self.root/'ci/cases/fixture';case.mkdir(parents=True);shutil.copytree(self.repo,case/'snapshot');(case/'repo').mkdir()
        (case/'meta.json').write_text(json.dumps({'id':'fixture','language':'Python','test_cmd':'true'}));(case/'failure.txt').write_text('failed')
        code=self.root/'code';code.mkdir();(code/'prompt-v1.txt').write_text('synthetic {language} case')
        script=self.root/'agent.py';script.write_text((R/'agent/agent.py').read_text().replace('/srv/ci',str(self.root/'ci')).replace('/code/',str(code)+'/'))
        class StopRequest(Exception):pass
        def stop(**kwargs):raise StopRequest('offline test ends before any provider call')
        captured=[]
        def client(**kwargs):captured.append(kwargs);return types.SimpleNamespace(messages=types.SimpleNamespace(create=stop))
        stub=types.SimpleNamespace(Anthropic=client,RateLimitError=type('UnusedRateLimit',(Exception,),{}))
        env={'CASE_ID':'fixture','RUN_ID':'public-run','RUN_TOKEN':'random-bearer-fixture','GATEWAY_URL':'http://example.invalid'}
        out=io.StringIO()
        with warnings.catch_warnings(),patch.dict(sys.modules,{'anthropic':stub}),patch.dict(os.environ,env),contextlib.redirect_stdout(out):
            warnings.simplefilter('ignore',ResourceWarning)
            agent=module('security_token_agent',script);agent.main()
        self.assertEqual(captured[0]['default_headers'],{'x-run-token':'random-bearer-fixture'})
        self.assertEqual(val.last_record(out.getvalue(),'RESULT ')['run'],'public-run')
        self.assertNotIn('random-bearer-fixture',out.getvalue())
    def test_agent_reports_model_path_failures_as_infrastructure_without_a_patch(self):
        case=self.root/'ci/cases/fixture';case.mkdir(parents=True);shutil.copytree(self.repo,case/'snapshot');(case/'repo').mkdir()
        (case/'meta.json').write_text(json.dumps({'id':'fixture','language':'Python','test_cmd':'true'}));(case/'failure.txt').write_text('failed')
        code=self.root/'code';code.mkdir();(code/'prompt-v1.txt').write_text('synthetic {language} case')
        script=self.root/'agent.py';script.write_text((R/'agent/agent.py').read_text().replace('/srv/ci',str(self.root/'ci')).replace('/code/',str(code)+'/'))
        class Status(Exception):
            def __init__(self,code,text):super().__init__(f'Error code: {code} - {text}');self.status_code=code;self.body={'error':text}
        class Connection(Exception):pass
        halted='gateway halted: a run close could not be written to the state file'
        for name,error,outcome,keeps_patch in [
                ('gateway-halted',Status(503,halted),'gateway_unavailable',False),
                ('run-closed',Status(403,'unknown or closed run token'),'gateway_unavailable',False),
                ('provider-overloaded',Status(529,'overloaded_error'),'gateway_unavailable',False),
                ('provider-5xx',Status(500,'api_error'),'gateway_unavailable',False),
                ('gateway-502',Status(502,'upstream error: TimeoutError'),'gateway_unavailable',False),
                ('total-budget',Status(429,'gateway budget: this call reserves $0.0100, $0.0000 left'),'gateway_unavailable',False),
                ('provider-rate-limit',Status(429,'rate_limit_error'),'gateway_unavailable',False),
                ('no-connection',Connection('connection refused'),'gateway_unavailable',False),
                ('own-cap',Status(429,'run budget: this call reserves $0.0100, $0.0000 left in run public-run'),'budget_exhausted',True),
                ('bad-request',Status(400,'prompt is too long'),'error',True),
                ('harness-bug',RuntimeError('unexpected'),'error',True)]:
            with self.subTest(failure=name):
                holder={}
                def create(error=error,**kwargs):
                    with open(os.path.join(holder['agent'].REPO,'core.py'),'w') as f:f.write('value = 9\n')  # work left half done
                    raise error
                stub=types.SimpleNamespace(Anthropic=lambda **kwargs:types.SimpleNamespace(messages=types.SimpleNamespace(create=create)),
                                           RateLimitError=type('UnusedRateLimit',(Exception,),{}),APIConnectionError=Connection)
                env={'CASE_ID':'fixture','RUN_ID':'public-run','RUN_TOKEN':'random-bearer-fixture','GATEWAY_URL':'http://example.invalid'}
                out=io.StringIO()
                with warnings.catch_warnings(),patch.dict(sys.modules,{'anthropic':stub}),patch.dict(os.environ,env),contextlib.redirect_stdout(out):
                    warnings.simplefilter('ignore',ResourceWarning)
                    holder['agent']=module('security_failure_agent_'+name.replace('-','_'),script);holder['agent'].main()
                result=val.last_record(out.getvalue(),'RESULT ')
                self.assertEqual(result['outcome'],outcome,result);self.assertEqual(bool(result['patch']),keeps_patch,result)
                self.assertEqual(result['model_calls'],0)
    def test_attempt_with_unavailable_model_path_is_not_recorded_and_is_redone(self):
        cases=self.root/'cases';cases.mkdir();bin_dir=self.root/'bin';bin_dir.mkdir()
        ci=self.root/'ci';(ci/'cases/a').mkdir(parents=True);(ci/'cases/a/failure.txt').write_text('failed');(ci/'admin-key').write_text('synthetic-key')
        (cases/'cases.csv').write_text('case_id,repo\na,example/a\n')
        target=cases/'attempt.sh';target.write_text((R/'cases/attempt.sh').read_text().replace('/srv/ci',str(ci)));target.chmod(0o755)
        # The pod reports what the "gateway" allows: unavailable while the marker file exists, a finished attempt after.
        (cases/'pod.py').write_text('import json,os\n'
            'outcome="gateway_unavailable" if os.path.exists("halted") else "finished"\n'
            'print("RESULT "+json.dumps({"outcome":outcome,"patch":"" if outcome!="finished" else "synthetic patch","error":"InternalServerError: Error code: 503"}))\n')
        (cases/'validate.py').write_text('open("validated","a").write("x")\nprint(\'EXECUTOR {"outcome":"ci_still_red"}\')\n')
        md5=bin_dir/'md5sum';md5.write_text('#!'+sys.executable+'\nimport hashlib,sys\nprint(hashlib.md5(sys.stdin.buffer.read()).hexdigest()+"  -")\n');md5.chmod(0o755)
        curl=bin_dir/'curl';curl.write_text('#!'+sys.executable+'\nimport json,sys\n'
            'sys.stdin.read()\nwith open("gateway-calls.jsonl","a") as f: f.write(json.dumps(sys.argv[1:])+"\\n")\n'
            'print(json.dumps({"spent_usd":0.0,"calls":0,"cap_usd":0.33,"token":"synthetic-run-token-0123456789abcdef"}))\n');curl.chmod(0o755)
        env={**os.environ,'PATH':str(bin_dir)+':'+os.environ['PATH'],'ADMIN_KEY_FILE':str(ci/'admin-key'),'CLOSE_RETRY_S':'0'}
        attempt=lambda:subprocess.run(['bash','cases/attempt.sh','v1','a','1'],cwd=self.root,env=env,capture_output=True,text=True)
        journal=self.root/'results/attempts-v1.jsonl';infra=self.root/'results/infra-v1.jsonl';(self.root/'halted').write_text('x')
        opened=lambda:[json.loads(a[a.index('-d')+1])['run'] for a in map(json.loads,(self.root/'gateway-calls.jsonl').read_text().splitlines()) if a[-3].endswith('/runs')]
        first=attempt();self.assertNotEqual(first.returncode,0);self.assertIn('not recorded as an attempt',first.stderr)
        self.assertFalse(journal.exists());self.assertFalse((self.root/'validated').exists())
        self.assertFalse(list((self.root/'results/patches/v1').glob('*.diff')))
        second=attempt();self.assertNotEqual(second.returncode,0)
        tries=[json.loads(line) for line in infra.read_text().splitlines()]
        base=tries[0]['run'];self.assertEqual([t['run'] for t in tries],[base,base+'-t2']);self.assertEqual(opened(),[base,base+'-t2'])  # never a reused id
        self.assertTrue(all(t['agent']['outcome']=='gateway_unavailable' and 'unavailable' in t['reason'] for t in tries))
        (self.root/'halted').unlink()
        third=attempt();self.assertEqual(third.returncode,0,third.stdout+third.stderr)
        rows=[json.loads(line) for line in journal.read_text().splitlines()]
        self.assertEqual([(r['run'],r['rep'],r['agent']['outcome'],r['executor']['outcome']) for r in rows],[(base+'-t3',1,'finished','ci_still_red')])
        again=attempt();self.assertEqual(again.returncode,0);self.assertIn('already recorded; skipping',again.stdout)
        self.assertEqual(len(opened()),3);self.assertEqual(len(infra.read_text().splitlines()),2)
        # A case that keeps failing for infrastructure reasons stops asking the gateway and asks for a person.
        (self.root/'halted').write_text('x')
        for rep in (1,2,3):
            last=subprocess.run(['bash','cases/attempt.sh','v1','a','2'],cwd=self.root,env=env,capture_output=True,text=True);self.assertNotEqual(last.returncode,0)
        calls_before=len(opened())
        refused=subprocess.run(['bash','cases/attempt.sh','v1','a','2'],cwd=self.root,env=env,capture_output=True,text=True)
        self.assertNotEqual(refused.returncode,0);self.assertIn('already failed 3 times for infrastructure reasons',refused.stderr);self.assertEqual(len(opened()),calls_before)
    def test_run_round_propagates_attempt_failure(self):
        (self.root/'cases').mkdir();(self.root/'cases/cases.csv').write_text('case_id\nfixture\n')
        shutil.copyfile(R/'cases/run-round.sh',self.root/'cases/run-round.sh')
        attempt=self.root/'cases/attempt.sh';attempt.write_text('#!/bin/bash\necho failed\nexit 7\n');attempt.chmod(0o755)
        run=subprocess.run(['bash','cases/run-round.sh','v1','1'],cwd=self.root,capture_output=True,text=True)
        self.assertNotEqual(run.returncode,0);self.assertNotIn('repetition 1 done',run.stdout)
    def test_reproduction_checks_hidden_control_completeness_and_stability(self):
        cases=self.root/'cases';cases.mkdir();shutil.copyfile(R/'cases/repro.sh',cases/'repro.sh')
        (cases/'pod.py').write_text('import json,sys\nrecords=json.load(open("fixture.json"))\nprint("EXECUTOR "+json.dumps(records[sys.argv[-2]]))\n')
        runs=lambda codes:[{'rc':code,'integrity':{'outcome':'sampled'}} for code in codes]
        for fixed,broken,expected in [([0,0,0],[1,1,1],'reproduced'),([0,0,0],None,'infra_error'),
                                     ([0,1,0],[1,1,1],'intermittent'),([0,0,0],[0,1,0],'intermittent'),
                                     ([1,1,1],[1,1,1],'not_reproduced_hidden_fix_fails'),([0,0,0],[0,0,0],'reproduced')]:
            with self.subTest(fixed=fixed,broken=broken):
                records={'broken':{'fail':3},'fixed':{'pass':3,'runs':runs([0,0,0]),'hidden_runs':runs(fixed)},
                         'hidden-broken':{'runs':runs(broken)} if broken is not None else {},
                         'fixed-agent-cache':{'not_applicable':True}}
                (self.root/'fixture.json').write_text(json.dumps(records))
                process=subprocess.run(['bash','cases/repro.sh','fixture'],cwd=self.root,capture_output=True,text=True)
                self.assertEqual(process.returncode,0,process.stderr)
                record=json.loads((cases/'repro.jsonl').read_text().splitlines()[-1])
                self.assertEqual(record['verdict'],expected)
                self.assertEqual(record['hidden_control']['discriminates'],fixed==[0,0,0] and broken==[1,1,1])
    def test_round_resume_skips_recorded_attempts_without_remote_calls(self):
        cases=self.root/'cases';cases.mkdir();bin_dir=self.root/'bin';bin_dir.mkdir()
        ci=self.root/'ci';(ci/'cases/a').mkdir(parents=True);(ci/'cases/b').mkdir()
        (ci/'cases/a/failure.txt').write_text('failed');(ci/'admin-key').write_text('synthetic-key')
        (cases/'cases.csv').write_text('case_id,repo\na,example/a\nb,example/b\n')
        for name in ('attempt.sh','run-round.sh','check-round.py'):
            target=cases/name;target.write_text((R/'cases'/name).read_text().replace('/srv/ci',str(ci)));target.chmod(0o755)
        # Exercise the real shell runner/attempt journal. Only the external gateway and pod boundaries are fake.
        (cases/'pod.py').write_text('import os,sys\nassert os.environ["RUN_TOKEN"] == "synthetic-run-token-0123456789abcdef"\nassert os.environ["RUN_TOKEN"] not in " ".join(sys.argv)\nprint(\'RESULT {"outcome":"finished","patch":"synthetic patch"}\')\n')
        (cases/'validate.py').write_text('print(\'EXECUTOR {"outcome":"ci_still_red"}\')\n')
        curl=bin_dir/'curl';curl.write_text('#!'+sys.executable+'\nimport json,sys\n'
            'sys.stdin.read()\nwith open("gateway-calls.jsonl","a") as f: f.write(json.dumps(sys.argv[1:])+"\\n")\n'
            'print(json.dumps({"spent_usd":0.01,"calls":1,"cap_usd":0.33,"token":"synthetic-run-token-0123456789abcdef"}))\n');curl.chmod(0o755)
        md5=bin_dir/'md5sum';md5.write_text('#!'+sys.executable+'\nimport hashlib,sys\nprint(hashlib.md5(sys.stdin.buffer.read()).hexdigest()+"  -")\n');md5.chmod(0o755)
        env={**os.environ,'PATH':str(bin_dir)+':'+os.environ['PATH'],'ADMIN_KEY_FILE':str(ci/'admin-key')}
        command=['bash','cases/run-round.sh','v1','1']
        first=subprocess.run(command,cwd=self.root,env=env,capture_output=True,text=True)
        self.assertNotEqual(first.returncode,0);self.assertIn('has no failure.txt',first.stdout)
        journal=self.root/'results/attempts-v1.jsonl';saved=json.loads(journal.read_text())
        self.assertEqual((saved['case'],saved['rep']),('a',1))
        # JSON formatting is immaterial to resumption; recorded failed attempts are also skipped.
        journal.write_text(json.dumps(saved,separators=(',',':'))+'\n');prefix=journal.read_bytes()
        patch_file=self.root/'results/patches/v1'/f"{saved['run']}.diff";original_patch=patch_file.read_bytes()
        (ci/'cases/b/failure.txt').write_text('failed')
        resumed=subprocess.run(command,cwd=self.root,env=env,capture_output=True,text=True)
        self.assertEqual(resumed.returncode,0,resumed.stdout+resumed.stderr)
        self.assertIn('already recorded; skipping',resumed.stdout)
        self.assertIn('6 unique attempts',resumed.stdout)
        self.assertTrue(journal.read_bytes().startswith(prefix));self.assertEqual(patch_file.read_bytes(),original_patch)
        rows=[json.loads(line) for line in journal.read_text().splitlines()]
        self.assertEqual({(r['case'],r['rep']) for r in rows},{(c,i) for c in ('a','b') for i in (1,2,3)})
        self.assertEqual(len(rows),6)
        self.assertNotIn('synthetic-run-token-',journal.read_text())
        requests=self.root/'gateway-calls.jsonl';calls=[json.loads(line) for line in requests.read_text().splitlines()]
        opened=[args for args in calls if any(a.endswith('/runs') for a in args)]
        self.assertEqual(len(opened),6)
        before=(journal.read_bytes(),requests.read_bytes())
        shutil.rmtree(ci)  # completed records need neither prepared trees nor the gateway credential
        again=subprocess.run(command,cwd=self.root,env=env,capture_output=True,text=True)
        self.assertEqual(again.returncode,0,again.stdout+again.stderr)
        self.assertEqual((journal.read_bytes(),requests.read_bytes()),before)

    def test_attempt_closes_run_opened_without_usable_token(self):
        cases=self.root/'cases';cases.mkdir();bin_dir=self.root/'bin';bin_dir.mkdir()
        ci=self.root/'ci';(ci/'cases/a').mkdir(parents=True);(ci/'cases/a/failure.txt').write_text('failed');(ci/'admin-key').write_text('synthetic-key')
        (cases/'cases.csv').write_text('case_id,repo\na,example/a\n')
        target=cases/'attempt.sh';target.write_text((R/'cases/attempt.sh').read_text().replace('/srv/ci',str(ci)));target.chmod(0o755)
        (cases/'pod.py').write_text('open("pod-ran","w").write("x")\n');(cases/'validate.py').write_text('open("pod-ran","w").write("x")\n')
        md5=bin_dir/'md5sum';md5.write_text('#!'+sys.executable+'\nimport hashlib,sys\nprint(hashlib.md5(sys.stdin.buffer.read()).hexdigest()+"  -")\n');md5.chmod(0o755)
        for name,reply in (('no-token','{"cap_usd":0.33,"open":true}'),('short-token','{"token":"short"}'),('not-json','ok')):
            with self.subTest(reply=name):
                curl=bin_dir/'curl';curl.write_text('#!'+sys.executable+'\nimport json,sys\n'
                    'sys.stdin.read()\nwith open("gateway-calls.jsonl","a") as f: f.write(json.dumps(sys.argv[1:])+"\\n")\n'
                    'print('+repr(reply)+')\n');curl.chmod(0o755)
                (self.root/'gateway-calls.jsonl').write_text('')
                run=subprocess.run(['bash','cases/attempt.sh','v1','a','1'],cwd=self.root,capture_output=True,text=True,
                    env={**os.environ,'PATH':str(bin_dir)+':'+os.environ['PATH'],'ADMIN_KEY_FILE':str(ci/'admin-key')})
                self.assertNotEqual(run.returncode,0);self.assertIn('returned no usable token; the run was closed',run.stdout)
                calls=[json.loads(line) for line in (self.root/'gateway-calls.jsonl').read_text().splitlines()]
                self.assertEqual(len(calls),2,calls)
                self.assertTrue(any(a.endswith('/runs') for a in calls[0]));self.assertTrue(any(a.endswith('/close') for a in calls[1]))
                self.assertFalse((self.root/'pod-ran').exists());self.assertFalse((self.root/'results/attempts-v1.jsonl').exists())
        tries=[json.loads(line) for line in (self.root/'results/infra-v1.jsonl').read_text().splitlines()]
        self.assertEqual([t['run'][-3:] for t in tries[1:]],['-t2','-t3']);self.assertTrue(all('no usable token' in t['reason'] for t in tries))
    def test_attempt_stops_the_round_when_the_close_is_never_confirmed(self):
        # The gateway halts when it cannot write a close. The attempt is still recorded (cost unknown) and the script fails.
        cases=self.root/'cases';cases.mkdir();bin_dir=self.root/'bin';bin_dir.mkdir()
        ci=self.root/'ci';(ci/'cases/a').mkdir(parents=True);(ci/'cases/a/failure.txt').write_text('failed');(ci/'admin-key').write_text('synthetic-key')
        (cases/'cases.csv').write_text('case_id,repo\na,example/a\n')
        target=cases/'attempt.sh';target.write_text((R/'cases/attempt.sh').read_text().replace('/srv/ci',str(ci)));target.chmod(0o755)
        (cases/'pod.py').write_text('print(\'RESULT {"outcome":"finished","patch":"synthetic patch"}\')\n')
        (cases/'validate.py').write_text('print(\'EXECUTOR {"outcome":"ci_still_red"}\')\n')
        md5=bin_dir/'md5sum';md5.write_text('#!'+sys.executable+'\nimport hashlib,sys\nprint(hashlib.md5(sys.stdin.buffer.read()).hexdigest()+"  -")\n');md5.chmod(0o755)
        curl=bin_dir/'curl';curl.write_text('#!'+sys.executable+'\nimport json,os,sys\n'
            'sys.stdin.read()\nwith open("gateway-calls.jsonl","a") as f: f.write(json.dumps(sys.argv[1:])+"\\n")\n'
            'closing=any(a.endswith("/close") for a in sys.argv)\n'
            'n=sum(1 for line in open("gateway-calls.jsonl") if "/close" in line)\n'
            'if closing and n<=int(os.environ["FAIL_CLOSES"]):sys.exit(22)\n'
            'print(json.dumps({"spent_usd":0.01,"calls":1,"cap_usd":0.33,"token":"synthetic-run-token-0123456789abcdef"}))\n');curl.chmod(0o755)
        for rep,failing,expected_closes,ok in ((1,1,2,True),(2,3,3,False)):
            with self.subTest(failing_closes=failing):
                (self.root/'gateway-calls.jsonl').write_text('')
                run=subprocess.run(['bash','cases/attempt.sh','v1','a',str(rep)],cwd=self.root,capture_output=True,text=True,
                    env={**os.environ,'PATH':str(bin_dir)+':'+os.environ['PATH'],'ADMIN_KEY_FILE':str(ci/'admin-key'),'CLOSE_RETRY_S':'0','FAIL_CLOSES':str(failing)})
                closes=sum('/close' in line for line in (self.root/'gateway-calls.jsonl').read_text().splitlines())
                self.assertEqual(closes,expected_closes,run.stdout+run.stderr)
                row=json.loads((self.root/'results/attempts-v1.jsonl').read_text().splitlines()[-1])
                self.assertEqual((row['rep'],row['executor']['outcome']),(rep,'ci_still_red'))
                self.assertEqual(run.returncode==0,ok,run.stdout+run.stderr)
                self.assertEqual(row['gateway']['spent_usd'],0.01 if ok else None)
                self.assertEqual('did not confirm the close' in run.stderr,not ok)
    def test_maintainer_side_effects_are_flagged_by_reproduction_before_freeze(self):
        # Actual executor -> repro.sh -> freeze.py, with only pod launching replaced by local subprocesses.
        records={}
        for phase in ('clean','suite','hidden','no-hidden'):
            with self.subTest(phase=phase):
                root=self.root/phase;cases=root/'cases';cases.mkdir(parents=True)
                case=root/'ci/cases/fixture';case.mkdir(parents=True);shutil.copytree(self.repo,case/'snapshot');(case/'repo').mkdir()
                snapshot=case/'snapshot'
                for script,dirty in [('check.py',phase in ('suite','no-hidden')),('hidden_check.py',phase=='hidden')]:
                    text='import core\nfrom pathlib import Path\nassert core.value == 1\n'
                    if dirty:text+='assert not Path("coverage.xml").exists()\nPath("coverage.xml").write_text("coverage")\n'
                    (snapshot/script).write_text(text)
                for args in [('add','.'),('-c','user.name=test','-c','user.email=test@example.invalid','commit','-qm','checks')]:
                    subprocess.run(['git',*args],cwd=snapshot,check=True,capture_output=True)
                (snapshot/'core.py').write_text('value = 1\n')
                fix=subprocess.run(['git','diff','--binary'],cwd=snapshot,check=True,capture_output=True,text=True).stdout
                (snapshot/'core.py').write_text('value = 0\n')
                hidden='diff --git a/added_test.py b/added_test.py\nnew file mode 100644\n--- /dev/null\n+++ b/added_test.py\n@@ -0,0 +1 @@\n+# hidden regression test\n'
                inputs=root/'in';inputs.mkdir();(inputs/'fix.diff').write_text(fix+hidden);(inputs/'hidden.diff').write_text(hidden)
                command=shlex.quote(sys.executable)+' -B '
                (case/'meta.json').write_text(json.dumps({'id':'fixture','test_cmd':command+'check.py'}))
                executor=root/'executor.py';executor.write_text((R/'executor/executor.py').read_text().replace('/srv/ci',str(root/'ci')).replace('/in/',str(inputs)+'/').replace('/tmp/run-output.txt',str(root/'run-output.txt')))
                shutil.copyfile(R/'cases/repro.sh',cases/'repro.sh')
                (cases/'pod.py').write_text('import os,subprocess,sys\n'
                    'env={**os.environ,"CASE_ID":sys.argv[2]}\n'
                    'sys.exit(subprocess.run([sys.executable,"-B","executor.py",*sys.argv[sys.argv.index("/code/executor.py")+1:]],env=env).returncode)\n')
                process=subprocess.run(['bash','cases/repro.sh','fixture'],cwd=root,
                    env={**os.environ,'HIDDEN_COMMAND':command+'hidden_check.py' if phase!='no-hidden' else ''},capture_output=True,text=True)
                self.assertEqual(process.returncode,0,process.stderr)
                record=json.loads((cases/'repro.jsonl').read_text());records[phase]=record
                self.assertEqual((record['broken_fail'],record['fixed_pass']),(3,3),record)
                expected='reproduced' if phase=='clean' else 'incompatible_test_side_effects'
                self.assertEqual(record['verdict'],expected,record)
                samples=record['fixed']['runs']+record['fixed'].get('hidden_runs',[])
                self.assertTrue(all(s['rc']==0 for s in samples),samples)  # each sample starts clean
                if phase!='clean':
                    changed=record['integrity_control']['hidden' if phase=='hidden' else 'suite']
                    self.assertEqual(len(changed),3)
                    self.assertTrue(all('coverage.xml' in check['why'] for check in changed))
        self.freeze_fixture(records['clean'],records['hidden'])

    def freeze_fixture(self, clean, incompatible):
        root=self.root/'freeze';cases=root/'cases';cases.mkdir(parents=True);(root/'mining').mkdir();(cases/'prep-out').mkdir()
        (cases/'prep-out/prep.jsonl').write_text('')
        candidates=[];records=[]
        for i in range(9):
            sha=f'{i:040x}';cid=f'example-case{i}-{sha[:8]}'
            candidates.append({'repo':f'example/case{i}','broken_sha':sha,'fix_sha':'f'*40,'language':'Python',
                               'workflow':'tests','failed_job':'tests','failed_run':1})
            record=json.loads(json.dumps(clean if i<8 else incompatible));record['id']=cid;records.append(record)
            secret=root/'ci/secret'/cid;secret.mkdir(parents=True);(root/'ci/cases'/cid).mkdir(parents=True)
            (secret/'meta.json').write_text(json.dumps({'test_cmd':'synthetic command'}))
        (root/'mining/candidates-python.jsonl').write_text(''.join(json.dumps(c)+'\n' for c in candidates))
        (root/'mining/candidates-go.jsonl').write_text('')
        (cases/'repro.jsonl').write_text(''.join(json.dumps(r)+'\n' for r in records))
        script=cases/'freeze.py';script.write_text((R/'cases/freeze.py').read_text().replace('/srv/ci',str(root/'ci')))
        frozen=subprocess.run([sys.executable,'-B','cases/freeze.py'],cwd=root,capture_output=True,text=True)
        self.assertEqual(frozen.returncode,0,frozen.stderr)
        with (cases/'cases.csv').open() as f:rows=list(csv.DictReader(f))
        self.assertEqual(len(rows),8);self.assertNotIn(records[-1]['id'],[r['case_id'] for r in rows])
        with (cases/'not-reproduced.csv').open() as f:excluded=list(csv.DictReader(f))
        self.assertEqual(excluded[0]['verdict'],'incompatible_test_side_effects')
        # Legacy reproduction records cannot silently bypass the new prerequisite.
        (cases/'cases.csv').unlink();records[0].pop('integrity_control')
        (cases/'repro.jsonl').write_text(''.join(json.dumps(r)+'\n' for r in records))
        missing=subprocess.run([sys.executable,'-B','cases/freeze.py'],cwd=root,capture_output=True,text=True)
        self.assertNotEqual(missing.returncode,0);self.assertIn('maintainer integrity control',missing.stderr)
        self.assertFalse((cases/'cases.csv').exists())
        records[0]['integrity_control']=clean['integrity_control']
        records[0]['hidden_control']['discriminates']=False
        (cases/'repro.jsonl').write_text(''.join(json.dumps(r)+'\n' for r in records))
        def freeze():return subprocess.run([sys.executable,'-B','cases/freeze.py'],cwd=root,capture_output=True,text=True)
        required=freeze();self.assertNotEqual(required.returncode,0);self.assertIn('needs an eligibility decision',required.stderr)
        digest=hashlib.sha256(json.dumps(records[0],sort_keys=True,separators=(',',':')).encode()).hexdigest()
        decision={'decision':'include','reason':'Reviewed the cause and retained the supplemental hidden check.',
                  'reviewer':'synthetic reviewer','repro_sha256':digest}
        dpath=cases/'eligibility-decisions.json'
        for invalid in ({**decision,'reason':' '},{**decision,'repro_sha256':'stale'}):
            dpath.write_text(json.dumps({records[0]['id']:invalid}));self.assertNotEqual(freeze().returncode,0)
        dpath.write_text(json.dumps({records[0]['id']:decision}));included=freeze()
        self.assertEqual(included.returncode,0,included.stderr)
        self.assertEqual(json.loads((cases/'eligibility-at-freeze.json').read_text())[records[0]['id']],decision)
        (cases/'cases.csv').unlink()
        records[-1]={**clean,'id':records[-1]['id']};(cases/'repro.jsonl').write_text(''.join(json.dumps(r)+'\n' for r in records))
        decision['decision']='exclude';dpath.write_text(json.dumps({records[0]['id']:decision}));excluded_run=freeze()
        self.assertEqual(excluded_run.returncode,0,excluded_run.stderr)
        with (cases/'cases.csv').open() as f:self.assertNotIn(records[0]['id'],[r['case_id'] for r in csv.DictReader(f)])
        (cases/'excluded-recheck.txt').write_text('');(root/'mining/candidates-go.log').write_text('')
        (root/'mining/candidates-python.log').write_text(''.join(json.dumps({'repo':c['repo'],'item':'pair','verdict':'candidate'})+'\n' for c in candidates))
        shutil.copyfile(R/'cases/funnel.py',cases/'funnel.py')
        funnel=subprocess.run([sys.executable,'-B','cases/funnel.py'],cwd=root,capture_output=True,text=True)
        self.assertEqual(funnel.returncode,0,funnel.stderr);self.assertIn('excluded: eligibility review: 1',funnel.stdout)
    def test_reproduction_runs_maintainer_fix_with_agent_cache(self):
        # The fourth control runs only for a reproduced pair; a failing control keeps the verdict and is left to freeze.py.
        cases=self.root/'cases';cases.mkdir();shutil.copyfile(R/'cases/repro.sh',cases/'repro.sh')
        (cases/'pod.py').write_text('import json,sys\nopen("calls.txt","a").write(sys.argv[-2]+"\\n")\n'
            'records=json.load(open("fixture.json"))\nprint("EXECUTOR "+json.dumps(records[sys.argv[-2]]))\n')
        runs=lambda codes:[{'rc':code,'integrity':{'outcome':'sampled'}} for code in codes]
        ok=runs([0,0,0])
        dirty=[{'rc':0,'integrity':{'outcome':'test_changed_tree','why':'test command changed the working tree: go.sum'}} for _ in range(3)]
        unchecked=[{'rc':0} for _ in range(3)]
        for name,broken_fail,control,verdict,applicable,passes,called in [
                ('passes',3,{'runs':ok,'hidden_runs':ok},'reproduced',True,True,True),
                ('suite-changes-tree',3,{'runs':dirty,'hidden_runs':ok},'reproduced',True,False,True),
                ('hidden-changes-tree',3,{'runs':ok,'hidden_runs':dirty},'reproduced',True,False,True),
                ('integrity-not-checked',3,{'runs':unchecked,'hidden_runs':ok},'infra_error',True,False,True),
                ('suite-fails',3,{'runs':runs([1,1,1]),'hidden_runs':ok},'reproduced',True,False,True),
                ('hidden-fails',3,{'runs':ok,'hidden_runs':runs([2,2,2])},'reproduced',True,False,True),
                ('not-go',3,{'not_applicable':True},'reproduced',False,None,True),
                ('missing',3,{},'infra_error',True,False,True),
                ('incomplete',3,{'runs':ok,'hidden_runs':runs([0,0])},'infra_error',True,False,True),
                ('timeout',3,{'runs':runs([0,124,0]),'hidden_runs':ok},'infra_error',True,False,True),
                ('fix-does-not-apply',3,{'error':'maintainer fix does not apply'},'infra_error',True,False,True),
                ('broken-passes',0,{'runs':ok,'hidden_runs':ok},'not_reproduced_broken_passes',None,None,False)]:
            with self.subTest(name=name):
                records={'broken':{'fail':broken_fail,'prep_compiles':False},'fixed':{'pass':3,'runs':ok,'hidden_runs':ok},
                         'hidden-broken':{'runs':runs([1,1,1])},'fixed-agent-cache':control}
                (self.root/'fixture.json').write_text(json.dumps(records));(self.root/'calls.txt').write_text('')
                process=subprocess.run(['bash','cases/repro.sh','fixture'],cwd=self.root,capture_output=True,text=True)
                self.assertEqual(process.returncode,0,process.stderr)
                record=json.loads((cases/'repro.jsonl').read_text().splitlines()[-1])
                self.assertEqual(record['verdict'],verdict,record)
                self.assertEqual(record['cache_control']['applicable'],applicable,record)
                self.assertEqual(record['cache_control'].get('passes'),passes,record)
                self.assertEqual('fixed-agent-cache' in (self.root/'calls.txt').read_text().split(),called)
                self.assertIs(record['prep_control']['broken_compiles'],False)
                if applicable:
                    expected='changed' if 'changes-tree' in name else 'error' if verdict=='infra_error' else 'clean'
                    self.assertEqual(record['cache_control']['integrity'],expected,record)
                    self.assertEqual('go.sum' in record['cache_control'].get('why',''),'changes-tree' in name)
    def test_executor_agent_cache_control_and_compile_record(self):
        hidden='diff --git a/added_test.py b/added_test.py\nnew file mode 100644\n--- /dev/null\n+++ b/added_test.py\n@@ -0,0 +1 @@\n+# hidden regression test\n'
        for language,compiles in (('Go',False),('Python',None)):
            with self.subTest(language=language):
                root=self.root/language;case=root/'ci/cases/fixture';case.mkdir(parents=True);shutil.copytree(self.repo,case/'snapshot');(case/'repo').mkdir()
                snapshot=case/'snapshot';(snapshot/'check.py').write_text('import core\nassert core.value == 1\n')
                for args in [('add','.'),('-c','user.name=test','-c','user.email=test@example.invalid','commit','-qm','check')]:
                    subprocess.run(['git',*args],cwd=snapshot,check=True,capture_output=True)
                (snapshot/'core.py').write_text('value = 1\n')
                fix=subprocess.run(['git','diff','--binary'],cwd=snapshot,check=True,capture_output=True,text=True).stdout
                (snapshot/'core.py').write_text('value = 0\n')
                inputs=root/'in';inputs.mkdir();(inputs/'fix.diff').write_text(fix+hidden);(inputs/'hidden.diff').write_text(hidden)
                command=shlex.join([sys.executable,'-B','check.py'])
                meta={'id':'fixture','language':language,'test_cmd':command}
                if compiles is not None:meta['broken_compiles']=compiles
                (case/'meta.json').write_text(json.dumps(meta))
                script=root/'executor.py';script.write_text((R/'executor/executor.py').read_text().replace('/srv/ci',str(root/'ci')).replace('/in/',str(inputs)+'/').replace('/tmp/run-output.txt',str(root/'run-output.txt')))
                def repro(tree):
                    result=subprocess.run([sys.executable,'-B',str(script),'repro',tree,'3'],capture_output=True,text=True,
                        env={**os.environ,'CASE_ID':'fixture','HIDDEN_COMMAND':command})
                    self.assertEqual(result.returncode,0,result.stderr);return val.last_record(result.stdout,'EXECUTOR ')
                control=repro('fixed-agent-cache')
                if language=='Go':
                    self.assertEqual([s['rc'] for s in control['runs']],[0,0,0],control)
                    self.assertEqual([s['rc'] for s in control['hidden_runs']],[0,0,0],control)
                else:
                    self.assertTrue(control['not_applicable']);self.assertNotIn('runs',control)
                broken=repro('broken')
                self.assertEqual(broken['fail'],3,broken);self.assertIs(broken['prep_compiles'],compiles)
    def test_agent_cache_control_tree_change_blocks_automatic_freeze(self):
        # Real executor -> repro.sh -> freeze.py. With the agent's cache the suite ends 0 and writes go.sum: not a pass.
        root=self.root/'cache-e2e';cases=root/'cases';cases.mkdir(parents=True)
        case=root/'ci/cases/fixture';case.mkdir(parents=True);shutil.copytree(self.repo,case/'snapshot');(case/'repo').mkdir()
        snapshot=case/'snapshot'
        (snapshot/'check.py').write_text('import core,os\nfrom pathlib import Path\nassert core.value == 1\n'
            'if os.environ.get("AGENT_CACHE"):Path("go.sum").write_text("example.test/module v1.0.0 h1:synthetic\\n")\n')
        for args in [('add','.'),('-c','user.name=test','-c','user.email=test@example.invalid','commit','-qm','check')]:
            subprocess.run(['git',*args],cwd=snapshot,check=True,capture_output=True)
        (snapshot/'core.py').write_text('value = 1\n')
        fix=subprocess.run(['git','diff','--binary'],cwd=snapshot,check=True,capture_output=True,text=True).stdout
        (snapshot/'core.py').write_text('value = 0\n')
        inputs=root/'in';inputs.mkdir();(inputs/'fix.diff').write_text(fix);(inputs/'hidden.diff').write_text('')
        (case/'meta.json').write_text(json.dumps({'id':'fixture','language':'Go','broken_compiles':True,'test_cmd':shlex.join([sys.executable,'-B','check.py'])}))
        (root/'executor.py').write_text((R/'executor/executor.py').read_text().replace('/srv/ci',str(root/'ci')).replace('/in/',str(inputs)+'/').replace('/tmp/run-output.txt',str(root/'run-output.txt')))
        shutil.copyfile(R/'cases/repro.sh',cases/'repro.sh')
        (cases/'pod.py').write_text('import os,subprocess,sys\n'
            'action=sys.argv[sys.argv.index("/code/executor.py")+1:]\n'
            'env={**os.environ,"CASE_ID":sys.argv[2]}\n'
            'if action[1]=="fixed-agent-cache":env["AGENT_CACHE"]="1"\n'
            'sys.exit(subprocess.run([sys.executable,"-B","executor.py",*action],env=env).returncode)\n')
        process=subprocess.run(['bash','cases/repro.sh','fixture'],cwd=root,env={**os.environ,'HIDDEN_COMMAND':''},capture_output=True,text=True)
        self.assertEqual(process.returncode,0,process.stderr)
        record=json.loads((cases/'repro.jsonl').read_text())
        self.assertEqual(record['verdict'],'reproduced',record);self.assertEqual(record['integrity_control']['outcome'],'clean',record)
        control=record['cache_control']
        self.assertEqual([s['rc'] for s in control['suite']],[0,0,0],control)
        self.assertEqual([s['integrity']['outcome'] for s in control['suite']],['test_changed_tree']*3,control)
        self.assertIs(control['passes'],False);self.assertEqual(control['integrity'],'changed');self.assertIn('go.sum',control['why'])
        (root/'mining').mkdir();(cases/'prep-out').mkdir();(cases/'prep-out/prep.jsonl').write_text('');candidates=[];records=[]
        for i in range(8):
            sha=f'{i:040x}';cid=f'example-go{i}-{sha[:8]}'
            candidates.append({'repo':f'example/go{i}','broken_sha':sha,'fix_sha':'f'*40,'language':'Go','workflow':'tests','failed_job':'tests','failed_run':1})
            records.append({**record,'id':cid});(root/'ci/secret'/cid).mkdir(parents=True);(root/'ci/cases'/cid).mkdir(parents=True)
            (root/'ci/secret'/cid/'meta.json').write_text(json.dumps({'test_cmd':'synthetic command'}))
        (root/'mining/candidates-go.jsonl').write_text(''.join(json.dumps(c)+'\n' for c in candidates));(root/'mining/candidates-python.jsonl').write_text('')
        (cases/'repro.jsonl').write_text(''.join(json.dumps(r)+'\n' for r in records))
        (cases/'freeze.py').write_text((R/'cases/freeze.py').read_text().replace('/srv/ci',str(root/'ci')))
        frozen=subprocess.run([sys.executable,'-B','cases/freeze.py'],cwd=root,capture_output=True,text=True)
        self.assertNotEqual(frozen.returncode,0);self.assertFalse((cases/'cases.csv').exists())
        self.assertIn('needs an eligibility decision',frozen.stderr);self.assertIn('test_changed_tree for every patch',frozen.stderr);self.assertIn('go.sum',frozen.stderr)
    def test_freeze_requires_decisions_for_go_compile_and_cache_controls(self):
        root=self.root/'freeze-go';cases=root/'cases';cases.mkdir(parents=True);(root/'mining').mkdir();(cases/'prep-out').mkdir()
        (cases/'prep-out/prep.jsonl').write_text('');candidates=[];records=[]
        for i in range(8):
            sha=f'{i:040x}';cid=f'example-go{i}-{sha[:8]}'
            candidates.append({'repo':f'example/go{i}','broken_sha':sha,'fix_sha':'f'*40,'language':'Go','workflow':'tests','failed_job':'tests','failed_run':1})
            records.append({'id':cid,'verdict':'reproduced','broken_fail':3,'fixed_pass':3,'n':3,'broken':{'output_head':'FAIL'},
                            'integrity_control':{'outcome':'clean'},'hidden_control':{'applicable':False,'discriminates':False},
                            'cache_control':{'applicable':True,'passes':True,'integrity':'clean'},'prep_control':{'broken_compiles':True}})
            (root/'ci/secret'/cid).mkdir(parents=True);(root/'ci/cases'/cid).mkdir(parents=True)
            (root/'ci/secret'/cid/'meta.json').write_text(json.dumps({'test_cmd':'synthetic command'}))
        (root/'mining/candidates-go.jsonl').write_text(''.join(json.dumps(c)+'\n' for c in candidates));(root/'mining/candidates-python.jsonl').write_text('')
        (cases/'freeze.py').write_text((R/'cases/freeze.py').read_text().replace('/srv/ci',str(root/'ci')))
        dpath=cases/'eligibility-decisions.json'
        def freeze(first,decision=None):
            (cases/'cases.csv').unlink(missing_ok=True)
            rows=[first]+records[1:];(cases/'repro.jsonl').write_text(''.join(json.dumps(r)+'\n' for r in rows))
            if decision:
                digest=hashlib.sha256(json.dumps(first,sort_keys=True,separators=(',',':')).encode()).hexdigest()
                dpath.write_text(json.dumps({first['id']:{'decision':decision,'reason':'Read failure.txt: the commit itself does not compile.','reviewer':'synthetic reviewer','repro_sha256':digest}}))
            else:dpath.write_text('{}')
            return subprocess.run([sys.executable,'-B','cases/freeze.py'],cwd=root,capture_output=True,text=True)
        def frozen_ids():
            with (cases/'cases.csv').open() as f:return [r['case_id'] for r in csv.DictReader(f)]
        clean=freeze(records[0]);self.assertEqual(clean.returncode,0,clean.stderr);self.assertEqual(len(frozen_ids()),8)
        for missing,message in (('prep_control','broken-tree compile result'),('cache_control','agent-cache control')):
            stale={k:v for k,v in records[0].items() if k!=missing};refused=freeze(stale)
            self.assertNotEqual(refused.returncode,0);self.assertIn(message,refused.stderr);self.assertFalse((cases/'cases.csv').exists())
        tree={'applicable':True,'integrity':'changed','why':'test command changed the working tree: go.sum'}
        for change,message in (({'prep_control':{'broken_compiles':False}},'did not compile'),
                               ({'cache_control':{'applicable':True,'passes':False,'integrity':'clean'}},"does not pass with the agent's dependency cache"),
                               ({'cache_control':{'applicable':True,'passes':True}},"does not pass with the agent's dependency cache"),
                               ({'cache_control':{**tree,'passes':False}},'test_changed_tree for every patch: test command changed the working tree: go.sum'),
                               ({'cache_control':{**tree,'passes':True}},'test_changed_tree for every patch')):
            with self.subTest(change=change):
                flagged={**records[0],**change};required=freeze(flagged)
                self.assertNotEqual(required.returncode,0);self.assertIn('needs an eligibility decision',required.stderr);self.assertIn(message,required.stderr)
                included=freeze(flagged,'include');self.assertEqual(included.returncode,0,included.stderr);self.assertIn(flagged['id'],frozen_ids())
        # Go cases whose control is not applicable (no second cache in use) need no decision; below the floor nothing freezes.
        relaxed=freeze({**records[0],'cache_control':{'applicable':False}});self.assertEqual(relaxed.returncode,0,relaxed.stderr)
        excluded=freeze({**records[0],'prep_control':{'broken_compiles':False}},'exclude')
        self.assertNotEqual(excluded.returncode,0);self.assertIn('floor 8',excluded.stderr)
    def test_empty_candidate_queue_exits_without_waiting(self):
        (self.root/'cases').mkdir();(self.root/'mining').mkdir();(self.root/'bin').mkdir()
        for name in ('pipeline.sh','claim.py'):shutil.copyfile(R/'cases'/name,self.root/'cases'/name)
        for lang in ('go','python'):(self.root/f'mining/candidates-{lang}.jsonl').write_text('')
        kubectl=self.root/'bin/kubectl';kubectl.write_text('#!/bin/sh\nexit 0\n');kubectl.chmod(0o755)
        run=subprocess.run(['bash','cases/pipeline.sh','test'],cwd=self.root,env={**os.environ,'PATH':str(self.root/'bin')+':'+os.environ['PATH']},capture_output=True,text=True,timeout=5)
        self.assertEqual(run.returncode,0,run.stderr);self.assertIn('no unclaimed candidate; done',run.stdout)

class JudgeRequests(unittest.TestCase):
    def request(self,content_type,origin):
        with tempfile.TemporaryDirectory(prefix='judge-security-') as temp:
            handler=object.__new__(judge.Handler);handler.path='/api/verdict'
            handler.server=types.SimpleNamespace(server_address=('127.0.0.1',8791));handler.headers=email.message.Message()
            body=json.dumps({'packet':'p','verdict':'equivalente'}).encode()
            for key,value in {'Host':'127.0.0.1:8791','Content-Type':content_type,'Content-Length':str(len(body))}.items():handler.headers[key]=value
            if origin is not None:handler.headers['Origin']=origin
            handler.rfile=io.BytesIO(body);handler.vpath=str(pathlib.Path(temp)/'verdicts.jsonl')
            handler.packets=[{'id':'p','project':'fixture','excluded':False,'hidden':'none','patch_hash':'hash','second':None}]
            sent=[];handler.send=lambda status,*args:sent.append(status)
            handler.do_POST();return sent[-1],pathlib.Path(handler.vpath).exists()
    def test_cross_origin_and_simple_posts_cannot_write(self):
        self.assertEqual(self.request('text/plain','http://evil.invalid'),(415,False))
        self.assertEqual(self.request('application/json','http://evil.invalid'),(403,False))
        self.assertEqual(self.request('application/json','null'),(403,False))
    def test_same_origin_json_and_non_browser_clients_work(self):
        self.assertEqual(self.request('application/json','http://127.0.0.1:8791'),(200,True))
        self.assertEqual(self.request('application/json',None),(200,True))

if __name__=='__main__':unittest.main()
