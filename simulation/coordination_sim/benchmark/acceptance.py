"""Reproducible local acceptance evidence; never rubber-stamp unavailable QA."""
import json
import subprocess
import sys
import uuid

from ..runner import ROOT, run_directory
from ..serialization import write_json
from .contracts import Outcome
from .generation import generate, second_tenant_probe
from .runner import run
from .validation import validate


def acceptance():
    target=run_directory(f'acceptance-{uuid.uuid4().hex}')
    checks=[]

    def command(name,args):
        result=subprocess.run(args,cwd=ROOT,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
        (target/f'{name}.txt').write_text(result.stdout)
        checks.append({'id':name,'status':'PASS' if result.returncode==0 else 'FAIL','command':args,'exit_code':result.returncode,'evidence':f'{name}.txt'})
        return result.returncode==0

    command('python-tests',[sys.executable,'-B','-m','unittest','discover','-s','tests','-v'])
    connected=run()
    m=json.loads((connected/'manifest.json').read_text())
    main_ok=m['status']=='COMPLETED' and len(m['attempts'])==4 and all(a['terminal']=='COMPLETED' and a['violations']==0 for a in m['attempts'])
    checks.append({'id':'tiny-connected','status':'PASS' if main_ok else 'FAIL','evidence':str(connected.relative_to(ROOT))})
    command('javascript-syntax',['node','--check','ui/app.js'])
    command('ui-logic',['node','tests/ui.test.cjs',str(connected/'judge-data.json')])
    for preset in ('medium','demo'):
        snapshot=generate(preset)
        o=Outcome(method='naive',classification='FEASIBLE',terminal='COMPLETED',schedule=snapshot.schedule,considered_task_ids=(),iterations=0,plan_versions=0)
        v=validate(snapshot,o)
        write_json(target/f'{preset}-validation.json',v)
        checks.append({'id':f'{preset}-initial','status':'PASS' if not v.violations else 'FAIL',
                       'employees':len(snapshot.employees),'teams':len(snapshot.teams),'projects':len(snapshot.projects),'tasks':len(snapshot.tasks),
                       'evidence':f'{preset}-validation.json'})
    write_json(target/'second-tenant.json',second_tenant_probe())
    command('repository-guards',[sys.executable,'-B','scripts/check_repository.py'])
    qa_path=ROOT/'evals/browser-qa/manifest.json'
    qa=json.loads(qa_path.read_text()) if qa_path.exists() else {'checks':[]}
    qa_checks={item['id']:item for item in qa['checks']}
    evidence_files={name for item in qa['checks'] for name in item.get('evidence',[])}
    archived_ok=(qa_checks.get('loopback-page-load',{}).get('status')=='PASS' and
                 qa_checks.get('desktop-overview-scorecard-trace',{}).get('status')=='PASS' and
                 all((qa_path.parent/name).is_file() for name in evidence_files))
    checks.extend([
       {'id':'archived-browser-desktop-povs','status':'PASS' if archived_ok else 'FAIL',
        'evidence':'evals/browser-qa/manifest.json',
        'scope':'Pre-inspector 0.2.0 desktop overview and manager/Security/Delivery projections.'},
       {'id':'loopback-service','status':'PASS' if qa_checks.get('loopback-page-load',{}).get('status')=='PASS' else 'NOT_RUN',
        'evidence':'evals/browser-qa/overview-1.png',
        'scope':'Repository-user execution at 127.0.0.1:8765; current command does not reopen the listener.'},
       {'id':'current-company-graph-inspector-browser','status':'NOT_RUN',
        'prerequisite':'Fresh browser interaction after the inspector implementation; current browser discovery returned no connected browser.',
        'evidence':'evals/browser-qa/README.md'},
       {'id':'browser-narrow-layout','status':'NOT_RUN',
        'prerequisite':'A narrow/mobile viewport browser pass and retained screenshot.',
        'evidence':'evals/browser-qa/manifest.json'}])
    failed=any(c['status']=='FAIL' for c in checks)
    pending=any(c['status']=='NOT_RUN' for c in checks)
    report={'specification_version':'0.5.0','harness_version':'0.3.0',
            'section_13_1':'FAIL' if failed else 'BLOCKED' if pending else 'PASS',
            'section_13_2':'NOT_RUN','automated_checks_passed':all(c['status']!='FAIL' for c in checks),
            'checks':checks,'golden_cases':8,'generated_expansion_cases':0,'held_out_cases':0,
            'review_scope':'Manual arithmetic/trace review by implementing orchestrator; not external human/customer validation.',
            'judge_replay':str((connected/'judge.html').relative_to(ROOT)),
            'note':'Archived screenshots close the prior desktop/loopback evidence gap. The newly added inspector and narrow layout remain NOT_RUN until fresh browser evidence is retained.'}
    write_json(target/'acceptance.json',report)
    return target,report['section_13_1']=='PASS'
