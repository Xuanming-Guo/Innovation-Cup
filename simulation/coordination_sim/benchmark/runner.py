"""Run immutable independent method attempts, preserve failures and evidence."""
import hashlib
import json
import platform
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

from .. import REPLAY_LABEL
from ..runner import ROOT, git_head, run_directory
from ..serialization import canonical, digest, write_json
from . import VERSION
from .contracts import Outcome, Snapshot
from .generation import apply_change, change, generate, truth
from .inspector import company_inspector, coordination_graph
from .metrics import aggregate, compute, headline, product_cells, registry
from .naive import NaiveCoordinator
from .sut import DeterministicActors, ProductUnavailable, RecordedReplay, check_mapping
from .trace import Trace
from .validation import validate
from .workspaces import authorised_manifest

RECORDING=ROOT/'fixtures/replays/tiny-connected.v2.json'


def implementation_digest():
    paths=[*sorted((ROOT/'coordination_sim').rglob('*.py')),*sorted((ROOT/'ui').glob('*')),
           *sorted((ROOT/'evals').glob('*.json')),*sorted((ROOT/'metrics').glob('*.json')),ROOT/'pyproject.toml',ROOT/'uv.lock']
    return digest({str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths if p.is_file()})


def run(*,preset='tiny',seed=17,cases=('A','B'),run_id=None,replay_path=RECORDING,iteration_cap=200):
    run_id=run_id or f'benchmark-{uuid.uuid4().hex}'
    target=run_directory(run_id)
    started=datetime.now(timezone.utc).isoformat();wall=time.monotonic()
    trace=None;attempts=[];cells=[];rows=[];fatal=None
    try:
        initial=generate(preset,seed)
        write_json(target/'initial.json',initial)
        write_json(target/'company-inspector.json',company_inspector(initial))
        initial_outcome=Outcome(method='naive',classification='FEASIBLE',terminal='COMPLETED',schedule=initial.schedule,
                                considered_task_ids=(),iterations=0,plan_versions=0)
        initial_report=validate(initial,initial_outcome)
        write_json(target/'initial-validation.json',initial_report)
        if initial_report.violations:raise ValueError('INITIAL_FIXTURE_INVALID')
        trace=Trace(run_id,initial.company,target/'trace.jsonl')
        trace.emit('fixture_generated','Generated coherent synthetic company and validated its initial concrete schedule.',
                   outputs=('initial.json','initial-validation.json'),after=digest(initial))
        write_json(target/'metric-registry.json',registry())
        write_json(target/'product-capabilities.json',ProductUnavailable().discover())
        replay=None
        if preset=='tiny' and seed==17 and tuple(cases[:2])==('A','B'):
            try:
                recording_bytes=Path(replay_path).read_bytes()
                with (target/'replay-recording.json').open('xb') as f:f.write(recording_bytes)
                replay=RecordedReplay(target/'replay-recording.json',trace)
                write_json(target/'replay-capabilities.json',replay.discover())
                replay.reset(initial.company.company_id);replay.seed(initial)
            except (OSError,ValueError):
                replay=None
                trace.emit('replay_unavailable','No matching versioned replay for this seed/preset; no schedule substituted.',
                           approach='product_replay',origin='replay',status='failed',error='REPLAY_UNAVAILABLE')
        states={'naive':initial,'product_replay':initial}
        for case in cases:
            event=change(case)
            scenario_observations={}
            canonical_inputs={}
            for method in ('naive','product_replay'):
                if method=='product_replay' and (replay is None or case not in ('A','B')):continue
                before=states[method]
                snapshot=apply_change(before,event)
                folder=target/f'{case}-{method}';folder.mkdir()
                prefix=folder.name+'/'
                write_json(folder/'before.json',before)
                write_json(folder/'event.json',event)
                write_json(folder/'input.json',snapshot)
                gold=truth(snapshot,event);write_json(folder/'ground-truth.json',gold)
                first=len(trace.rows);retrieval=time.monotonic()
                manifest=authorised_manifest(snapshot,event,trace,method)
                retrieval_ms=(time.monotonic()-retrieval)*1000
                write_json(folder/'input-manifest.json',manifest)
                canonical_inputs[method]=manifest
                mapping=check_mapping(manifest,json.loads(canonical(manifest)))
                write_json(folder/'mapping.json',mapping)
                trace.emit('change_received',event.summary,scenario=case,approach=method,actor=event.actor_id,
                           role='requesting_actor',phase='request',at=event.at_slot,
                           inputs=(prefix+'event.json',prefix+'input-manifest.json'),sources=event.source_refs,before=digest(before))
                start=time.monotonic()
                failure=None
                try:
                    if method=='naive':outcome=NaiveCoordinator(iteration_cap).run(snapshot,event,trace)
                    else:
                        requests=replay.submit(event,manifest)
                        actors=DeterministicActors(snapshot,trace)
                        for request in requests:replay.respond(actors.answer(request,case,method))
                        replay.observe()
                        projections=[replay.capture(person) for person in ('e0000','e0006','e0008')]
                        write_json(folder/'projections.json',[p.model_dump(mode='json') for p in projections])
                        outcome=replay.export()
                except (ValueError,NotImplementedError):
                    failure='ADAPTER_CONTRACT_FAILURE'
                    outcome=Outcome(method=method,classification='UNKNOWN',terminal='FAILED',schedule=(),considered_task_ids=(),
                                    iterations=0,plan_versions=0,reason=failure)
                    trace.emit('run_failed','Adapter evidence unavailable or incompatible; failed attempt retained.',
                               scenario=case,approach=method,status='failed',error=failure)
                planning_ms=(time.monotonic()-start)*1000
                write_json(folder/'outcome.json',outcome)
                write_json(folder/'coordination-graph.json',coordination_graph(snapshot,event,outcome))
                validation_start=time.monotonic();report=validate(snapshot,outcome,event.at_slot)
                validation_ms=(time.monotonic()-validation_start)*1000
                write_json(folder/'validation.json',report)
                trace.emit('candidate_validated',f'Neutral concrete validation recorded {len(report.violations)} violations.',
                           scenario=case,approach=method,phase='validation',status='failed' if report.violations else 'succeeded',
                           inputs=(prefix+'input.json',prefix+'outcome.json'),outputs=(prefix+'validation.json',),after=digest(report))
                events=trace.rows[first:]
                write_json(folder/'events.json',events)
                observations=compute(snapshot,outcome,report,events,run_id=run_id,scenario=case,event_slot=event.at_slot,
                    expected_classification=gold.expected_classification,stage_ms={'fixture_retrieval':retrieval_ms,'naive_planning':planning_ms,'neutral_validation':validation_ms},
                    artifact_prefix=prefix,input_bytes=len(canonical(manifest)),before_snapshot=before)
                write_json(folder/'metrics.json',[o.model_dump(mode='json') for o in observations])
                scenario_observations[method]=observations
                trace.emit('metric_recorded','Calculated versioned observations from concrete artifacts and factual events.',
                           scenario=case,approach=method,outputs=(prefix+'metrics.json',))
                # This is only comparator/replay state progression. No transaction
                # service, approvals or product commit is emulated here.
                if outcome.terminal=='COMPLETED' and not report.violations:
                    states[method]=snapshot.model_copy(update={'schedule':outcome.schedule,'revision':before.revision+1})
                attempt={'scenario':case,'method':method,'classification':outcome.classification,
                         'terminal':outcome.terminal,'expected':gold.expected_classification,
                         'violations':len(report.violations),'input_digest':digest(manifest),'outcome_digest':digest(outcome),
                         'before_digest':digest(before),'after_digest':digest(states[method]),'path':prefix,'failure':failure}
                attempts.append(attempt)
                if method=='naive':rows.append(attempt)
            products=product_cells(run_id,case)
            cells.extend(o.model_dump(mode='json') for o in products)
            if 'naive' in scenario_observations:
                mapping=check_mapping(canonical_inputs['naive'],canonical_inputs.get('product_replay',canonical_inputs['naive']))
                write_json(target/f'{case}-comparison-mapping.json',mapping)
                write_json(target/f'{case}-headlines.json',headline(scenario_observations['naive'],products,mapping))
        write_json(target/'product-metrics.json',cells)
        write_json(target/'aggregate.json',aggregate(rows))
        write_json(target/'attempts.json',attempts)
        # Judge payload deliberately contains only captured POVs, calculated metrics
        # and judge trace. Employee mode never builds cards from full snapshots.
        judge_cases=[]
        for case in cases:
            methods={}
            for method in ('naive','product_replay'):
                folder=target/f'{case}-{method}'
                if not folder.exists():continue
                methods[method]={'metrics':json.loads((folder/'metrics.json').read_text()),
                                 'outcome':next(x for x in attempts if x['scenario']==case and x['method']==method),
                                 'graph':json.loads((folder/'coordination-graph.json').read_text()),
                                 'projections':json.loads((folder/'projections.json').read_text()) if (folder/'projections.json').exists() else []}
            judge_cases.append({'id':case,'summary':change(case).summary,'methods':methods,
                                'product':[o for o in cells if o['scenario_id']==case]})
        payload={'label':'SYNTHETIC BENCHMARK — '+REPLAY_LABEL,'product_status':'NOT_RUN',
                 'run_id':run_id,'company':{'employees':len(initial.employees),'teams':len(initial.teams),'projects':len(initial.projects),'tasks':len(initial.tasks),'preset':preset},
                 'company_inspector':json.loads((target/'company-inspector.json').read_text()),
                 'cases':judge_cases,'registry':registry(),'events':trace.rows,'attempts':attempts}
        write_json(target/'judge-data.json',payload)
        from .presentation import export_html
        export_html(target,payload)
        trace.emit('run_completed','Harness attempts recorded; Section 13.2 remains NOT_RUN.',outputs=('manifest.json',))
        trace.export(target)
    except (OSError,ValueError,KeyError) as exc:
        fatal=type(exc).__name__  # Never expose arbitrary source bodies in exception strings.
        if trace:trace.emit('run_failed','Harness setup failed; artifacts retained.',status='failed',error=fatal)
    manifest={'specification_version':'0.5.0','harness_version':VERSION,'schema_version':'benchmark-2','run_id':run_id,
              'label':'SYNTHETIC BENCHMARK','replay_label':REPLAY_LABEL,'product_status':'NOT_RUN',
              'status':'FAILED' if fatal else 'COMPLETED','fatal_error':fatal,'seed':seed,'preset':preset,'cases':list(cases),
              'started_at':started,'ended_at':datetime.now(timezone.utc).isoformat(),'harness_wall_seconds':time.monotonic()-wall,
              'harness_git_head':git_head(),'implementation_digest':implementation_digest(),
              'lock_sha256':hashlib.sha256((ROOT/'uv.lock').read_bytes()).hexdigest(),
              'hardware':{'os':platform.system(),'release':platform.release(),'machine':platform.machine(),'python':platform.python_version()},
              'limits':{'naive_iteration_cap':iteration_cap,'slot_minutes':15,'horizon_days':5},
              'method_versions':{'naive':'greedy-cascade-1','replay':'recorded-1','validator':'neutral-2','metrics':'2'},
              'product_versions':{'commit':'NOT_AVAILABLE','api':'NOT_AVAILABLE','model':'NOT_AVAILABLE','solver':'NOT_AVAILABLE','compiler':'NOT_AVAILABLE'},
              'connector_modes':{p:'simulated' for p in ('teams','calendar','planner','sharepoint','github')},
              'deterministic_trace_digest':trace.semantic_digest() if trace else None,
              'runtime_exclusions':['run_id','recorded_at','started_at','ended_at','harness_wall_seconds','stage_ms'],
              'attempts':attempts,'artifact_sha256':{str(p.relative_to(target)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(target.rglob('*')) if p.is_file()}}
    write_json(target/'manifest.json',manifest)
    return target
