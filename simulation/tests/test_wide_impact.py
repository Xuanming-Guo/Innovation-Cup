import unittest

from coordination_sim.benchmark.generation import apply_change, change, generate
from coordination_sim.benchmark.naive import NaiveCoordinator
from coordination_sim.benchmark.trace import Trace
from coordination_sim.benchmark.validation import validate


class WideImpactScenarioTests(unittest.TestCase):
    def test_portfolio_case_is_a_valid_broad_supporting_demo(self):
        initial = generate()
        event = change("portfolio")
        snapshot = apply_change(initial, event)
        trace = Trace("portfolio-test", snapshot.company)
        outcome = NaiveCoordinator().run(snapshot, event, trace)
        report = validate(snapshot, outcome, event.at_slot)
        self.assertEqual(outcome.terminal, "COMPLETED")
        self.assertEqual(report.violations, ())
        before = {block.task_id: block.employee_id for block in snapshot.schedule}
        after = {block.task_id: block.employee_id for block in outcome.schedule}
        owner_changes = {task_id for task_id in event.task_ids if before[task_id] != after[task_id]}
        self.assertEqual(owner_changes, set(event.task_ids))
        self.assertEqual(len(owner_changes), 12)
        self.assertEqual(len(outcome.considered_task_ids), len(snapshot.tasks))
        recipients = {row["detail"].get("recipient") for row in trace.rows if row["action_type"] == "notification_relayed"}
        self.assertGreaterEqual(len(recipients - {None}), 20)
        task = next(task for task in snapshot.tasks if task.task_id == event.task_ids[0])
        self.assertTrue(task.allow_owner_change)
        self.assertEqual(len(task.eligible_owners), 2)
        self.assertEqual(task.movement_authority, "portfolio-rebalance-v1")


if __name__ == "__main__":
    unittest.main()
