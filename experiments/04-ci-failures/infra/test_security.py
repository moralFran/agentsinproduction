#!/usr/bin/env python3
"""Post-collection security/regression controls. Synthetic repositories and temporary files only; no provider or cluster.
Manifest checks establish mount contracts, not proof of isolation on a live Kata node. Run: python3 -B infra/test_security.py
"""
import contextlib, csv, email.message, importlib.util, io, json, os, pathlib, shlex, shutil, subprocess, sys, tempfile, types, unittest, warnings
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
            for role,action in [('agent',[]),('exec',['validate','suite']),('exec',['validate','hidden']),('exec',['repro','fixed','3'])]:
                with self.subTest(language=language,role=role,action=action):
                    cmd=['python3','/code/agent.py'] if role=='agent' else ['python3','-u','/code/executor.py',*action]
                    spec=pods.build_spec(role,'fixture','pod',900,cmd,{'language':language},secret_meta={'hidden_cmd':'hidden-test','fix_sha':'DO_NOT_EXPOSE'})
                    mounts=spec['spec']['containers'][0]['volumeMounts']; paths={m['mountPath'] for m in mounts}
                    self.assertNotIn('/in/secret',paths);self.assertNotIn('DO_NOT_EXPOSE',json.dumps(spec))
                    self.assertEqual('/in/fix.diff' in paths,action[:2]==['repro','fixed'])
                    self.assertEqual('/in/hidden.diff' in paths,action[:2]==['repro','fixed'])
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
        for outcome in ('ci_still_red','did_not_apply','rejected_by_validator','ci_flaky_after_patch','hidden_tests_did_not_apply','hidden_tests_flaky','infra_error','timeout',None):
            self.assertIsInstance(tally.final({'executor':{'outcome':outcome},'agent':{}},{},{}),str)
        expected={'finished':'desistiu','timeout':'parou por tempo','max_tool_calls':'parou por limite de ferramentas','error':'erro do agente','budget_exhausted':'parou por orçamento'}
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
        self.assertEqual(result['outcome'],'rejected_by_validator');self.assertIn('core.py',result['why'])
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
    def test_agent_shell_reports_pipeline_failure(self):
        case=self.root/'ci/cases/fixture';case.mkdir(parents=True);(case/'repo').mkdir()
        (case/'meta.json').write_text(json.dumps({'language':'Python'}));(case/'failure.txt').write_text('test failed')
        code=self.root/'code';code.mkdir();(code/'prompt-v1.txt').write_text('synthetic {language} case')
        script=self.root/'agent.py';script.write_text((R/'agent/agent.py').read_text().replace('/srv/ci',str(self.root/'ci')).replace('/code/',str(code)+'/'))
        with warnings.catch_warnings(),patch.dict(sys.modules,{'anthropic':types.ModuleType('anthropic')}),patch.dict(os.environ,{'CASE_ID':'fixture','RUN_ID':'fixture'}):
            warnings.simplefilter('ignore',ResourceWarning)
            agent=module('security_agent',script)
        rc,_,_=agent.bash('false | tail -1',5)
        self.assertNotEqual(rc,0)
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
                         'hidden-broken':{'runs':runs(broken)} if broken is not None else {}}
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
        (cases/'pod.py').write_text('print(\'RESULT {"outcome":"finished","patch":"synthetic patch"}\')\n')
        (cases/'validate.py').write_text('print(\'EXECUTOR {"outcome":"ci_still_red"}\')\n')
        curl=bin_dir/'curl';curl.write_text('#!'+sys.executable+'\nimport json,sys\n'
            'sys.stdin.read()\nwith open("gateway-calls.jsonl","a") as f: f.write(json.dumps(sys.argv[1:])+"\\n")\n'
            'print(json.dumps({"spent_usd":0.01,"calls":1,"cap_usd":0.33}))\n');curl.chmod(0o755)
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
        requests=self.root/'gateway-calls.jsonl';calls=[json.loads(line) for line in requests.read_text().splitlines()]
        opened=[args for args in calls if any(a.endswith('/runs') for a in args)]
        self.assertEqual(len(opened),6)
        before=(journal.read_bytes(),requests.read_bytes())
        shutil.rmtree(ci)  # completed records need neither prepared trees nor the gateway credential
        again=subprocess.run(command,cwd=self.root,env=env,capture_output=True,text=True)
        self.assertEqual(again.returncode,0,again.stdout+again.stderr)
        self.assertEqual((journal.read_bytes(),requests.read_bytes()),before)

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
