"""Neutral concrete checks. No scheduling, repair, baseline or SUT imports."""
from collections import Counter, defaultdict
from datetime import timedelta, timezone
from zoneinfo import ZoneInfo

from .contracts import Outcome, Snapshot, Validation, Violation
from ..serialization import digest

COVERAGE = ("tenant/entity integrity", "confirmed skills/qualifications/access", "effort/segments/owner consistency",
            "working/fixed/exclusive capacity", "daily/weekly budgets", "dependencies/lags/reviews/acceptance",
            "requested/agreed/forecast deadlines", "protected/started movement", "priority/displacement",
            "exact required approval evidence", "source authority/freshness", "disclosure")


def candidate_digest(outcome: Outcome) -> str:
    return digest({"schedule": [b.model_dump(mode="json") for b in outcome.schedule],
                   "deadlines": outcome.agreed_deadlines, "priorities": outcome.priorities,
                   "protected": outcome.protected_values, "cancelled": outcome.cancelled_task_ids})


def validate(snapshot: Snapshot, outcome: Outcome, at_slot: int = 0) -> Validation:
    tasks = {t.task_id:t for t in snapshot.tasks}
    employees = {e.employee_id:e for e in snapshot.employees}
    sources = {s.source_id:s for s in snapshot.sources}
    projects = {p.project_id:p for p in snapshot.projects}
    actors = {a.actor_id:a for a in snapshot.actors}
    now = snapshot.company.anchor.astimezone(timezone.utc) + timedelta(minutes=15*at_slot)
    grants = {(g.principal_id,g.resource_id) for g in snapshot.grants
              if g.company_id==snapshot.company.company_id and "read" in g.actions and
              not g.revoked and g.expires_at > now and g.resource_id in sources and
              g.connection_id == sources[g.resource_id].connection_id}
    violations = []

    def fail(category, code, tids=(), refs=(), amount=1):
        violations.append(Violation(category=category,code=code,task_ids=tuple(tids),entity_refs=tuple(refs),amount=amount))

    by_task, by_employee = defaultdict(list), defaultdict(list)
    before = defaultdict(list)
    for b in snapshot.schedule:
        before[b.task_id].append(b)
    for bid,n in Counter(b.block_id for b in outcome.schedule).items():
        if n>1:
            fail("tenant","duplicate_block",refs=(bid,))
    for b in outcome.schedule:
        t,e = tasks.get(b.task_id),employees.get(b.employee_id)
        if b.company_id!=snapshot.company.company_id:
            fail("tenant","cross_tenant",(b.task_id,),(b.block_id,))
        if t is None or e is None:
            fail("tenant","unknown_reference",(b.task_id,),(b.block_id,))
            continue
        by_task[b.task_id].append(b)
        if t.timing != "passive":
            by_employee[b.employee_id].append(b)
        if (b.employee_id not in t.eligible_owners or not set(t.required_skills)<=set(e.confirmed_skills)
            or not set(t.qualifications)<=set(e.qualifications)):
            fail("eligibility","owner_eligibility",(t.task_id,),(e.employee_id,))
        if e.availability != "known":
            fail("capacity","unknown_availability",(t.task_id,),(e.employee_id,))
        if b.span.start < t.window.start or b.span.end > t.window.end or b.span.end > snapshot.company.horizon_slots:
            fail("capacity","task_window",(t.task_id,),(b.block_id,))
        if t.timing != "passive" and not any(w.start <= b.span.start and b.span.end <= w.end for w in e.working):
            fail("capacity","working_window",(t.task_id,),(b.block_id,))
        if t.timing == "fixed" and b.span != t.window:
            fail("capacity","fixed_attendance",(t.task_id,),(b.block_id,))
        for sid in t.required_sources:
            s = sources.get(sid)
            if ((e.employee_id,sid) not in grants or s is None or s.revoked or s.freshness!="current" or s.expires_at<=now):
                fail("eligibility","source_access",(t.task_id,),(sid,))
    approvals_digest = candidate_digest(outcome)
    acceptances = {a.task_id:a for a in outcome.acceptances}
    if len(acceptances)!=len(outcome.acceptances):
        fail("dependency","duplicate_acceptance")
    requested,agreed = {},{}
    for tid,t in tasks.items():
        blocks = sorted(by_task[tid],key=lambda b:(b.span.start,b.block_id))
        original = sorted(before[tid],key=lambda b:(b.span.start,b.block_id))
        owners = {b.employee_id for b in blocks}
        if not blocks or len(owners)!=1:
            fail("effort","missing_or_multiple_owners",(tid,))
        elapsed = sum(b.span.end-b.span.start for b in blocks)
        if elapsed != (t.passive_slots if t.timing=="passive" else t.effort_slots):
            fail("effort","effort_total",(tid,))
        if len(blocks)>t.max_segments:
            fail("effort","max_segments",(tid,))
        if any(b.span.end-b.span.start < min(t.min_segment_slots,t.effort_slots) for b in blocks) and t.timing!="passive":
            fail("effort","minimum_run",(tid,))
        if any(a.span.end>=b.span.start for a,b in zip(blocks,blocks[1:])):
            fail("effort","overlapping_or_unmerged_segments",(tid,))
        for sid,needed in ((t.source_ref,"requirements"),(t.movement_authority,"movement"),(t.priority_source,"priority")):
            s = sources.get(sid)
            if s is None or s.revoked or s.freshness!="current" or s.expires_at<=now or needed not in s.authoritative_for:
                fail("authority","unsupported_constraint",(tid,),(sid,))
        project=projects.get(t.project_id)
        deadline_source=sources.get(project.source_ref) if project else None
        if (deadline_source and "agreed_deadline" in deadline_source.authoritative_for
            and deadline_source.fields.get("deadline_slot")!=t.agreed_deadline_slot):
            fail("authority","deadline_source_mismatch",(tid,))
        if t.priority==0:
            p = sources.get(t.priority_source)
            actor=actors.get(p.fields.get("actor_id")) if p else None
            if (p is None or p.fields.get("priority")!=0 or actor is None or
                "declare_critical" not in actor.permitted_actions or t.project_id not in actor.scope_refs):
                fail("authority","priority_origin",(tid,))
        if t.reviewer_id:
            r = employees.get(t.reviewer_id)
            if r is None or "review-certified" not in r.qualifications or (t.separation_of_duties and t.reviewer_id in owners):
                fail("eligibility","reviewer_eligibility",(tid,))
            if any((t.reviewer_id,sid) not in grants for sid in t.required_sources):
                fail("eligibility","reviewer_access",(tid,))
            review = by_task[t.review_task_id] if t.review_task_id else []
            if not review or any(b.employee_id!=t.reviewer_id for b in review):
                fail("dependency","review_capacity_missing",(tid,))
        if not t.self_certifiable and not t.reviewer_id:
            fail("dependency","acceptance_gate_missing",(tid,))
        if blocks:
            start,end = blocks[0].span.start,max(b.span.end for b in blocks)
            requested[tid]=max(0,end-t.requested_deadline_slot)
            deadline=outcome.agreed_deadlines.get(tid,t.agreed_deadline_slot)
            # Deadline extension is never available in this fixture policy.
            agreed[tid]=max(0,end-t.agreed_deadline_slot)
            if end>t.agreed_deadline_slot:
                fail("deadline","agreed_deadline",(tid,),amount=end-t.agreed_deadline_slot)
            if deadline != t.agreed_deadline_slot:
                fail("authority","deadline_change",(tid,))
            if tid in outcome.forecast_deadlines and outcome.forecast_deadlines[tid]!=end:
                fail("deadline","forecast_mismatch",(tid,))
            for d in t.dependencies:
                prev=by_task[d.predecessor]
                if not prev or max(b.span.end for b in prev)+d.lag_slots>start:
                    fail("dependency","precedence_or_lag",(d.predecessor,tid))
                # Schedule order and actual execution release are distinct checks.
                if tid in outcome.actual_starts and d.acceptance_required:
                    a=acceptances.get(d.predecessor)
                    if a is None or a.accepted_slot+d.lag_slots>outcome.actual_starts[tid]:
                        fail("dependency","acceptance_release",(d.predecessor,tid))
            a=acceptances.get(tid)
            if a:
                expected_reviewer=t.reviewer_id or next(iter(owners),None)
                review_end=max((b.span.end for b in by_task[t.review_task_id]),default=end) if t.review_task_id else end
                if (a.reviewer_id!=expected_reviewer or a.accepted_slot<max(end,review_end)
                    or not a.evidence_ref or not a.submission_version):
                    fail("dependency","invalid_acceptance",(tid,))
            if tid in outcome.actual_starts and outcome.actual_starts[tid] < start:
                fail("dependency","actual_start_before_schedule",(tid,))
        moved = [(b.employee_id,b.span) for b in original] != [(b.employee_id,b.span) for b in blocks]
        if original and moved:
            if t.protected or t.lifecycle=="in_progress" or not t.movable or any(b.span.start<at_slot for b in original):
                fail("protection","protected_or_started_movement",(tid,))
            if not t.allow_owner_change and {b.employee_id for b in original}!=owners:
                fail("protection","owner_lock",(tid,))
            if t.required_approver and not any(a.actor_id==t.required_approver and tid in a.task_ids and
                    a.decision=="approved" and a.proposal_digest==approvals_digest and a.base_revision==snapshot.revision and
                    a.source_ref==t.movement_authority for a in outcome.approvals):
                fail("authority","required_approval",(tid,))
        if outcome.priorities.get(tid,t.priority)!=t.priority:
            fail("authority","priority_change",(tid,))
        if outcome.protected_values.get(tid,t.protected)!=t.protected or tid in outcome.cancelled_task_ids:
            fail("protection","protection_or_cancellation_change",(tid,))
    # Detect direct, locally checkable inversions of the declared ready-work
    # policy. This is a check, not a search/repair or global optimality claim.
    for tid,t in tasks.items():
        if t.priority != 0 or not by_task[tid]:
            continue
        own=by_task[tid][0].employee_id
        ready=max(at_slot,t.window.start,max((max((b.span.end for b in by_task[d.predecessor]),default=t.window.end)+d.lag_slots for d in t.dependencies),default=0))
        start=min(b.span.start for b in by_task[tid])
        for low_id,low in tasks.items():
            if low.priority<=t.priority or low.protected or not low.movable or low.lifecycle=="in_progress":
                continue
            for b in by_task[low_id]:
                if (b.employee_id==own and ready<=b.span.start<start and b.span.end-b.span.start>=t.effort_slots
                    and b.span.start>=at_slot and b.span.start+t.effort_slots<=t.agreed_deadline_slot):
                    fail("authority","ready_priority_inversion",(tid,low_id))
    for tid in set(outcome.agreed_deadlines)|set(outcome.forecast_deadlines)|set(outcome.priorities)|set(outcome.actual_starts)|set(acceptances)|set(outcome.protected_values)|set(outcome.cancelled_task_ids):
        if tid not in tasks:
            fail("tenant","unknown_outcome_task",(tid,))
    overload=0
    pairs=0
    maximum_daily=maximum_weekly=0.0
    for eid,e in employees.items():
        occupancy=Counter()
        labels=defaultdict(list)
        for b in by_employee[eid]:
            for slot in range(b.span.start,min(b.span.end,snapshot.company.horizon_slots)):
                occupancy[slot]+=1
                labels[slot].append(b.task_id)
        ids={b.block_id for b in by_employee[eid]}
        for r in snapshot.reservations:
            if r.employee_id==eid and r.internal_block_ref not in ids:
                for slot in range(r.span.start,r.span.end):
                    occupancy[slot]+=1
        conflicts={tuple(sorted((a.block_id,b.block_id))) for i,a in enumerate(by_employee[eid]) for b in by_employee[eid][i+1:]
                   if a.span.start<b.span.end and b.span.start<a.span.end}
        pairs+=len(conflicts)
        pairs+=sum(a.span.start<r.span.end and r.span.start<a.span.end
                   for a in by_employee[eid] for r in snapshot.reservations
                   if r.employee_id==eid and r.internal_block_ref!=a.block_id)
        excess=sum(max(0,n-1) for n in occupancy.values())
        overload+=excess
        if excess:
            tids=sorted({t for slot,n in occupancy.items() if n>1 for t in labels[slot]})
            fail("capacity","exclusive_overlap",tids,(eid,),excess)
        daily=Counter()
        weekly=Counter()
        for slot,n in occupancy.items():
            date=(snapshot.company.anchor.astimezone(timezone.utc)+timedelta(minutes=15*slot)).astimezone(ZoneInfo(e.timezone)).date()
            daily[date]+=n
            weekly[date.isocalendar()[:2]]+=n
        for load in daily.values():
            maximum_daily=max(maximum_daily,load/e.daily_budget_slots)
            if load>e.daily_budget_slots:
                fail("capacity","daily_budget",tuple(b.task_id for b in by_employee[eid]),(eid,),load-e.daily_budget_slots)
        for load in weekly.values():
            maximum_weekly=max(maximum_weekly,load/e.weekly_budget_slots)
            if load>e.weekly_budget_slots:
                fail("capacity","weekly_budget",tuple(b.task_id for b in by_employee[eid]),(eid,),load-e.weekly_budget_slots)
    for sid in outcome.read_source_ids:
        s=sources.get(sid)
        if s is None or ("coordinator",sid) not in grants or s.revoked or s.freshness!="current" or s.expires_at<=now:
            fail("authority","unauthorised_source_read",refs=(sid,))
    briefs={b.brief_id:b for b in snapshot.briefs}
    for d in outcome.disclosures:
        for sid in d.source_refs:
            s=sources.get(sid)
            if s is None or (d.viewer_id,sid) not in grants or s.revoked or s.expires_at<=now:
                fail("disclosure","forbidden_source",refs=(d.viewer_id,sid))
        for bid in d.brief_ids:
            b=briefs.get(bid)
            if b is None or b.revoked or d.viewer_id not in b.audience:
                fail("disclosure","unapproved_brief",refs=(d.viewer_id,bid))
    return Validation(violations=tuple(violations),checked_task_count=len(tasks),
        requested_lateness_slots=requested,agreed_lateness_slots=agreed,overloaded_slots=overload,
        overlap_pairs=pairs,maximum_daily_load_ratio=maximum_daily,maximum_weekly_load_ratio=maximum_weekly,coverage=COVERAGE)
