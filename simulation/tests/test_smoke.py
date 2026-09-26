from __future__ import annotations

import ast
import hashlib
import json
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory

from pydantic import ValidationError

from coordination_sim import REPLAY_LABEL
from coordination_sim.contracts import Fixture, MetricObservation, Window
from coordination_sim.generation import tiny
from coordination_sim.replay import AuthoredReplay, input_manifest
from coordination_sim.runner import EXAMPLE, ROOT, run_directory, smoke
from coordination_sim.scoring import score
from coordination_sim.serialization import digest


class FixtureTests(unittest.TestCase):
    def setUp(self):
        self.fixture, self.scenario, self.truth = tiny()

    def test_tiny_totals_and_reproducibility(self):
        self.assertEqual((len(self.fixture.employees), len(self.fixture.teams), len(self.fixture.tasks)),
                         (25, 4, 75))
        self.assertEqual(digest(self.fixture), digest(tiny()[0]))
        self.assertNotEqual(digest(self.fixture), digest(tiny(18)[0]))
        self.assertEqual(len({task.project_id for task in self.fixture.tasks}), 25)
        self.assertEqual(len(self.fixture.employees[0].working_windows), 5)

    def test_initial_schedule_and_flexible_windows(self):
        self.assertEqual(score(self.fixture, self.truth, self.fixture.initial_schedule).violations, ())
        self.assertEqual(self.fixture.tasks[0].window, self.fixture.tasks[1].window)

    def test_bad_fixture_inputs_rejected(self):
        original = self.fixture.model_dump(mode="json")
        for mutate in (
            lambda obj: obj["tasks"][0].update(effort_minutes=-1),
            lambda obj: obj["tasks"][0].update(effort_minutes=True),
            lambda obj: obj["tasks"][0].update(company_id="second-tenant"),
            lambda obj: obj["tasks"][0].update(predecessors=["missing-task"]),
            lambda obj: obj["tasks"][0].update(predecessors=["task-00-2"]),
            lambda obj: obj["tasks"][0].update(unimplemented_review=True),
            lambda obj: obj["tasks"][0].update(source_version_ref="missing-source"),
        ):
            with self.subTest(mutate=mutate):
                candidate = json.loads(json.dumps(original))
                mutate(candidate)
                with self.assertRaises(ValidationError):
                    Fixture.model_validate(candidate)

    def test_naive_time_and_invalid_json_rejected(self):
        with self.assertRaises(ValidationError):
            Window(start=datetime(2026, 9, 28, 9), end=datetime(2026, 9, 28, 10))
        with self.assertRaises(ValidationError):
            Fixture.model_validate_json("not JSON")

    def test_gold_labels_not_in_method_input(self):
        inputs = json.dumps(input_manifest(self.fixture, self.scenario))
        self.assertNotIn("expected_task_ids", inputs)
        self.assertNotIn("expected_class", inputs)
        self.assertNotIn("acceptance_checks", inputs)


