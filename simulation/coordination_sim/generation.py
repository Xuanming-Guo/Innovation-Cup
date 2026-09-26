"""Deterministic tiny fixture subset; no scheduling or product workflow logic."""

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from .contracts import Block, Employee, Fixture, GroundTruth, Scenario, SourceVersion, Task, Team, Window


def tiny(seed: int = 17) -> tuple[Fixture, Scenario, GroundTruth]:
    start = datetime(2026, 9, 28, 9, tzinfo=ZoneInfo("Asia/Tokyo"))
    company = "soraworks-synthetic"
    teams = tuple(Team(team_id=f"team-{i:02}", company_id=company, display_name=name)
                  for i, name in enumerate(("Delivery", "Reporting", "QA", "Enablement")))
    windows = tuple(Window(start=start + timedelta(days=day),
                           end=start + timedelta(days=day, hours=8)) for day in range(5))
    employees, tasks, blocks = [], [], []
    sources = [SourceVersion(source_version_id="working-rule-v1", company_id=company,
                             content="Synthetic company policy: weekdays 09:00–17:00 Asia/Tokyo.")]
    for index in range(25):
        employee_id, team_id = f"employee-{index:02}", teams[index % 4].team_id
        employees.append(Employee(
            employee_id=employee_id, company_id=company, team_id=team_id,
            display_name=f"Synthetic colleague {index + 1:02}",
            confirmed_skills=("delivery-preparation",), working_windows=windows,
            source_version_ref="working-rule-v1",
        ))
        source = f"project-{index:02}-brief-v1"
        sources.append(SourceVersion(
            source_version_id=source, company_id=company,
            content="Synthetic delivery pack: review requirements, prepare materials, check handoff.",
        ))
        for step, title in enumerate(("Review requirements", "Prepare materials", "Check handoff")):
            task_id = f"task-{index:02}-{step}"
            # Explicit arithmetic variation is portable; no wall clock or random global state.
            minutes = 15 * (1 + (seed + index + step) % 3)
            block_start = start + timedelta(hours=step)
            tasks.append(Task(
                task_id=task_id, company_id=company, project_id=f"project-{index:02}",
                team_id=team_id, title=title, effort_minutes=minutes,
                required_skill="delivery-preparation", window=Window(start=start, end=windows[-1].end),
                requested_deadline=windows[-1].end, agreed_deadline=windows[-1].end,
                predecessors=() if step == 0 else (f"task-{index:02}-{step - 1}",),
                protected=step == 0, source_version_ref=source,
            ))
            blocks.append(Block(
                block_id=f"block-{index:02}-{step}", company_id=company,
                task_id=task_id, employee_id=employee_id,
                interval=Window(start=block_start, end=block_start + timedelta(minutes=minutes)),
            ))
    fixture = Fixture(seed=seed, horizon=Window(start=start, end=windows[-1].end),
                      teams=teams, employees=tuple(employees), tasks=tuple(tasks),
                      initial_schedule=tuple(blocks), sources=tuple(sources))
    scenario = Scenario(simulated_at=start - timedelta(minutes=15))
    truth = GroundTruth(
        expected_task_ids=tuple(task.task_id for task in fixture.tasks),
        protected_task_ids=tuple(task.task_id for task in fixture.tasks if task.protected),
        acceptance_checks=("complete schedule", "exclusive active effort", "dependency ordering",
                           "effort totals", "working windows", "agreed deadlines", "protected work"),
    )
    return fixture, scenario, truth
