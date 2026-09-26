"""Judge-safe synthetic company directory and derived relational graph views.

These exports are presentation indexes over the immutable benchmark contracts.
They are not a graph database, an authorisation boundary or product state.
"""
from collections import defaultdict


INSPECTOR_LABEL = "SYNTHETIC JUDGE/DEVELOPER INSPECTOR — NOT AN AUTHORISATION VIEW"


def company_inspector(snapshot):
    """Export bounded fields for browsing every fictional employee and work item."""
    teams = {team.team_id: team for team in snapshot.teams}
    people = {person.employee_id: person for person in snapshot.employees}
    projects = {project.project_id: project for project in snapshot.projects}
    blocks_by_task = defaultdict(list)
    blocks_by_person = defaultdict(list)
    for block in snapshot.schedule:
        blocks_by_task[block.task_id].append(block)
        blocks_by_person[block.employee_id].append(block)
    tasks_by_person = defaultdict(set)
    tasks_by_team = defaultdict(set)
    tasks_by_project = defaultdict(set)
    for task in snapshot.tasks:
        tasks_by_team[task.team_id].add(task.task_id)
        tasks_by_project[task.project_id].add(task.task_id)
        for employee_id in task.eligible_owners:
            tasks_by_person[employee_id].add(task.task_id)

    employees = []
    for person in snapshot.employees:
        blocks = blocks_by_person[person.employee_id]
        employees.append({
            "employee_id": person.employee_id,
            "name": person.name,
            "role": "manager" if any(t.manager_id == person.employee_id for t in snapshot.teams) else "employee",
            "manager_id": person.manager_id,
            "manager_name": people[person.manager_id].name,
            "teams": [{"team_id": team_id, "name": teams[team_id].name} for team_id in person.team_ids],
            "confirmed_skills": list(person.confirmed_skills),
            "declared_skills": list(person.declared_skills),
            "qualifications": list(person.qualifications),
            "timezone": person.timezone,
            "locale": person.locale,
            "availability": person.availability,
            "daily_budget_minutes": person.daily_budget_slots * snapshot.company.slot_minutes,
            "weekly_budget_minutes": person.weekly_budget_slots * snapshot.company.slot_minutes,
            "working_windows": [span.model_dump(mode="json") for span in person.working],
            "eligible_task_count": len(tasks_by_person[person.employee_id]),
            "scheduled_task_count": len({block.task_id for block in blocks}),
            "scheduled_minutes": sum((block.span.end - block.span.start) * snapshot.company.slot_minutes for block in blocks),
            "familiarity": [{
                "project_id": item.project_id,
                "project_title": projects[item.project_id].title,
                "maturity": item.maturity,
                "source_ref": item.source_ref,
                "version": item.version,
            } for item in person.familiarity],
            "profile_versions": {
                "profile": person.profile_version,
                "skills": person.skill_version,
                "capacity": person.capacity_version,
                "estimate": person.estimate_version,
            },
            "source_ref": person.source_ref,
        })

    team_rows = []
    for team in snapshot.teams:
        team_rows.append({
            "team_id": team.team_id,
            "name": team.name,
            "function": team.function,
            "manager_id": team.manager_id,
            "manager_name": people[team.manager_id].name,
            "employee_count": sum(team.team_id in person.team_ids for person in snapshot.employees),
            "project_count": sum(project.team_id == team.team_id for project in snapshot.projects),
            "task_count": len(tasks_by_team[team.team_id]),
        })

    project_rows = []
    for project in snapshot.projects:
        project_rows.append({
            "project_id": project.project_id,
            "title": project.title,
            "purpose": project.purpose,
            "classification": project.classification,
            "team_id": project.team_id,
            "team_name": teams[project.team_id].name,
            "manager_id": project.manager_id,
            "manager_name": people[project.manager_id].name,
            "requested_deadline_slot": project.requested_deadline_slot,
            "agreed_deadline_slot": project.agreed_deadline_slot,
            "task_count": len(tasks_by_project[project.project_id]),
            "source_ref": project.source_ref,
        })

    task_rows = []
    for task in snapshot.tasks:
        blocks = blocks_by_task[task.task_id]
        task_rows.append({
            "task_id": task.task_id,
            "title": task.title,
            "project_id": task.project_id,
            "project_title": projects[task.project_id].title,
            "team_id": task.team_id,
            "lifecycle": task.lifecycle,
            "priority": task.priority,
            "effort_minutes": task.effort_slots * snapshot.company.slot_minutes,
            "requested_deadline_slot": task.requested_deadline_slot,
            "agreed_deadline_slot": task.agreed_deadline_slot,
            "required_skills": list(task.required_skills),
            "eligible_owners": [{"employee_id": employee_id, "name": people[employee_id].name}
                                for employee_id in task.eligible_owners],
            "assigned_owners": [{"employee_id": employee_id, "name": people[employee_id].name}
                                for employee_id in sorted({block.employee_id for block in blocks})],
            "dependencies": [dependency.predecessor for dependency in task.dependencies],
            "reviewer_id": task.reviewer_id,
            "protected": task.protected,
            "movable": task.movable,
            "allow_owner_change": task.allow_owner_change,
            "source_refs": sorted({task.source_ref, task.priority_source, task.movement_authority,
                                   *task.required_sources}),
        })

    source_counts = defaultdict(int)
    classification_counts = defaultdict(int)
    for source in snapshot.sources:
        source_counts[source.provider] += 1
        classification_counts[source.classification] += 1
    return {
        "label": INSPECTOR_LABEL,
        "notice": "All records are fictional. This complete-company view is for judge/developer inspection and is not a product user POV.",
        "company": {
            "company_id": snapshot.company.company_id,
            "name": snapshot.company.name,
            "business": snapshot.company.business,
            "locale": snapshot.company.locale,
            "timezone": snapshot.company.timezone,
            "anchor": snapshot.company.anchor.isoformat(),
            "horizon_slots": snapshot.company.horizon_slots,
            "slot_minutes": snapshot.company.slot_minutes,
            "policy_version": snapshot.company.policy_version,
            "holiday_calendar": snapshot.company.holiday_calendar,
            "optional_agent_enabled": snapshot.company.optional_agent_enabled,
        },
        "counts": {
            "employees": len(snapshot.employees),
            "teams": len(snapshot.teams),
            "projects": len(snapshot.projects),
            "tasks": len(snapshot.tasks),
            "schedule_blocks": len(snapshot.schedule),
            "opaque_reservations": len(snapshot.reservations),
            "sources": len(snapshot.sources),
            "grants": len(snapshot.grants),
        },
        "source_counts": dict(sorted(source_counts.items())),
        "classification_counts": dict(sorted(classification_counts.items())),
        "teams": team_rows,
        "employees": employees,
        "projects": project_rows,
        "tasks": task_rows,
    }


