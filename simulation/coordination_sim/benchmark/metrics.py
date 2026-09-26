"""Evidence-backed scorecard. Replay never enters product headline arithmetic."""
from collections import Counter, defaultdict
from statistics import median, quantiles

from pydantic import Field, model_validator
from ..contracts import Contract
from .contracts import Outcome, Snapshot, Validation

PRIMARY = {
 'changed_commitments': ('Existing commitments changed','commitments','Distinct pre-existing tasks/blocks with owner, start/end, agreed deadline, protection or cancellation changes.'),
 'owner_churn': ('Owner churn','tasks','Distinct pre-existing tasks with changed owners; started and cross-team subsets.'),
 'displacement': ('Schedule displacement','minutes','Absolute start shifts of matched pre-existing blocks; sum, median, maximum and distribution. Unmatched blocks listed separately.'),
 'preservation': ('Preservation rate','ratio','Unchanged pre-existing tasks within the method-declared affected scope / all pre-existing affected tasks.'),
 'replans': ('Replan iterations / plan versions','attempts','Local planning iterations, cascade cycles and generated plan versions before any terminal state.'),
 'late_conflicts': ('Late conflict discoveries','conflicts','Logged collisions/precedence conflicts first discovered after a local proposal.'),
 'contacts': ('People contacted / interrupted','people','Unique recipients of coordination, clarification, approval and changed-task messages.'),
 'relay_hops': ('Coordination relay hops','edges','Reporting/project graph edges traversed by each normalised material fact.'),
 'duplicate_transmissions': ('Duplicate information transmissions','transmissions','Repeated (normalised fact, recipient) deliveries after the first within the scenario.'),
 'clarifications_approvals': ('Clarifications / approvals','actions','Required clarification, avoidable reconstruction, required approval requests and actual decisions reported separately.'),
 'invalid_delegations': ('Invalid task delegations','ratio','Distinct assigned tasks with at least one independent hard failure / distinct assigned tasks. Missing tasks remain in hard violations.'),
 'capacity_overload': ('Capacity overload','minutes','Sum over person-slots of max(0, occupancy - 1), times 15; overlap pairs and maximum daily ratio.'),
 'dependency_deadlines': ('Dependency / deadline violations','violations','Precedence/lag/acceptance failures, missed original agreed deadlines and lateness minutes; requested lateness separate.'),
 'priority_service': ('Priority service time','simulated minutes','Change B injection to accepted incident resolution and latest required blocking-task acceptance; no completion inferred from a plan.'),
 'collateral': ('Lower-priority collateral damage','commitments','Pre-existing lower-priority tasks moved, deadlines/owners changed and newly affected people during Change B.'),
 'completion': ('Scenario / key-work completion','simulated minutes','Injection to accepted affected work, Hikari, incident; only when required acceptance evidence exists.'),
 'hard_violations': ('Hard-constraint violations','violations','Neutral validation record count and breakdown by category; not a count of unique invalid tasks.'),
 'source_authority': ('Source / authority failures','violations','Unsupported constraints, unapproved priority/deadline movement and other out-of-authority records.'),
 'scope': ('Affected-scope size','entities','Distinct employees, teams, projects and tasks read/replanned/notified versus full company; percent excluded.'),
 'planning_latency': ('Planning latency and model size','milliseconds','Actually measured stage runtimes, separate from simulated duration; unexposed product/solver dimensions remain null.'),
}
EXTRA = {
 'terminal_classification': ('Terminal classification accuracy','cases','Expected generator class versus observed class; all attempted cases included.'),
 'false_success': ('False-success rate','ratio','Claimed completed outcomes failing independently checked requirements / all attempted outcomes.'),
 'correct_replan': ('Correct replan rate','ratio','Accepted authorised independently valid correctly committed communicated outcomes / all eligible attempts; product lifecycle evidence required.'),
 'commit_safety': ('Commit safety','ratio','Independently invalid committed outcomes / outcomes with observed exact internal commitment.'),
 'deadline_movement': ('Deadline movement','minutes','Requested→agreed, prior agreed→new agreed and agreed→forecast deltas; changes never erase original deadlines.'),
 'fragmentation': ('Fragmentation and continuity','segments','Segment counts, extra starts, minimum-run violations and handoffs.'),
 'workload_balance': ('Workload distribution','minutes','Scheduled active minutes per affected employee; never a performance grade.'),
 'source_grounding': ('Source grounding','ratio','Material fixture constraints with current authoritative lineage; not model extraction accuracy.'),
 'privacy': ('Authority / privacy failures','violations','Neutral source, approval, movement and disclosure failure records.'),
 'boundary_facts': ('Boundary fact use','reservations','Opaque reservations for considered employees; no private titles.'),
 'action_burden': ('Coordination action burden','actions','Deterministic clarification, approval, review, correction, relay and failed attempts.'),
 'communication': ('Communication correctness','recipients','Required changed-work owners versus recorded recipients; forbidden disclosures independently counted.'),
 'partial_failure': ('Partial-failure honesty','cases','Observed external per-action failures distinguish partial from success; only with sync evidence.'),
 'objective_vector': ('Objective vector','vector','Verbatim product objective metadata only; never inferred from final schedule.'),
 'execution_safety': ('Execution safety','effects','Wrong/duplicate/stale/unapproved provider effects with exact external evidence.'),
 'recovery': ('Recovery correctness and attempts','attempts','Observed reconciliation/crash/retry results; provider fixture operations are not product recovery.'),
 'refresh': ('Refresh / reconnect reliability','notifications','Persisted notification/refetch evidence after lost signals; unavailable until product supports it.'),
 'end_to_end_latency': ('Correct committed communicated latency','milliseconds','Monotonic submission to independently correct committed communicated terminal state; no schedule advancement.'),
 'resources': ('Resource usage','operations','Actual fixture read/write pages, events and input bytes; unavailable tokens/CPU/memory remain null.'),
 'cost': ('Cost per accepted replan','currency','Requires attributable usage, accepted product outcomes and versioned price configuration.'),
 'interpretation': ('Interpretation accuracy','ratio','Requires real product structured interpretation plus reviewed expected constraints and mode metadata.'),
 'retrieval_accuracy': ('Relevant evidence retrieval','ratio','Requires reviewed relevance labels; all permitted facts are not automatically relevant.'),
 'estimate_quality': ('Estimate quality','minutes','Chronologically held-out accepted active-effort errors with sample counts; missing effort excluded explicitly.'),
 'estimator_comparison': ('Estimator comparison','minutes','Class prior / skills-only / recent-context methods on identical held-out evidence.'),
 'evidence_maturity': ('Evidence maturity correctness','violations','Requires observed versioned learning evidence; assignment and waiting are not accepted skill.'),
 'profile_corrections': ('Profile correction integrity','versions','Requires observed superseding correction versions and reproducible old snapshots.'),
 'employee_control': ('Employee-control events','events','Observed estimate/access/input objections, corrections and resolutions; no employee scoring.'),
 'stale_concurrent': ('Stale / concurrent commit safety','attempts','Requires product revision rechecks and exact competing commit evidence.'),
}


