"""Independent concrete arithmetic checks. Never imports an adapter or planner."""

from collections import Counter, defaultdict

from .contracts import Block, Fixture, GroundTruth, ValidationReport, Violation

COVERAGE = ("entity_and_tenant_references", "complete_single_segment_schedule", "effort",
            "confirmed_skill", "working_and_task_windows", "exclusive_capacity",
            "finish_to_start_dependencies", "agreed_deadlines", "protected_schedule")
UNCHECKED = ("access_and_disclosure", "source_authority", "review_and_acceptance",
             "daily_weekly_budgets", "priority_and_displacement_authority", "approvals",
             "commit_and_sync", "split_and_passive_work", "real_product_correctness")


def score(fixture: Fixture, truth: GroundTruth, schedule: tuple[Block, ...]) -> ValidationReport:
    tasks = {task.task_id: task for task in fixture.tasks}
    employees = {employee.employee_id: employee for employee in fixture.employees}
    if set(truth.expected_task_ids) != set(tasks):
        raise ValueError("ground truth does not match fixture task scope")
    if set(truth.protected_task_ids) != {task.task_id for task in fixture.tasks if task.protected}:
        raise ValueError("ground truth does not match protected scope")
    violations: list[Violation] = []

    def fail(code: str, *refs: str) -> None:
        violations.append(Violation(code=code, entity_refs=tuple(refs)))

    by_task: dict[str, list[Block]] = defaultdict(list)
    by_employee: dict[str, list[Block]] = defaultdict(list)
    for key, count in Counter(block.block_id for block in schedule).items():
        if count > 1:
            fail("duplicate_block", key)
    for block in schedule:
        if block.company_id != fixture.company_id:
            fail("tenant", block.block_id)
        task, employee = tasks.get(block.task_id), employees.get(block.employee_id)
        if task is None or employee is None:
            fail("unknown_reference", block.block_id)
            continue
        by_task[block.task_id].append(block)
        by_employee[block.employee_id].append(block)
        if task.required_skill not in employee.confirmed_skills:
            fail("eligibility", block.block_id)
        start, end = block.interval.start, block.interval.end
        if start < task.window.start or end > task.window.end:
            fail("task_window", block.block_id)
        if not any(window.start <= start and end <= window.end for window in employee.working_windows):
            fail("working_window", block.block_id)
        if start < fixture.horizon.start or end > fixture.horizon.end:
            fail("horizon", block.block_id)
        if end > task.agreed_deadline:
            fail("agreed_deadline", block.block_id)

    for task_id, task in tasks.items():
        blocks = by_task[task_id]
        if len(blocks) != 1:
            fail("schedule_completeness", task_id)
        seconds = sum((block.interval.end - block.interval.start).total_seconds() for block in blocks)
        if seconds != task.effort_minutes * 60:
            fail("effort", task_id)
        if blocks:
            start = min(block.interval.start for block in blocks)
            for predecessor in task.predecessors:
                previous = by_task[predecessor]
                if not previous or max(block.interval.end for block in previous) > start:
                    fail("dependency", predecessor, task_id)
        if task_id in truth.protected_task_ids:
            original = tuple(block for block in fixture.initial_schedule if block.task_id == task_id)
            if tuple(blocks) != original:
                fail("protected_movement", task_id)
    for blocks in by_employee.values():
        ordered = sorted(blocks, key=lambda block: (block.interval.start, block.block_id))
        for index, left in enumerate(ordered):
            for right in ordered[index + 1:]:
                if right.interval.start < left.interval.end:
                    fail("exclusive_overlap", left.block_id, right.block_id)
    return ValidationReport(coverage=COVERAGE, unchecked=UNCHECKED, violations=tuple(violations))