def coordination_graph(snapshot, event, outcome):
    """Derive a typed impact graph from relational task and schedule records."""
    tasks = {task.task_id: task for task in snapshot.tasks}
    people = {person.employee_id: person for person in snapshot.employees}
    projects = {project.project_id: project for project in snapshot.projects}
    teams = {team.team_id: team for team in snapshot.teams}
    sources = {source.source_id: source for source in snapshot.sources}
    before = defaultdict(list)
    after = defaultdict(list)
    for block in snapshot.schedule:
        before[block.task_id].append((block.employee_id, block.span.start, block.span.end))
    for block in outcome.schedule:
        after[block.task_id].append((block.employee_id, block.span.start, block.span.end))
    changed = {task_id for task_id in set(before) | set(after)
               if sorted(before[task_id]) != sorted(after[task_id])}
    direct = {task_id for task_id in event.task_ids if task_id in tasks}
    considered = {task_id for task_id in outcome.considered_task_ids if task_id in tasks}
    selected = set(direct | changed | considered)
    # Retain immediate graph context without allowing unbounded traversal.
    successors = defaultdict(set)
    for task in tasks.values():
        for dependency in task.dependencies:
            successors[dependency.predecessor].add(task.task_id)
    for task_id in tuple(selected):
        selected.update(dependency.predecessor for dependency in tasks[task_id].dependencies)
        selected.update(successors[task_id])
    # Large runs remain inspectable; changed/direct tasks always win the cap.
    priority = sorted(selected, key=lambda task_id: (task_id not in direct, task_id not in changed, task_id))
    selected = set(priority[:80])

    nodes = {}
    edges = []

    def node(node_id, kind, label, subtitle="", status="context", **meta):
        existing = nodes.get(node_id)
        rank = {"context": 0, "affected": 1, "changed": 2, "direct": 3}
        if existing and rank[existing["status"]] >= rank[status]:
            return
        nodes[node_id] = {"id": node_id, "kind": kind, "label": label, "subtitle": subtitle,
                          "status": status, "meta": meta}

    def edge(source, target, kind, status="context"):
        edges.append({"source": source, "target": target, "kind": kind, "status": status})

    for task_id in sorted(selected):
        task = tasks[task_id]
        status = "direct" if task_id in direct else "changed" if task_id in changed else "affected"
        node(f"task:{task_id}", "task", task.title, task_id, status,
             project_id=task.project_id, deadline_slot=task.agreed_deadline_slot,
             before=sorted(before[task_id]), after=sorted(after[task_id]))
        project = projects[task.project_id]
        node(f"project:{project.project_id}", "project", project.title, project.project_id, status)
        edge(f"project:{project.project_id}", f"task:{task_id}", "contains", status)
        team = teams[task.team_id]
        node(f"team:{team.team_id}", "team", team.name, team.function, status)
        edge(f"project:{project.project_id}", f"team:{team.team_id}", "belongs_to", status)
        for employee_id, _, _ in sorted(set(before[task_id])):
            person = people[employee_id]
            node(f"employee:{employee_id}", "employee", person.name, employee_id, status)
            edge(f"task:{task_id}", f"employee:{employee_id}", "assigned_before", status)
        for employee_id, _, _ in sorted(set(after[task_id])):
            person = people[employee_id]
            node(f"employee:{employee_id}", "employee", person.name, employee_id, status)
            edge(f"task:{task_id}", f"employee:{employee_id}", "assigned_after", status)
            for team_id in person.team_ids:
                member_team = teams[team_id]
                node(f"team:{team_id}", "team", member_team.name, member_team.function, status)
                edge(f"employee:{employee_id}", f"team:{team_id}", "member_of", status)
        for dependency in task.dependencies:
            if dependency.predecessor in selected:
                edge(f"task:{dependency.predecessor}", f"task:{task_id}", "precedes", status)
        if task.reviewer_id:
            reviewer = people[task.reviewer_id]
            node(f"employee:{reviewer.employee_id}", "employee", reviewer.name, reviewer.employee_id, status)
            edge(f"task:{task_id}", f"employee:{reviewer.employee_id}", "reviewed_by", status)
        task_sources = sorted(({task.source_ref, task.priority_source, task.movement_authority,
                                *task.required_sources}) & set(sources))
        for source_id in task_sources:
            source = sources[source_id]
            node(f"source:{source_id}", "source", source_id, source.provider, status,
                 provider=source.provider, classification=source.classification,
                 authoritative_for=list(source.authoritative_for))
            edge(f"source:{source_id}", f"task:{task_id}", "grounds", status)

    unique_edges = {(item["source"], item["target"], item["kind"], item["status"]): item for item in edges}
    for item in nodes.values():
        flags={item["status"]}
        if item["kind"] == "task":
            task_id=item["id"].split(":",1)[1]
            if task_id in direct: flags.add("direct")
            if task_id in changed: flags.add("changed")
            if task_id in considered: flags.add("affected")
        item["flags"]=sorted(flags)
    return {
        "label": "DERIVED RELATIONAL COORDINATION GRAPH — NOT A GRAPH DATABASE",
        "notice": "Nodes and edges are recomputed from task, dependency, ownership, source and team records. They do not add facts or authority.",
        "scenario_id": event.scenario_id,
        "method": outcome.method,
        "stats": {
            "company_tasks": len(snapshot.tasks),
            "considered_tasks": len(considered),
            "direct_tasks": len(direct),
            "changed_tasks": len(changed),
            "rendered_tasks": sum(node["kind"] == "task" for node in nodes.values()),
            "rendered_employees": sum(node["kind"] == "employee" for node in nodes.values()),
        },
        "nodes": sorted(nodes.values(), key=lambda item: (item["kind"], item["id"])),
        "edges": sorted(unique_edges.values(), key=lambda item: (item["source"], item["target"], item["kind"])),
    }
