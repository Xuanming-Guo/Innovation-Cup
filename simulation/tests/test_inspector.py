import unittest

from coordination_sim.benchmark.generation import apply_change, change, generate
from coordination_sim.benchmark.inspector import company_inspector, coordination_graph
from coordination_sim.benchmark.naive import NaiveCoordinator
from coordination_sim.benchmark.trace import Trace


class InspectorTests(unittest.TestCase):
    def test_company_inspector_indexes_every_synthetic_record_without_source_bodies(self):
        snapshot = generate()
        inspector = company_inspector(snapshot)
        self.assertEqual(inspector["counts"]["employees"], 25)
        self.assertEqual(len(inspector["employees"]), len(snapshot.employees))
        self.assertEqual(len(inspector["tasks"]), len(snapshot.tasks))
        self.assertEqual(len(inspector["projects"]), len(snapshot.projects))
        self.assertEqual(len(inspector["teams"]), len(snapshot.teams))
        self.assertIn("NOT AN AUTHORISATION VIEW", inspector["label"])
        self.assertNotIn("excerpt", repr(inspector).lower())
        employee = next(row for row in inspector["employees"] if row["employee_id"] == "e0006")
        self.assertIn("security", employee["confirmed_skills"])
        self.assertGreater(employee["scheduled_task_count"], 0)

    def test_graph_is_derived_from_typed_relations_and_marks_impact(self):
        initial = generate()
        event = change("A")
        snapshot = apply_change(initial, event)
        outcome = NaiveCoordinator().run(snapshot, event, Trace("inspector-test", snapshot.company))
        graph = coordination_graph(snapshot, event, outcome)
        self.assertEqual(graph["stats"]["direct_tasks"], 5)
        self.assertEqual(graph["stats"]["changed_tasks"], 5)
        self.assertGreaterEqual(graph["stats"]["rendered_employees"], 5)
        self.assertIn("NOT A GRAPH DATABASE", graph["label"])
        kinds = {node["kind"] for node in graph["nodes"]}
        self.assertTrue({"task", "employee", "project", "team", "source"} <= kinds)
        h0 = next(node for node in graph["nodes"] if node["id"] == "task:h0")
        self.assertTrue({"direct", "changed", "affected"} <= set(h0["flags"]))
        edge_kinds = {edge["kind"] for edge in graph["edges"]}
        self.assertTrue({"precedes", "assigned_before", "assigned_after", "grounds"} <= edge_kinds)


if __name__ == "__main__":
    unittest.main()