def registry():
    return {'schema_version':'metric-registry-2','definition_version':'1','metrics':[
        {'metric_id':key,'name':name,'unit':unit,'definition':definition,'primary':key in PRIMARY,
         'definition_version':'1','direction_if_any':None,
         'eligibility_rule':'All attempted cases retained. Evidence-dependent fields use null plus a reason; no silent exclusions.',
         'denominator':'Defined raw denominators appear in each value. Zero denominators produce null rates.',
         'exclusions':'No failed/unknown/timeout/partial cases dropped. Real-world human productivity is outside scope.'}
        for key,(name,unit,definition) in {**PRIMARY,**EXTRA}.items()]}


class Observation(Contract):
    metric_schema_version: str = '2'
    metric_definition_version: str = '1'
    metric_id: str
    run_id: str
    scenario_id: str
    approach_or_condition: str
    evidence_class: str
    unit: str
    direction_if_any: str | None = None
    eligibility_rule: str
    numerator_and_denominator_refs: tuple[str,...]
    source_event_or_artifact_refs: tuple[str,...]
    value: dict | float | int | list | str | None
    status: str
    missing_or_invalid_reason: str | None = None

    @model_validator(mode='after')
    def honest(self):
        if self.status=='MEASURED':
            if self.value is None or self.missing_or_invalid_reason: raise ValueError('measured evidence missing')
        elif self.status in ('NOT_MEASURED','NOT_APPLICABLE','INVALID','NOT_RUN'):
            if self.value is not None or not self.missing_or_invalid_reason:raise ValueError('missing evidence must be null with reason')
        else:raise ValueError('unknown metric status')
        return self


