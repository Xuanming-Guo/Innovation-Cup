"""Author fixed tiny replay examples. Never runs a planner or imports gold/scoring.

The Hikari/incident intervals below are manually specified examples, not product
captures. Changing them requires a new recording version and new input hashes.
"""
from pathlib import Path

from coordination_sim.benchmark.contracts import Acceptance, Outcome, Segment, Span
from coordination_sim.benchmark.generation import apply_change, change, generate
from coordination_sim.benchmark.sut import CapturedProjection, ReplayFrame, ReplayRecording, ResponseRequest
from coordination_sim.benchmark.trace import Trace
from coordination_sim.benchmark.workspaces import authorised_manifest
from coordination_sim.serialization import digest, write_json


def author():
    initial=generate();state=initial;frames=[]
    authored={"A":{"h0":(0,4),"h1":(8,12),"h2":(16,20),"h3":(20,24),"h4":(24,28)},
              "B":{"h0":(0,4),"h1":(8,12),"h2":(18,22),"h3":(22,26),"h4":(26,30),
                   "i0":(4,6),"i1":(6,10),"i2":(10,12),"i3":(16,18),"i4":(18,20)}}
    for case,intervals in authored.items():
        event=change(case);snapshot=apply_change(state,event)
        tasks={t.task_id:t for t in snapshot.tasks}
        schedule={b.task_id:b for b in state.schedule}
        for tid,(start,end) in intervals.items():
            schedule[tid]=Segment(block_id=f'b-{tid}',company_id=state.company.company_id,task_id=tid,
                                 employee_id=tasks[tid].eligible_owners[0],span=Span(start=start,end=end))
        blocks=tuple(sorted(schedule.values(),key=lambda b:b.block_id))
        considered=tuple(sorted(set(intervals)))
        accepts=tuple(Acceptance(task_id=tid,reviewer_id=tasks[tid].reviewer_id or b.employee_id,
                      submission_version='authored-1',accepted_slot=max(b.span.end,schedule[tasks[tid].review_task_id].span.end) if tasks[tid].review_task_id else b.span.end,
                      evidence_ref=f'authored-duration:{tid}') for tid,b in sorted(schedule.items()))
        outcome=Outcome(method='product_replay',classification='FEASIBLE',terminal='COMPLETED',schedule=blocks,
                        considered_task_ids=considered,iterations=0,plan_versions=0,acceptances=accepts,
                        actual_starts={tid:b.span.start for tid,b in schedule.items()},
                        reason='Authored contract example; no product or internal workflow executed.')
        next_state=snapshot.model_copy(update={'schedule':blocks,'revision':state.revision+1})
        projections=[]
        for viewer,role in [('e0000','manager'),('e0006','employee'),('e0008','employee')]:
            allowed_sources={g.resource_id for g in snapshot.grants if g.principal_id==viewer and not g.revoked}
            briefs=[b for b in snapshot.briefs if viewer in b.audience and not b.revoked]
            allowed_briefs={b.brief_id for b in briefs}
            visible=[t for t in snapshot.tasks if t.brief_id in allowed_briefs and (viewer in t.eligible_owners or role=='manager' and t.project_id=='hikari')]
            cards=[{'task_id':t.task_id,'title':t.title,'purpose':t.purpose,'deliverable':t.deliverable,
                    'acceptance_criteria':list(t.acceptance_criteria),'effort_minutes':t.effort_slots*15,
                    'window':t.window.model_dump(),'suggested_segments':[schedule[t.task_id].span.model_dump()],
                    'deadline_slot':t.agreed_deadline_slot,'reviewer':t.reviewer_id,
                    'dependencies':[d.predecessor for d in t.dependencies if d.predecessor in {x.task_id for x in visible}],
                    'brief':next(b.text for b in briefs if b.brief_id==t.brief_id),
                    'next_action':'Inspect this authored replay; no live task action is available.',
                    'reason':'Confirmed task capability and explicit access in this synthetic example.'} for t in visible]
            before_cards=[{'task_id':b.task_id,'span':b.span.model_dump(),'employee_id':b.employee_id} for b in state.schedule if b.task_id in {t.task_id for t in visible}]
            projections.append(CapturedProjection(viewer_id=viewer,role=role,
                permitted_source_refs=tuple(sorted(allowed_sources & {s for t in visible for s in t.required_sources})),
                brief_refs=tuple(sorted({t.brief_id for t in visible})),panels={
                    'notice':'Authored synthetic projection. Product interpretation, insertion, approval, commitment, sync and acceptance states are NOT_AVAILABLE.',
                    'request':event.summary if case=='A' else 'A higher-priority reservation changes shared capacity; restricted incident details omitted.',
                    'before':before_cards,'today':cards,'upcoming':[],'blocked':[],'submitted':[],
                    'opaque_reservations':[{'label':'Protected commitment','span':r.span.model_dump()} for r in snapshot.reservations if r.employee_id==viewer or role=='manager' and r.employee_id=='e0006'],
                    'scope':{'visible_tasks':len(visible),'company_tasks':len(snapshot.tasks),'company_employees':len(snapshot.employees)},
                    'clarifications':[],'approval':'NOT_AVAILABLE','pinned_insertion':'NOT_AVAILABLE',
                    'source_basis':sorted(allowed_sources & set(event.source_refs)),
                    'unchanged_task_ids':[b.task_id for b in state.schedule if b.task_id in {t.task_id for t in visible} and schedule[b.task_id]==b]}))
        trace=Trace('author',snapshot.company)
        manifest=authorised_manifest(snapshot,event,trace,'product_replay')
        request=ResponseRequest(request_id=f'{case}-ack',actor_id='e0006',kind='acknowledge',exact_version='authored-1',permitted_answer='acknowledged')
        frames.append(ReplayFrame(scenario_id=case,event_digest=digest(event),input_digest=digest(manifest),
            before_digest=digest(state),after_snapshot_digest=digest(next_state),requests=(request,),
            observations=({'event_id':f'authored-{case}-1','summary':'Authored terminal schedule is available for harness replay; product internals were not observed.','state':'RECORDED_EXAMPLE'},),
            projections=tuple(projections),outcome=outcome))
        state=next_state
    return ReplayRecording(recording_version='tiny-connected-authored-2',initial_digest=digest(initial),frames=tuple(frames))


if __name__=='__main__':
    path=Path('fixtures/replays/tiny-connected.v2.json')
    write_json(path,author())
    print(path)
