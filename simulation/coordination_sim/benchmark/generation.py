"""Synthetic company and scenario facts. Gold labels are a separate export."""
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from .contracts import (Actor, Brief, Change, Company, Dependency, Employee, Familiarity,
                        Grant, GroundTruth, Project, Reservation, Segment, Snapshot,
                        Source, Span, Task, Team)
from ..serialization import digest

PRESETS = {"tiny": (25, 4, 75, 12), "medium": (100, 10, 350, 30), "demo": (3000, 117, 8000, 150)}
FUNCTIONS = (("Engineering", 900, 35), ("Product / Planning", 350, 15),
             ("Design", 150, 8), ("Sales / Partnerships", 600, 20),
             ("Customer Success / Implementation", 450, 15), ("People / HR", 120, 6),
             ("Corporate Operations", 180, 8), ("Security / Data / Shared Platform", 250, 10))
TEMPLATES = (("Product feature", ("Requirements", "Implementation", "Validation")),
             ("Customer implementation", ("Configuration", "UAT preparation", "Training pack")),
             ("Internal onboarding", ("Orientation materials", "Technical induction", "Checklist review")),
             ("Security evidence", ("Collect evidence", "Review checklist", "Handoff record")),
             ("Data migration", ("Map fields", "Reconcile sample", "Approval pack")))


def instant(company: Company, slot: int):
    return company.anchor.astimezone(timezone.utc) + timedelta(minutes=slot * company.slot_minutes)


def _updated(model, **fields):
    return type(model).model_validate({**model.model_dump(), **fields})