def ratio(n,d):return n/d if d else None


def compute(snapshot:Snapshot,outcome:Outcome,report:Validation,events:list,*,run_id,scenario,event_slot,expected_classification,
            stage_ms=None,artifact_prefix='',input_bytes=0,before_snapshot=None):
    definitions={r['metric_id']:r for r in registry()['metrics']}
    before,after=defaultdict(list),defaultdict(list)
    for b in snapshot.schedule:before[b.task_id].append(b)
    for b in outcome.schedule:after[b.task_id].append(b)
    tasks={t.task_id:t for t in snapshot.tasks};employees={e.employee_id:e for e in snapshot.employees}
    pre=set(before);assigned=set(after)
    prior_tasks={t.task_id:t for t in (before_snapshot or snapshot).tasks}
    changed=set();breakdown={k:[] for k in ('owner','start_end','deadline','protection','cancellation')}
    changed_blocks=set();shifts=[];unmatched=[]
    owners_before={tid:{b.employee_id for b in rows} for tid,rows in before.items()}
    owners_after={tid:{b.employee_id for b in rows} for tid,rows in after.items()}
    for tid,old in before.items():
        new=after[tid];task=tasks[tid]
        tests={'owner':owners_before[tid]!=owners_after.get(tid,set()),
               'start_end':[(b.block_id,b.span) for b in old]!=[(b.block_id,b.span) for b in new],
               'deadline':outcome.agreed_deadlines.get(tid,task.agreed_deadline_slot)!=prior_tasks.get(tid,task).agreed_deadline_slot,
               'protection':outcome.protected_values.get(tid,task.protected)!=task.protected,
               'cancellation':tid in outcome.cancelled_task_ids or not new}
        for kind,yes in tests.items():
            if yes:breakdown[kind].append(tid);changed.add(tid)
        mapped={b.block_id:b for b in new}
        for b in old:
            nb=mapped.get(b.block_id)
            if nb is None:unmatched.append(b.block_id);changed_blocks.add(b.block_id)
            else:
                shifts.append(abs(b.span.start-nb.span.start)*15)
                if b!=nb:changed_blocks.add(b.block_id)
    considered=set(outcome.considered_task_ids)
    affected=pre&considered
    actor_events=[r for r in events if r['scenario_id']==scenario and r['approach']==outcome.method]
    relays=[r for r in actor_events if r['action_type'] in ('notification_relayed','notification_delivered')]
    recipients={r['detail']['recipient'] for r in relays if r['detail'].get('recipient')}
    tx=Counter((r['detail'].get('fact_id'),r['detail'].get('recipient')) for r in relays)
    conflicts=[r for r in actor_events if r['action_type']=='conflict_discovered' and r['detail'].get('late')]
    clarification=[r for r in actor_events if r['action_type']=='clarification_requested']
    approvals=[r for r in actor_events if r['action_type']=='approval_decided']
    invalid={t for v in report.violations for t in v.task_ids if t in assigned}
    categories=dict(Counter(v.category for v in report.violations))
    accepted={a.task_id:a.accepted_slot for a in outcome.acceptances}
    lower={tid for tid in pre if tasks[tid].priority>0}
    incident={tid for tid,t in tasks.items() if t.project_id=='incident'}
    hikari={tid for tid,t in tasks.items() if t.project_id=='hikari'}
    blocking={d.predecessor for tid in incident for d in tasks[tid].dependencies}

    def completion(ids):
        return (max(0,max(accepted[tid] for tid in ids)-event_slot)*15) if ids and ids<=set(accepted) else None
    scoped_people={b.employee_id for tid in considered for b in after[tid]}|{o for tid in considered if tid in tasks for o in tasks[tid].eligible_owners}
    scoped_projects={tasks[tid].project_id for tid in considered if tid in tasks}
    scoped_teams={tasks[tid].team_id for tid in considered if tid in tasks}
    def sizes(tids,people=None):
        people=people if people is not None else {b.employee_id for tid in tids for b in after[tid]}
        return {'tasks':len(tids),'employees':len(people),'teams':len({tasks[t].team_id for t in tids if t in tasks}),
                'projects':len({tasks[t].project_id for t in tids if t in tasks})}
    full={'tasks':len(tasks),'employees':len(employees),'teams':len(snapshot.teams),'projects':len(snapshot.projects)}
    read=sizes(considered,scoped_people)
    replanned={t for r in actor_events if r['action_type']=='task_assigned' for t in r['affected_entity_refs']}
    notified_tasks={t for r in relays for t in r['affected_entity_refs']}
    deadline_deltas={tid:{'requested_to_agreed':(outcome.agreed_deadlines.get(tid,t.agreed_deadline_slot)-t.requested_deadline_slot)*15,
                         'prior_to_new_agreed':(outcome.agreed_deadlines.get(tid,t.agreed_deadline_slot)-prior_tasks.get(tid,t).agreed_deadline_slot)*15,
                         'agreed_to_forecast':(max(b.span.end for b in after[tid])-outcome.agreed_deadlines.get(tid,t.agreed_deadline_slot))*15 if after[tid] else None}
                     for tid,t in tasks.items()}
    values={
      'changed_commitments':{'tasks':len(changed),'blocks':len(changed_blocks),'by_type':{k:len(v) for k,v in breakdown.items()},'task_ids':sorted(changed)},
      'owner_churn':{'count':len(breakdown['owner']),'started':sum(tasks[t].lifecycle=='in_progress' or any(b.span.start<event_slot for b in before[t]) for t in breakdown['owner']),
                     'cross_team':sum({team for e in owners_before[t] if e in employees for team in employees[e].team_ids} != {team for e in owners_after.get(t,set()) if e in employees for team in employees[e].team_ids} for t in breakdown['owner'])},
      'displacement':{'total':sum(shifts),'median':median(shifts) if shifts else None,'maximum':max(shifts,default=None),'distribution':sorted(shifts),'unmatched_blocks':unmatched},
      'preservation':{'unchanged':len(affected-changed),'considered':len(affected),'rate':ratio(len(affected-changed),len(affected)),'affected_task_ids':sorted(affected)},
      'replans':{'planning_attempts':outcome.iterations,'cascade_cycles':len(conflicts),'plan_versions':outcome.plan_versions},
      'late_conflicts':len(conflicts),'contacts':{'count':len(recipients),'recipient_ids':sorted(recipients)},
      'relay_hops':len(relays),'duplicate_transmissions':sum(n-1 for n in tx.values()),
      'clarifications_approvals':{'required_clarifications':sum(r['detail'].get('kind')=='required' for r in clarification),
         'avoidable_reconstruction':sum(r['detail'].get('kind')=='avoidable' for r in clarification),
         'required_approval_requests':sum(r['action_type']=='approval_requested' and r['detail'].get('required',False) for r in actor_events),
         'approval_decisions':len(approvals),'bound_approval_records':len(outcome.approvals)},
      'invalid_delegations':{'invalid':len(invalid),'assignments':len(assigned),'rate':ratio(len(invalid),len(assigned)),'task_ids':sorted(invalid)},
      'capacity_overload':{'active_minutes':report.overloaded_slots*15,'overlap_pairs':report.overlap_pairs,'maximum_daily_ratio':report.maximum_daily_load_ratio,'maximum_weekly_ratio':report.maximum_weekly_load_ratio},
      'dependency_deadlines':{'precedence':sum(v.code=='precedence_or_lag' for v in report.violations),
         'acceptance_review':sum(v.category=='dependency' and v.code!='precedence_or_lag' for v in report.violations),
         'missed_agreed':sum(x>0 for x in report.agreed_lateness_slots.values()),'agreed_lateness_minutes':sum(report.agreed_lateness_slots.values())*15,
         'requested_lateness_minutes':sum(report.requested_lateness_slots.values())*15,
         'median_lateness_minutes':median([v*15 for v in report.agreed_lateness_slots.values()]) if report.agreed_lateness_slots else None,
         'maximum_lateness_minutes':max(report.agreed_lateness_slots.values(),default=0)*15},
      'priority_service':{'incident_resolution':completion(incident),'blocking_tasks':completion(blocking),'clock':'synthetic accepted duration'},
      'collateral':{'moved':len(changed&lower),'deadlines_changed':len(set(breakdown['deadline'])&lower),'owners_changed':len(set(breakdown['owner'])&lower),
          'newly_affected_people':sorted({p for t in changed&lower for p in owners_after.get(t,set())} - {p for t in incident for p in tasks[t].eligible_owners})},
      'completion':{'affected':completion(considered),'hikari':completion(hikari),'incident':completion(incident),'clock':'synthetic accepted duration'},
      'hard_violations':{'count':len(report.violations),'by_category':categories},
      'source_authority':{'count':categories.get('authority',0),'by_code':dict(Counter(v.code for v in report.violations if v.category=='authority'))},
      'scope':{'read':full,'considered':read,'replanned':sizes(replanned),'moved':sizes(changed),'notified':sizes(notified_tasks,recipients),
               'full':full,'considered_excluded_percent':{k:100*(1-read[k]/n) if n else None for k,n in full.items()},'sources_read':len(outcome.read_source_ids)},
      'planning_latency':{'stage_ms':stage_ms or {},'clock':'harness monotonic runtime','product_latency':None,'variables':None,'constraints':None,
                          'unavailable_reason':'No product compiler/solver/model executed.'},
      'terminal_classification':{'expected':expected_classification,'observed':outcome.classification,'correct':int(expected_classification==outcome.classification),'attempts':1},
      'false_success':{'false_successes':int(outcome.terminal=='COMPLETED' and bool(report.violations)),'attempts':1,'rate':int(outcome.terminal=='COMPLETED' and bool(report.violations)),
                       'scope':'Concrete schedule and supplied evidence only; product workflow not observed.'},
      'deadline_movement':deadline_deltas,
      'fragmentation':{'segments':len(outcome.schedule),'additional_starts':max(0,len(outcome.schedule)-len(assigned)),
                        'minimum_run_violations':sum(v.code=='minimum_run' for v in report.violations),'handoffs':len(breakdown['owner'])},
      'workload_balance':{'active_minutes':{p:sum((b.span.end-b.span.start)*15 for tid,rows in after.items() if tasks.get(tid) and tasks[tid].timing!='passive' for b in rows if b.employee_id==p) for p in sorted(scoped_people)}},
      'source_grounding':{'unsupported':sum(v.code=='unsupported_constraint' for v in report.violations),'material_checks':len(tasks)*3,
                          'supported_rate':ratio(len(tasks)*3-sum(v.code=='unsupported_constraint' for v in report.violations),len(tasks)*3)},
      'privacy':{'authority':categories.get('authority',0),'disclosure':categories.get('disclosure',0)},
      'boundary_facts':sum(r.opaque and r.employee_id in scoped_people for r in snapshot.reservations),
      'action_burden':dict(Counter(r['action_type'] for r in actor_events if r['phase'] in ('coordination','response','synthetic_execution'))),
      'communication':{'required_owners':sorted({p for t in changed for p in owners_after.get(t,set())}),
                        'missed_owners':sorted({p for t in changed for p in owners_after.get(t,set())}-recipients),
                        'forbidden_disclosures':categories.get('disclosure',0),'scope':'Minimum fact relays; not product notifications.'},
      'resources':{'events':len(actor_events),'fixture_pages':sum(r['action_type']=='source_retrieved' for r in actor_events),
                    'input_bytes':input_bytes,'model_tokens':None,'solver_cpu':None,'peak_memory':None},
      'employee_control':dict(Counter(r['action_type'] for r in actor_events if r['action_type'] in ('estimate_corrected','input_objected','access_objected','correction_resolved'))),
    }
    observations=[]
    for mid,definition in definitions.items():
        status='MEASURED' if mid in values else 'NOT_MEASURED'
        value=values.get(mid);reason=None if value is not None else 'Required product lifecycle/model/provider/held-out evidence is absent.'
        if mid in ('priority_service','collateral') and scenario!='B':status='NOT_APPLICABLE';value=None;reason='Only Change B has incident priority service/collateral eligibility.'
        if mid=='priority_service' and scenario=='B' and completion(incident) is None:status='NOT_MEASURED';value=None;reason='Incident acceptance evidence is absent; planned finish is not accepted resolution.'
        if mid=='completion' and not outcome.acceptances:status='NOT_MEASURED';value=None;reason='No accepted terminal workload evidence; failure remains in the denominator.'
        if mid in ('planning_latency','replans','late_conflicts','contacts','relay_hops','duplicate_transmissions','clarifications_approvals','communication') and outcome.method=='product_replay':status='NOT_MEASURED';value=None;reason='Recording has no product timing, planning-attempt or communication evidence; absence is not zero.'
        refs=tuple(artifact_prefix+n for n in ('input.json','outcome.json','validation.json','events.json'))
        observations.append(Observation(metric_id=mid,run_id=run_id,scenario_id=scenario,approach_or_condition=outcome.method,
            evidence_class='recorded_replay' if outcome.method=='product_replay' else ('product_runtime' if outcome.method=='coordination_engine_product' else 'synthetic'),
            unit=definition['unit'],eligibility_rule=definition['eligibility_rule'],numerator_and_denominator_refs=refs[:3],
            source_event_or_artifact_refs=refs,status=status,value=value,missing_or_invalid_reason=reason))
    return observations


