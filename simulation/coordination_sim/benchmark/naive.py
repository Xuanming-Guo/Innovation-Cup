"""Mandatory transparent local greedy/cascade comparator; no scoring oracle."""
from collections import defaultdict, deque
from datetime import timedelta, timezone

from . import NAIVE_VERSION
from .contracts import Acceptance, Outcome, Segment, Span, StageStates
from ..serialization import digest


class NaiveCoordinator:
    version=NAIVE_VERSION
    tie_breakers="ready priority, deadline, release, task ID; eligible accepted familiarity, submission, exposure, employee ID"

    def __init__(self, iteration_cap=200):
        if iteration_cap<1: raise ValueError("positive iteration cap required")
        self.iteration_cap=iteration_cap

    def run(self,snapshot,event,trace):
        tasks={t.task_id:t for t in snapshot.tasks}
        people={e.employee_id:e for e in snapshot.employees}
        sources={s.source_id:s for s in snapshot.sources}
        now=snapshot.company.anchor.astimezone(timezone.utc)+timedelta(minutes=15*event.at_slot)
        grants={(g.principal_id,g.resource_id) for g in snapshot.grants if not g.revoked and g.expires_at>now and "read" in g.actions and g.company_id==snapshot.company.company_id and g.resource_id in sources and g.connection_id==sources[g.resource_id].connection_id}
        schedule=defaultdict(list)
        for b in snapshot.schedule: schedule[b.task_id].append(b)
        successors=defaultdict(set)
        for t in tasks.values():
            for d in t.dependencies: successors[d.predecessor].add(t.task_id)
        considered=set(event.task_ids)
        for tid in event.task_ids:
            if tid in tasks:
                considered.update(d.predecessor for d in tasks[tid].dependencies)
                considered.update(successors[tid])
        shared={o for tid in considered for o in tasks[tid].eligible_owners}
        considered.update(b.task_id for b in snapshot.schedule if b.employee_id in shared)
        trace.emit("planning_scope_expanded","Expanded changed work through immediate dependencies and assigned shared resources.",
                   scenario=event.scenario_id,phase="scope",refs=sorted(considered),
                   detail={"method_version":self.version,"iteration_cap":self.iteration_cap,"tie_breakers":self.tie_breakers})
        iterations=versions=0
        read_sources=set(event.source_refs)
        queue=set(event.task_ids)

        def emit(action,summary,tid=None,**detail):
            trace.emit(action,summary,scenario=event.scenario_id,actor="coordinator",role="naive_coordinator",
                       phase="planning",at=event.at_slot,refs=() if tid is None else (tid,),detail=detail)

        def relay(tid,fact,reason):
            targets=tasks[tid].eligible_owners
            graph=defaultdict(set)
            for a,b in snapshot.reporting_edges:
                graph[a].add(b);graph[b].add(a)
            for target in targets:
                pending=deque([(event.actor_id,[event.actor_id])]);seen={event.actor_id};path=None
                while pending:
                    node,route=pending.popleft()
                    if node==target: path=route;break
                    for child in sorted(graph[node]-seen):
                        seen.add(child);pending.append((child,route+[child]))
                if path is None:
                    emit("coordination_unreachable","Reporting graph has no route to the required actor.",tid)
                    continue
                for sender,recipient in zip(path,path[1:]):
                    trace.emit("notification_relayed","Relayed a minimum change fact through the reporting graph.",
                               scenario=event.scenario_id,actor=sender,role="coordination_relay",phase="coordination",
                               at=event.at_slot,refs=(tid,),detail={"recipient":recipient,"fact_id":fact,"reason":reason,"edge":[sender,recipient]})

        def finish(classification,terminal,reason=None):
            blocks=tuple(sorted((b for rows in schedule.values() for b in rows),key=lambda b:b.block_id))
            outcome=Outcome(method="naive",classification=classification,terminal=terminal,schedule=blocks,
                            considered_task_ids=tuple(sorted(considered)),iterations=iterations,plan_versions=versions,reason=reason,
                            read_source_ids=tuple(sorted(s for s in read_sources if s in sources and not sources[s].revoked and sources[s].freshness=="current")),
                            forecast_deadlines={tid:max(b.span.end for b in rows) for tid,rows in schedule.items() if rows})
            # Fixed-duration deterministic actors produce synthetic acceptance evidence.
            # This is the comparator's workload clock, never product execution.
            if terminal=="COMPLETED":
                accepted=[]
                starts={}
                for tid in sorted(schedule,key=lambda tid:(max(b.span.end for b in schedule[tid]),tid)):
                    rows=schedule[tid];task=tasks[tid]
                    end=max(b.span.end for b in rows)
                    if task.review_task_id:
                        end=max(end,max((b.span.end for b in schedule[task.review_task_id]),default=end))
                    accepted.append(Acceptance(task_id=tid,reviewer_id=task.reviewer_id or rows[0].employee_id,
                                               submission_version="synthetic-duration-1",accepted_slot=end,evidence_ref=f"duration-policy-1:{tid}"))
                    starts[tid]=min(b.span.start for b in rows)
                    if tid in considered:
                        trace.emit("duration_policy_evaluated","Fixed-duration actor policy projected synthetic acceptance; no human work executed.",
                            scenario=event.scenario_id,actor=accepted[-1].reviewer_id,role="synthetic_reviewer",phase="synthetic_execution",
                            at=event.at_slot,refs=(tid,),detail={"submission_version":"synthetic-duration-1","accepted_slot":end})
                outcome=outcome.model_copy(update={"acceptances":tuple(accepted),"actual_starts":starts,
                    "states":StageStates(work_acceptance="SIMULATED",notification_refetch="SIMULATED_REPORTING_RELAYS")})
            emit("naive_terminal",f"Naive comparator ended {terminal}; no product executed.",classification=classification,reason=reason)
            return outcome

        if event.kind=="no_impact": return finish("FEASIBLE","COMPLETED")
        if event.kind=="concurrent":
            emit("capability_unavailable","The naive comparator has no transactional commit capability.")
            return finish("UNKNOWN","UNKNOWN","Transactional competing-commit behavior requires the real SUT; no commit emulation.")
        for tid in event.task_ids:
            relay(tid,f"{event.scenario_id}:change","change")
        while queue:
            if iterations>=self.iteration_cap:
                return finish("UNKNOWN","TIMED_OUT","Declared local cascade iteration cap reached; no infeasibility proof.")
            ready=[tasks[tid] for tid in queue if all(d.predecessor not in queue and schedule[d.predecessor] for d in tasks[tid].dependencies)]
            if not ready: return finish("UNKNOWN","UNKNOWN","Local queue cannot advance; no global infeasibility claim.")
            task=min(ready,key=lambda t:(t.priority,t.agreed_deadline_slot,t.window.start,t.task_id))
            tid=task.task_id;queue.remove(tid);considered.add(tid);iterations+=1
            original=schedule.pop(tid,[])
            if original and (task.protected or not task.movable or task.lifecycle=="in_progress" or any(b.span.start<event.at_slot for b in original)):
                schedule[tid]=original
                continue
            read_sources.update(task.required_sources)
            eligible=[]
            for eid in task.eligible_owners:
                e=people[eid]
                if e.availability=="unknown":
                    schedule[tid]=original
                    emit("clarification_requested","Availability is unknown; no free-time fallback.",tid,kind="required")
                    return finish("UNKNOWN","UNKNOWN","Authorised availability evidence unavailable.")
                if not set(task.required_skills)<=set(e.confirmed_skills) or not set(task.qualifications)<=set(e.qualifications): continue
                if any((eid,sid) not in grants or sources[sid].revoked or sources[sid].freshness!="current" or sources[sid].expires_at<=now for sid in task.required_sources): continue
                if original and not task.allow_owner_change and eid!=original[0].employee_id: continue
                familiarity=max(({"exposure":1,"submission":2,"accepted":3}[f.maturity] for f in e.familiarity if f.project_id==task.project_id),default=0)
                eligible.append((-familiarity,eid))
            if not eligible:
                schedule[tid]=original
                emit("clarification_requested","No eligible owner with current essential source access.",tid,kind="required")
                return finish("INVALID_INPUT","REFUSED","Missing qualification, authority or essential source access.")
            release=max(task.window.start,event.at_slot,max((max(b.span.end for b in schedule[d.predecessor])+d.lag_slots for d in task.dependencies),default=0))
            deadline=min(task.window.end,task.agreed_deadline_slot)
            duration=task.passive_slots if task.timing=="passive" else task.effort_slots
            if release+duration>deadline:
                schedule[tid]=original
                # Only the single task's own release/effort bound proves refusal;
                # a predecessor chosen by this heuristic cannot prove infeasibility.
                proved=max(task.window.start,event.at_slot)+duration>deadline
                return finish("INFEASIBLE_WITHIN_SCOPE" if proved else "UNKNOWN","REFUSED" if proved else "UNKNOWN",
                              "Task release/effort lower bound exceeds deadline." if proved else "Greedy predecessor placement leaves insufficient room; wider repair not proved impossible.")
            chosen=None
            for _,eid in sorted(eligible):
                employee=people[eid]
                occupied=defaultdict(list)
                for other,rows in schedule.items():
                    for b in rows:
                        if b.employee_id==eid:
                            for slot in range(b.span.start,b.span.end): occupied[slot].append(other)
                for r in snapshot.reservations:
                    if r.employee_id==eid and not any(r.internal_block_ref==b.block_id for rows in schedule.values() for b in rows):
                        for slot in range(r.span.start,r.span.end): occupied[slot].append("#fixed")
                workable={slot for w in employee.working for slot in range(max(w.start,release),min(w.end,deadline))}
                # Aggregate check is heuristic, not a proof of contiguous feasibility.
                if task.timing!="passive" and len(workable-set(occupied))<task.effort_slots: continue

                def movable(other):
                    if other=="#fixed": return False
                    ot=tasks[other]
                    return (ot.movable and not ot.protected and ot.lifecycle!="in_progress" and
                            all(b.span.start>=event.at_slot for b in schedule[other]) and task.priority<ot.priority and
                            ot.required_approver is None)

                def free(slot):
                    return slot in workable and all(movable(other) for other in occupied[slot])

                spans=[]
                if task.timing=="passive":
                    spans=[Span(start=release,end=release+duration)]
                elif task.timing=="fixed":
                    if all(free(slot) for slot in range(task.window.start,task.window.end)):
                        spans=[task.window]
                else:
                    remaining=task.effort_slots
                    cursor=release
                    while cursor<deadline and remaining:
                        if not free(cursor): cursor+=1;continue
                        end=cursor
                        while end<deadline and free(end) and end-cursor<remaining: end+=1
                        length=end-cursor
                        if length>=min(task.min_segment_slots,remaining) and (task.max_segments>1 or length>=remaining):
                            spans.append(Span(start=cursor,end=end));remaining-=length
                        cursor=max(end,cursor+1)
                        if len(spans)>=task.max_segments: break
                    if remaining: spans=[]
                if not spans: continue
                # Locally account for budgets; use the same single company-wide person.
                loads=defaultdict(int)
                for slot in occupied: loads[slot//96]+=1
                for span in spans:
                    for slot in range(span.start,span.end):
                        if task.timing!="passive" and slot not in occupied: loads[slot//96]+=1
                if any(v>employee.daily_budget_slots for v in loads.values()) or sum(loads.values())>employee.weekly_budget_slots: continue
                chosen=eid,spans,occupied
                break
            if chosen is None:
                schedule[tid]=original
                return finish("UNKNOWN","UNKNOWN","No local slot found within fixed facts/budgets; this is not global infeasibility.")
            eid,spans,occupied=chosen
            blocks=[Segment(block_id=f"b-{tid}" if n==0 else f"b-{tid}-{n}",company_id=snapshot.company.company_id,
                            task_id=tid,employee_id=eid,span=span) for n,span in enumerate(spans)]
            schedule[tid]=blocks;versions+=1
            emit("task_assigned","Proposed earliest local eligible assignment.",tid,employee_id=eid,segments=[s.model_dump() for s in spans])
            collisions=sorted({other for span in spans for slot in range(span.start,span.end) for other in occupied[slot]}) if task.timing!="passive" else []
            for other in collisions:
                emit("conflict_discovered","A local proposal exposed a collision; enqueue one conflicting commitment.",other,
                     late=True,proposed_task=tid)
                queue.add(other);considered.add(other)
                relay(other,f"{event.scenario_id}:change","conflict")
            if blocks!=original:
                emit("schedule_block_moved","Recorded the concrete local before/after assignment change.",tid,
                     before=[b.model_dump(mode="json") for b in original],after=[b.model_dump(mode="json") for b in blocks])
                relay(tid,f"{event.scenario_id}:change","assignment")
                for child in successors[tid]:
                    if schedule[child] and min(b.span.start for b in schedule[child])<max(b.span.end for b in blocks)+next(d.lag_slots for d in tasks[child].dependencies if d.predecessor==tid):
                        queue.add(child);considered.add(child)
                        emit("conflict_discovered","Local movement propagates a downstream dependency repair.",child,late=True,proposed_task=tid)
                if task.required_approver:
                    # Do not assume granted approval. The supported naive policy stops.
                    emit("approval_requested","Movement requires an explicit authority decision.",tid,required=True)
                    return finish("UNKNOWN","UNKNOWN","Required approval not supplied by this baseline policy.")
        return finish("FEASIBLE","COMPLETED")