def generate(preset="tiny", seed=17) -> Snapshot:
    count, team_count, task_count, project_count = PRESETS[preset]
    company = Company(company_id="soraworks-synthetic", anchor=datetime(2026, 9, 28, 9, tzinfo=ZoneInfo("Asia/Tokyo")))
    cid = company.company_id
    horizon = instant(company, company.horizon_slots)
    managers = [f"e{i:04}" for i in range(team_count)]
    if preset == "demo":
        team_functions = [name for name, _, n in FUNCTIONS for _ in range(n)]
        employee_teams = []
        offset = 0
        for _, headcount, nteams in FUNCTIONS:
            employee_teams.extend(offset + j % nteams for j in range(headcount))
            offset += nteams
    else:
        team_functions = [FUNCTIONS[i % len(FUNCTIONS)][0] for i in range(team_count)]
        employee_teams = [i % team_count for i in range(count)]
    if preset == "demo":
        managers = [f"e{employee_teams.index(i):04}" for i in range(team_count)]
    teams = tuple(Team(team_id=f"team-{i:03}", company_id=cid, name=f"{team_functions[i]} {i+1}",
                       function=team_functions[i], manager_id=managers[i]) for i in range(team_count))
    sources = []

    def source(sid, provider, authority, excerpt, fields=None, classification="team"):
        sources.append(Source(source_id=sid, company_id=cid, provider=provider,
            connection_id=f"sim-{provider}", external_id=f"object-{sid}", version="1",
            retrieved_at=company.anchor - timedelta(hours=1), expires_at=horizon + timedelta(days=1),
            classification=classification, owner_id="e0000", authoritative_for=tuple(authority),
            fields=fields or {}, excerpt=excerpt))
        return sid

    source("working-rules-v1", "calendar", ["capacity", "working_rules"],
           "Fixture company rule: 09:00–12:00 and 13:00–17:00; 7 active hours/day, 35/week.")
    source("policy-v1", "sharepoint", ["priority", "movement", "review"],
           "Unstarted work may move within its agreed window. Critical ready work wins contested capacity. No overtime or deadline extensions.",
           {"critical_setter": "incident-commander", "deadline_extension": False})
    source("hikari-request-v1", "teams", ["requested_deadline"],
           "Hikari Manufacturing requests Wednesday 15:00 JST instead of Friday afternoon.", {"deadline_slot": 216})
    source("hikari-commitment-v1", "planner", ["agreed_deadline", "acceptance"],
           "Reporting demonstration currently committed for Friday 15:00 JST. QA and Security evidence required.", {"deadline_slot": 408})
    source("hikari-requirements-v1", "sharepoint", ["requirements", "effort", "eligibility", "dependencies"],
           "Reporting API → dashboard → QA validation → Security review → customer demo. Approved synthetic fixed-duration tasks.")
    source("hikari-brief-v1", "sharepoint", ["disclosure"],
           "Prepare the approved reporting demo. Deliver the dashboard and QA/Security checklists by the agreed time.")
    source("reporting-pr-v1", "github", ["development_status"],
           "Selected reporting PR has an approved API contract; review and acceptance remain separate.", {"pull_request": 41, "state": "open"})
    source("incident-declaration-v1", "teams", ["priority", "request"],
           "Authorised incident commander declares a Sev-1 SSO failure Critical under policy-v1.",
           {"actor_id": "incident-commander", "priority": 0}, "restricted")
    source("incident-brief-v1", "sharepoint", ["disclosure", "requirements", "effort"],
           "Restore the synthetic SSO service using triage, hotfix, Security review, smoke test and deploy/verify.", classification="restricted")
    source("opaque-capacity-v1", "calendar", ["capacity"],
           "Protected occupancy only. Underlying title and personal reason omitted.", {"known": True})
    source("hr-brief-v1", "sharepoint", ["disclosure", "requirements", "effort"],
           "Prepare internal induction and technical orientation. No recruiting or personnel evaluation.", classification="internal")
    projects = [Project(project_id="hikari", company_id=cid, team_id=teams[0].team_id,
                        manager_id="e0000", title="Hikari reporting demo", purpose="Customer reporting demonstration",
                        classification="customer-confidential", requested_deadline_slot=408,
                        agreed_deadline_slot=408, source_ref="hikari-commitment-v1"),
                Project(project_id="incident", company_id=cid, team_id=teams[1].team_id,
                        manager_id="e0001", title="SSO incident response", purpose="Restore service",
                        classification="restricted", requested_deadline_slot=216,
                        agreed_deadline_slot=216, source_ref="incident-declaration-v1"),
                Project(project_id="hr", company_id=cid, team_id=teams[-1].team_id,
                        manager_id=managers[-1], title="Internal technical orientation", purpose="Induction preparation",
                        classification="internal", requested_deadline_slot=312,
                        agreed_deadline_slot=312, source_ref="hr-brief-v1")]
    for i in range(project_count - 3):
        template, _ = TEMPLATES[i % len(TEMPLATES)]
        sid = source(f"work-pack-{i:03}-v1", "planner", ["requirements", "effort", "eligibility", "dependencies", "acceptance"],
                     f"Approved {template.lower()} pack: concrete checklist, accountable owner and acceptance record.")
        projects.append(Project(project_id=f"p{i:03}", company_id=cid, team_id=teams[i % team_count].team_id,
                        manager_id=managers[i % team_count], title=f"{template} {i+1}", purpose=template,
                        classification="team", requested_deadline_slot=416, agreed_deadline_slot=416, source_ref=sid))
    employees = []
    names = ("Aoi", "Ren", "Haru", "Mio", "Sora", "Yui", "Kaito", "Nao", "Akari", "Riku")
    specialist = {4: "api", 5: "frontend", 6: "security", 7: "qa", 8: "delivery", 9: "sre", 10: "sso"}
    for i in range(count):
        team = employee_teams[i]
        shared = i < (120 if preset == "demo" else 20)
        skills = ("general", specialist.get(i, "operations"))
        # A subset starts at 10:00. No inferred nationality-based working rule.
        shift = 4 if i >= 20 and (i + seed) % 5 == 0 else 0
        working = tuple(Span(start=d*96+a+shift if a == 0 else d*96+a, end=d*96+b)
                        for d in range(5) for a, b in ((0,12), (16,32)))
        employees.append(Employee(employee_id=f"e{i:04}", company_id=cid,
            name=f"{names[i % 10]} / 架空 {i+1:04}", team_ids=(teams[team].team_id, teams[(team+1)%team_count].team_id) if shared else (teams[team].team_id,),
            manager_id=managers[team], confirmed_skills=skills, declared_skills=("training",),
            qualifications=("review-certified",) if i in (6,7) else (), working=working,
            daily_budget_slots=28-shift, weekly_budget_slots=(28-shift)*5,
            familiarity=(Familiarity(project_id="hikari", maturity="accepted", source_ref="reporting-pr-v1"),) if i in specialist else (),
            source_ref="working-rules-v1"))
    actors = [Actor(actor_id=e.employee_id, company_id=cid, role="manager" if e.employee_id in managers else "employee",
                    scope_refs=e.team_ids, permitted_actions=("acknowledge", "submit", "review") + (("approve", "clarify") if e.employee_id in managers else ())) for e in employees]
    actors += [Actor(actor_id="incident-commander", company_id=cid, role="incident_commander", scope_refs=("incident",), permitted_actions=("declare_critical",)),
               Actor(actor_id="coordinator", company_id=cid, role="benchmark_coordinator", scope_refs=(cid,), permitted_actions=("read", "plan"))]
    audience = tuple(e.employee_id for e in employees)
    briefs = [Brief(brief_id="brief-hikari", company_id=cid, text=sources[5].excerpt,
                     audience=("e0000", "e0004", "e0005", "e0006", "e0007", "e0008"), approved_by="e0000", source_ref="hikari-brief-v1"),
              Brief(brief_id="brief-incident", company_id=cid, text="Restore SSO using the approved incident checklist.",
                     audience=("e0001", "e0006", "e0007", "e0009", "e0010"), approved_by="e0001", source_ref="incident-brief-v1"),
              Brief(brief_id="brief-hr", company_id=cid, text="Prepare technical orientation for internal onboarding.",
                     audience=("e0003", "e0006", "e0011"), approved_by="e0003", source_ref="hr-brief-v1")]
    tasks, schedule = [], []
    for j, (title, skill, owner, start) in enumerate(zip(
        ("Reporting API", "Reporting dashboard", "QA validation", "Security review", "Customer demo"),
        ("api", "frontend", "qa", "security", "delivery"), (4,5,7,6,8), (16,20,96,288,404))):
        tid = f"h{j}"
        tasks.append(Task(task_id=tid, company_id=cid, project_id="hikari", team_id=teams[0].team_id,
            title=title, purpose="Prepare Hikari reporting", deliverable=f"{title} artifact",
            acceptance_criteria=("Approved reporting checklist satisfied",), task_class=skill, effort_slots=4,
            window=Span(start=0,end=408), requested_deadline_slot=408, agreed_deadline_slot=408,
            priority=1, priority_source="policy-v1", required_skills=(skill,),
            qualifications=("review-certified",) if j in (2,3) else (), eligible_owners=(f"e{owner:04}",),
            required_sources=("hikari-requirements-v1",),
            dependencies=() if j == 0 else (Dependency(predecessor=f"h{j-1}", acceptance_required=j != 2),),
            reviewer_id="e0007" if j == 1 else None, review_task_id="h2" if j == 1 else None,
            self_certifiable=j != 1, separation_of_duties=j == 1,
            movement_authority="policy-v1", brief_id="brief-hikari", source_ref="hikari-requirements-v1"))
        schedule.append(Segment(block_id=f"b-{tid}", company_id=cid, task_id=tid, employee_id=f"e{owner:04}", span=Span(start=start,end=start+4)))
    for i in range(task_count-5):
        employee_index = i % count
        round_index = i // count
        owner = employees[employee_index]
        project = projects[3 + (i // 3) % (project_count-3)]
        step = i % 3
        _, labels = TEMPLATES[((i // 3) % (project_count-3)) % len(TEMPLATES)]
        # Three work packs per person, predominantly Tue–Thu. Nonempty and distributed.
        start = 96*(1+round_index%4) + (4 if employee_index >= 20 and (employee_index+seed)%5==0 else 0)
        effort = 1+(seed+i)%3
        if employee_index in (6,7):
            start += 28  # Leave morning for chain, avoid Tuesday 14–16 private occupancy.
        if employee_index == 8 and round_index == 2:
            start += 16
        tid = f"w{i:05}"
        # Adjacent steps share a project, but only form dependency chains when their
        # concrete committed order supports them. Other packs remain independent.
        predecessor = f"w{i-1:05}" if step and i > 0 and (i-1)//count == round_index and employee_index not in (6,7,8) and employee_index-1 not in (6,7,8) else None
        if predecessor:
            start = max(start, schedule[-1].span.end)
        tasks.append(Task(task_id=tid, company_id=cid, project_id=project.project_id, team_id=project.team_id,
            title=f"{project.title}: {labels[step]}", purpose=project.purpose,
            deliverable=f"Versioned {labels[step].lower()}", acceptance_criteria=("Checklist complete; references recorded",),
            task_class="general", effort_slots=effort, window=Span(start=0,end=416),
            requested_deadline_slot=416, agreed_deadline_slot=416, priority=2+(i%3==0),
            priority_source="policy-v1", required_skills=("general",), eligible_owners=(owner.employee_id,),
            required_sources=(project.source_ref,), dependencies=() if predecessor is None else (Dependency(predecessor=predecessor),),
            protected=i%11==0, movable=i%11!=0, allow_owner_change=False,
            movement_authority="policy-v1", brief_id=f"brief-{project.project_id}", source_ref=project.source_ref))
        schedule.append(Segment(block_id=f"b-{tid}", company_id=cid, task_id=tid, employee_id=owner.employee_id, span=Span(start=start,end=start+effort)))
    for p in projects[3:]:
        members = tuple(sorted({o for t in tasks if t.project_id==p.project_id for o in t.eligible_owners} | {p.manager_id}))
        briefs.append(Brief(brief_id=f"brief-{p.project_id}", company_id=cid, text=f"Complete {p.purpose.lower()} checklist and handoff.",
                            audience=members, approved_by=p.manager_id, source_ref=p.source_ref))
    reservations = [Reservation(reservation_id="private-security", company_id=cid, employee_id="e0006",
                                span=Span(start=116,end=124), source_ref="opaque-capacity-v1"),
                    Reservation(reservation_id="frontend-started", company_id=cid, employee_id="e0005",
                                span=Span(start=0,end=8), source_ref="opaque-capacity-v1")]
    # Ten shared-capacity facts, including the private Security interval.
    reservations += [Reservation(reservation_id=f"opaque-{i}", company_id=cid, employee_id=f"e{i:04}",
                     span=Span(start=4*96+16,end=4*96+20), source_ref="opaque-capacity-v1") for i in range(12,21)]
    grants = []
    allowed = {e.employee_id: {"working-rules-v1", "opaque-capacity-v1", "policy-v1"} for e in employees}
    allowed["coordinator"] = {s.source_id for s in sources}
    allowed["incident-commander"] = {"incident-declaration-v1", "policy-v1"}
    for t in tasks:
        for person in (*t.eligible_owners, projects[0].manager_id if t.project_id=="hikari" else next(p.manager_id for p in projects if p.project_id==t.project_id)):
            allowed[person].update(t.required_sources)
    for b in briefs:
        for person in b.audience:
            allowed[person].add(b.source_ref)
    for person in ("e0006", "e0007", "e0009", "e0010", "e0001"):
        allowed[person].update(("incident-brief-v1", "incident-declaration-v1"))
    for sid in ("hikari-request-v1", "hikari-commitment-v1", "reporting-pr-v1"):
        allowed["e0000"].add(sid)
    for person, ids in sorted(allowed.items()):
        for sid in sorted(ids):
            s = next(s for s in sources if s.source_id==sid)
            grants.append(Grant(grant_id=f"g-{person}-{sid}", company_id=cid, principal_id=person,
                          connection_id=s.connection_id, resource_id=sid, actions=("read",),
                          expires_at=horizon+timedelta(days=1), authority_ref="policy-v1"))
    edges = {(e.manager_id,e.employee_id) for e in employees if e.manager_id != e.employee_id}
    edges.update(("e0000", x) for x in managers[1:])
    edges.add(("incident-commander", "e0001"))
    return Snapshot(preset=preset, seed=seed, company=company, teams=teams, employees=tuple(employees),
                    actors=tuple(actors), projects=tuple(projects), tasks=tuple(tasks), schedule=tuple(schedule),
                    reservations=tuple(reservations), sources=tuple(sources), grants=tuple(grants), briefs=tuple(briefs),
                    reporting_edges=tuple(sorted(edges)))


def change(case: str) -> Change:
    specs = {
        "A": ("deadline",0,"e0000","hikari",("hikari-request-v1","hikari-commitment-v1","hikari-requirements-v1","reporting-pr-v1"), tuple(f"h{i}" for i in range(5)),216),
        "B": ("incident",4,"incident-commander","incident",("incident-declaration-v1","incident-brief-v1","policy-v1"), tuple(f"i{i}" for i in range(5)),None),
        "impossible": ("deadline",0,"e0000","hikari",("hikari-request-v1",),tuple(f"h{i}" for i in range(5)),2),
        "no-impact": ("no_impact",0,"e0000","hikari",("hikari-request-v1",),(),None),
        "revoked": ("revocation",0,"e0000","hikari",("hikari-requirements-v1",),tuple(f"h{i}" for i in range(5)),None),
        "unavailable": ("unavailable",0,"e0000","hikari",("working-rules-v1",),tuple(f"h{i}" for i in range(5)),None),
        "HR": ("hr",4,"e0003","hr",("hr-brief-v1","opaque-capacity-v1"),("hr0","hr1"),None),
        "portfolio": ("portfolio",8,"e0000","portfolio",("portfolio-rebalance-v1","policy-v1"),
                      tuple([*(f"w{i:05}" for i in range(12,22)),"w00023","w00024"]),216),
        "concurrent": ("concurrent",0,"e0000","hikari",("policy-v1",),tuple(f"h{i}" for i in range(5)),None),
    }
    kind, at, actor, project, sources, ids, deadline = specs[case]
    return Change(scenario_id=case, kind=kind, at_slot=at, actor_id=actor, project_id=project,
                  source_refs=sources, task_ids=ids, requested_deadline_slot=deadline,
                  summary={"A":"Hikari requests Wednesday 15:00 JST; current Friday commitment retained in history.",
                           "B":"Authorised Critical SSO incident competes for QA and Security capacity.",
                           "portfolio":"Authorised multi-team launch pulls forward 12 work packages and permits reassignment across an approved response pool.",
                           "HR":"Internal technical orientation needs the shared Security specialist."}.get(case, f"Synthetic supporting case: {case}."))


def apply_change(before: Snapshot, event: Change) -> Snapshot:
    """Apply scenario-author facts, never compute a plan, approval or commitment."""
    tasks, employees, sources, grants, briefs = (list(before.tasks), list(before.employees), list(before.sources),
                                                 list(before.grants), list(before.briefs))
    if event.kind == "deadline":
        tasks = [_updated(t, requested_deadline_slot=event.requested_deadline_slot,
                          agreed_deadline_slot=event.requested_deadline_slot) if t.task_id in event.task_ids else t for t in tasks]
        # The fixture includes explicit manager confirmation of this finite deadline.
        sources = [_updated(s, version="2", fields={**s.fields,"deadline_slot":event.requested_deadline_slot},
                            excerpt=f"Synthetic requested deadline: {instant(before.company,event.requested_deadline_slot).isoformat()}.")
                   if s.source_id=="hikari-request-v1" else
                   _updated(s, version="2", fields={**s.fields,"deadline_slot":event.requested_deadline_slot,"confirmed_by":event.actor_id},
                            excerpt="Fixture manager explicitly confirms the changed deadline. The original commitment remains in the immutable before snapshot.")
                   if s.source_id=="hikari-commitment-v1" else s for s in sources]
    if event.kind in ("incident", "hr"):
        definitions = [("Triage","sre",9,2), ("Diagnosis/hotfix","sso",10,4), ("Security review","security",6,2),
                       ("Smoke test","qa",7,2), ("Deploy/verify","sre",9,2)] if event.kind=="incident" else [
                       ("Induction preparation","general",11,2), ("Technical orientation","security",6,2)]
        for j,(title,skill,owner,effort) in enumerate(definitions):
            tid = event.task_ids[j]
            sid = "incident-brief-v1" if event.kind=="incident" else "hr-brief-v1"
            tasks.append(Task(task_id=tid, company_id=before.company.company_id, project_id=event.project_id,
                team_id=before.teams[1 if event.kind=="incident" else -1].team_id, title=title,
                purpose="Restore service" if event.kind=="incident" else "Internal induction", deliverable=f"{title} checklist",
                acceptance_criteria=("Required checklist verified",), task_class=skill, effort_slots=effort,
                window=Span(start=event.at_slot,end=216 if event.kind=="incident" else 312),
                requested_deadline_slot=216 if event.kind=="incident" else 312, agreed_deadline_slot=216 if event.kind=="incident" else 312,
                priority=0 if event.kind=="incident" else 2, priority_source="incident-declaration-v1" if event.kind=="incident" else "policy-v1",
                required_skills=(skill,), qualifications=("review-certified",) if skill in ("security","qa") else (),
                eligible_owners=(f"e{owner:04}",), required_sources=(sid,),
                dependencies=() if j==0 else (Dependency(predecessor=event.task_ids[j-1],acceptance_required=True),),
                movement_authority="policy-v1", brief_id="brief-incident" if event.kind=="incident" else "brief-hr", source_ref=sid))
    if event.kind == "portfolio":
        sid = "portfolio-rebalance-v1"
        sources.append(Source(source_id=sid, company_id=before.company.company_id, provider="teams",
            connection_id="sim-teams", external_id="object-portfolio-rebalance-v1", version="1",
            retrieved_at=before.company.anchor-timedelta(hours=1),
            expires_at=instant(before.company,before.company.horizon_slots)+timedelta(days=1),
            classification="internal", owner_id=event.actor_id,
            authoritative_for=("requested_deadline","priority","movement","eligibility"),
            fields={"deadline_slot":event.requested_deadline_slot,"owner_change":True,"task_count":len(event.task_ids)},
            excerpt="Fixture manager authorises a bounded multi-team launch response pool and the earlier deadline."))
        by_id={task.task_id:task for task in tasks}
        grant_pairs={(grant.principal_id,grant.resource_id) for grant in grants}
        replacements={}
        for offset,task_id in enumerate(event.task_ids):
            task=by_id[task_id]
            current=next(block.employee_id for block in before.schedule if block.task_id==task_id)
            alternate=f"e{offset:04}"
            replacements[task_id]=_updated(task,requested_deadline_slot=event.requested_deadline_slot,
                agreed_deadline_slot=event.requested_deadline_slot,priority=1,priority_source=sid,
                eligible_owners=(current,alternate),required_sources=tuple(sorted({*task.required_sources,sid})),
                allow_owner_change=True,movement_authority=sid)
            for principal,resource in (("coordinator",sid),(current,sid),(alternate,sid),
                                       *((alternate,required) for required in task.required_sources)):
                if (principal,resource) in grant_pairs:
                    continue
                source=next(item for item in sources if item.source_id==resource)
                grants.append(Grant(grant_id=f"g-portfolio-{principal}-{resource}",company_id=before.company.company_id,
                    principal_id=principal,connection_id=source.connection_id,resource_id=resource,actions=("read",),
                    expires_at=instant(before.company,before.company.horizon_slots)+timedelta(days=1),authority_ref=sid))
                grant_pairs.add((principal,resource))
        tasks=[replacements.get(task.task_id,task) for task in tasks]
        added_audiences=defaultdict(set)
        for task in replacements.values():
            added_audiences[task.brief_id].update(task.eligible_owners)
        briefs=[_updated(brief,audience=tuple(sorted(set(brief.audience)|added_audiences[brief.brief_id])))
                if brief.brief_id in added_audiences else brief for brief in briefs]
    if event.kind=="revocation":
        sources = [_updated(s, revoked=True) if s.source_id=="hikari-requirements-v1" else s for s in sources]
    if event.kind=="unavailable":
        employees = [_updated(e, availability="unknown") if e.employee_id=="e0006" else e for e in employees]
    return _updated(before,tasks=tuple(tasks),employees=tuple(employees),sources=tuple(sources),grants=tuple(grants),briefs=tuple(briefs))


def truth(snapshot: Snapshot, event: Change) -> GroundTruth:
    classification = {"impossible":"INFEASIBLE_WITHIN_SCOPE", "revoked":"INVALID_INPUT",
                      "unavailable":"UNKNOWN", "concurrent":"UNKNOWN"}.get(event.scenario_id,"FEASIBLE")
    return GroundTruth(scenario_id=event.scenario_id,input_digest=digest(snapshot),
        expected_classification=classification, material_source_refs=tuple(sorted({s for t in snapshot.tasks for s in (t.source_ref,t.movement_authority,t.priority_source)})),
        protected_task_ids=tuple(t.task_id for t in snapshot.tasks if t.protected or t.lifecycle=="in_progress"),
        allowed_scope=tuple(t.task_id for t in snapshot.tasks), review_note_ref=f"evals/golden-review.md#{event.scenario_id}")


def second_tenant_probe() -> Snapshot:
    """Small unrelated tenant reusing IDs to test composite, not UUID-only scope."""
    original=generate()
    cid='unrelated-synthetic'
    company=_updated(original.company,company_id=cid,name='Unrelated fictional tenant')
    fields={name:tuple(_updated(x,company_id=cid) for x in getattr(original,name))
            for name in ('teams','employees','actors','projects','tasks','schedule','reservations','sources','grants','briefs')}
    return _updated(original,company=company,**fields)