def product_cells(run_id,scenario):
    return [Observation(metric_id=r['metric_id'],run_id=run_id,scenario_id=scenario,
        approach_or_condition='coordination_engine_product',evidence_class='product_runtime',unit=r['unit'],
        eligibility_rule=r['eligibility_rule'],numerator_and_denominator_refs=(),source_event_or_artifact_refs=('product-capabilities.json',),
        value=None,status='NOT_RUN',missing_or_invalid_reason='Real product adapter and supported seed/reset/drive/observe/project/export interfaces are unavailable.')
        for r in registry()['metrics']]


def headline(naive,product,mapping):
    """A positive result requires actual product evidence and equal inputs."""
    if mapping.status!='EQUIVALENT':return {'status':'INVALID','value':None,'reason':'Input mapping mismatch.'}
    if any(o.approach_or_condition!='coordination_engine_product' or o.evidence_class!='product_runtime' for o in product):
        return {'status':'NOT_RUN','value':None,'reason':'Replay is excluded from product headline calculations.'}
    n={o.metric_id:o for o in naive};p={o.metric_id:o for o in product}
    result={}
    formulas={
      'fewer_changed_commitments':('changed_commitments','tasks','reduction'),
      'fewer_replans':('replans','planning_attempts','reduction'),
      'fewer_relay_hops':('relay_hops',None,'reduction'),
      'fewer_invalid_delegations':('invalid_delegations','rate','difference'),
      'capacity_overload_difference':('capacity_overload','active_minutes','difference'),
      'critical_work_time_difference':('priority_service','incident_resolution','difference'),
      'preservation_rate_difference':('preservation','rate','increase'),
      'correct_replan_rate_difference':('correct_replan','rate','increase')}
    for name,(mid,key,op) in formulas.items():
        a,b=n.get(mid),p.get(mid)
        if a is None or b is None or a.status!='MEASURED' or b.status!='MEASURED':
            result[name]={'status':'NOT_RUN','value':None,'reason':'Required measured observations unavailable.'};continue
        av=a.value[key] if key else a.value;bv=b.value[key] if key else b.value
        if av is None or bv is None or (op=='reduction' and av==0):
            result[name]={'status':'NOT_APPLICABLE','value':None,'reason':'Missing rate or zero baseline denominator.'};continue
        result[name]={'status':'MEASURED','value':1-bv/av if op=='reduction' else (bv-av if op=='increase' else av-bv)}
    return result


def aggregate(rows):
    """Keep every attempted terminal outcome; no seed-as-customer inference."""
    classes=Counter(r['classification'] for r in rows)
    terminal=Counter(r['terminal'] for r in rows)
    matrix=Counter((r['expected'],r['classification']) for r in rows)
    return {'evidence_class':'synthetic','eligible_case_count':len(rows),'exclusions':[],
            'classification_counts':dict(classes),'terminal_counts':dict(terminal),
            'confusion_matrix':[{'expected':a,'observed':b,'count':n} for (a,b),n in sorted(matrix.items())],
            'classification_accuracy':ratio(sum(r['expected']==r['classification'] for r in rows),len(rows)),
            'warning':'Cases and seeds are synthetic conditions, not independent companies or human productivity evidence.'}