class ScorerTests(unittest.TestCase):
    def setUp(self):
        self.fixture, _, self.truth = tiny()
        self.blocks = self.fixture.initial_schedule

    def codes(self, blocks):
        return {item.code for item in score(self.fixture, self.truth, tuple(blocks)).violations}

    def test_missing_duplicate_and_unknown_assignments(self):
        self.assertIn("schedule_completeness", self.codes(self.blocks[1:]))
        self.assertIn("duplicate_block", self.codes((*self.blocks, self.blocks[0])))
        changed = self.blocks[0].model_copy(update={"employee_id": "unknown"})
        self.assertIn("unknown_reference", self.codes((changed, *self.blocks[1:])))

    def test_mutations_detect_effort_capacity_dependency_protection_and_tenant(self):
        first, second = self.blocks[:2]
        longer = first.model_copy(update={"interval": Window(
            start=first.interval.start, end=first.interval.end + timedelta(hours=2))})
        codes = self.codes((longer, *self.blocks[1:]))
        self.assertTrue({"effort", "exclusive_overlap", "dependency", "protected_movement"} <= codes)
        foreign = second.model_copy(update={"company_id": "second-tenant"})
        self.assertIn("tenant", self.codes((first, foreign, *self.blocks[2:])))

    def test_working_window_and_deadline_mutation(self):
        first = self.blocks[0]
        later = first.model_copy(update={"interval": Window(
            start=first.interval.start + timedelta(days=7), end=first.interval.end + timedelta(days=7))})
        self.assertTrue({"working_window", "task_window", "agreed_deadline", "horizon"}
                        <= self.codes((later, *self.blocks[1:])))

    def test_touching_half_open_intervals_are_allowed(self):
        first, second = self.blocks[:2]
        duration = second.interval.end - second.interval.start
        adjacent = second.model_copy(update={"interval": Window(
            start=first.interval.end, end=first.interval.end + duration)})
        self.assertEqual(self.codes((first, adjacent, *self.blocks[2:])), set())

    def test_skill_and_ground_truth_are_checked(self):
        employee = self.fixture.employees[0].model_copy(update={"confirmed_skills": ()})
        fixture = self.fixture.model_copy(update={"employees": (employee, *self.fixture.employees[1:])})
        self.assertIn("eligibility", {row.code for row in score(fixture, self.truth, self.blocks).violations})
        with self.assertRaises(ValueError):
            score(self.fixture, self.truth.model_copy(update={"expected_task_ids": ()}), self.blocks)


class ReplayTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.run_path = smoke()
        cls.manifest = json.loads((cls.run_path / "manifest.json").read_text())

    def test_replay_is_verbatim_and_hash_bound(self):
        fixture, scenario, _ = tiny()
        schedule = AuthoredReplay(EXAMPLE).run(fixture, scenario)
        raw = json.loads(EXAMPLE.read_text())
        self.assertEqual([block.model_dump(mode="json") for block in schedule], raw["schedule"])
        other, scenario, _ = tiny(18)
        with self.assertRaisesRegex(ValueError, "REPLAY_INPUT_MISMATCH"):
            AuthoredReplay(EXAMPLE).run(other, scenario)

    def test_measured_metric_and_no_product_claim(self):
        metric = MetricObservation.model_validate_json((self.run_path / "metric.json").read_bytes())
        self.assertEqual((metric.status, metric.value), ("MEASURED", 0))
        self.assertEqual(metric.evidence_class, "recorded_replay")
        self.assertEqual(self.manifest["label"], REPLAY_LABEL)
        self.assertEqual(self.manifest["product_result"]["status"], "NOT_RUN")
        self.assertIsNone(self.manifest["product_result"]["value"])
        self.assertEqual(self.manifest["specification_version"], "0.5.0")
        self.assertEqual(self.manifest["provenance"], "authored_synthetic_example_not_product_capture")
        definition = json.loads((self.run_path / "metric_registry.json").read_text())["metrics"][0]
        self.assertEqual(definition["metric_id"], metric.metric_id)
        self.assertEqual(definition["definition_version"], metric.metric_definition_version)
        self.assertEqual(definition["unit"], metric.unit)

    def test_artifact_integrity_and_trace_causality(self):
        for name, expected in self.manifest["artifact_sha256"].items():
            self.assertEqual(hashlib.sha256((self.run_path / name).read_bytes()).hexdigest(), expected)
        events = [json.loads(line) for line in (self.run_path / "trace.jsonl").read_text().splitlines()]
        self.assertEqual(len(events), 5)
        for sequence, row in enumerate(events, 1):
            self.assertEqual(row["sequence_number"], sequence)
            self.assertEqual(row["causation_event_id"], None if sequence == 1 else f"event-{sequence - 1:03}")
            self.assertIn(row["event_origin"], ("harness", "replay"))
            for reference in (*row["input_refs"], *row["output_refs"]):
                self.assertTrue((self.run_path / reference.split("#")[0]).exists(), reference)

    def test_same_input_reproduces_semantic_artifacts_and_trace(self):
        again = smoke()
        manifest = json.loads((again / "manifest.json").read_text())
        for field in ("input_digest", "ground_truth_digest", "deterministic_trace_digest"):
            self.assertEqual(self.manifest[field], manifest[field])
        for filename in ("fixture.json", "scenario.json", "ground_truth.json", "outcome.json", "validation.json"):
            self.assertEqual((self.run_path / filename).read_bytes(), (again / filename).read_bytes())
        self.assertNotEqual(self.manifest["run_id"], manifest["run_id"])

    def test_missing_and_mismatched_replay_preserve_failed_runs(self):
        for kwargs in ({"example": ROOT / "fixtures/absent.json"}, {"seed": 18}):
            with self.subTest(kwargs=kwargs):
                target = smoke(**kwargs)
                manifest = json.loads((target / "manifest.json").read_text())
                metric = json.loads((target / "metric.json").read_text())
                self.assertEqual(manifest["status"], "FAILED")
                self.assertEqual(metric["status"], "NOT_MEASURED")
                self.assertIsNone(metric["value"])
                self.assertTrue(metric["missing_or_invalid_reason"])
                self.assertEqual(manifest["product_result"]["status"], "NOT_RUN")

    def test_mutated_replay_is_scored_and_retained_as_invalid(self):
        (ROOT / ".tmp").mkdir(exist_ok=True)
        with TemporaryDirectory(dir=ROOT / ".tmp") as directory:
            candidate = json.loads(EXAMPLE.read_text())
            candidate["schedule"] = candidate["schedule"][1:]
            path = Path(directory) / "bad-replay.json"
            path.write_text(json.dumps(candidate))
            target = smoke(example=path)
            manifest = json.loads((target / "manifest.json").read_text())
            metric = json.loads((target / "metric.json").read_text())
            self.assertEqual(manifest["status"], "INVALID")
            self.assertEqual(metric["status"], "MEASURED")
            # Missing first task: completeness, effort, protection, successor dependency.
            self.assertEqual(metric["value"], 4)

    def test_overwrite_and_output_escape_rejected(self):
        with self.assertRaises(FileExistsError):
            smoke(run_id=self.manifest["run_id"])
        with self.assertRaises(ValueError):
            run_directory("../../outside")

    def test_unmeasured_cannot_be_zero(self):
        with self.assertRaises(ValidationError):
            MetricObservation(run_id="r", scenario_id="s", value=0, status="NOT_MEASURED",
                              missing_or_invalid_reason="no evidence")

    def test_architecture_does_not_import_product_or_scoring_into_replay(self):
        forbidden = {"coordination", "z3", "fastapi", "supabase", "google", "requests", "httpx"}
        for path in (ROOT / "coordination_sim").glob("*.py"):
            for node in ast.walk(ast.parse(path.read_text())):
                if isinstance(node, ast.Import):
                    names = [alias.name.split(".")[0] for alias in node.names]
                elif isinstance(node, ast.ImportFrom):
                    names = [(node.module or "").split(".")[0]]
                else:
                    continue
                self.assertFalse(forbidden.intersection(names), path)
                if path.name == "replay.py":
                    self.assertNotIn("scoring", names)
                if path.name == "scoring.py":
                    self.assertFalse({"replay", "generation", "runner"}.intersection(names))


class BoundaryTests(unittest.TestCase):
    def test_parent_change_is_detected_without_writing_parent(self):
        from unittest.mock import patch
        from scripts import check_boundary

        def fake_git(*args):
            if args[0] == "rev-parse":
                return check_boundary.EXPECTED_HEAD
            if args[0] == "branch":
                return check_boundary.EXPECTED_BRANCH
            if args[0] == "status":
                return " M docs/implementation-status.md\0"
            return ""

        with patch.object(check_boundary, "git", side_effect=fake_git):
            self.assertIn("repository change outside allowed simulation additions/edits", check_boundary.check())

    def test_actual_boundary_is_clean(self):
        from scripts.check_boundary import check

        self.assertEqual(check(), [])


if __name__ == "__main__":
    unittest.main()
