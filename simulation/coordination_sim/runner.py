"""A bounded fixture → authored replay → independent score → observation run."""

from __future__ import annotations

import hashlib
import json
import platform
import subprocess
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

from . import HARNESS_VERSION, REPLAY_LABEL, SCHEMA_VERSION, SPEC_VERSION
from .contracts import MetricObservation
from .generation import tiny
from .replay import AuthoredReplay, input_manifest, product_status
from .scoring import score
from .serialization import canonical, digest, write_json

ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / "fixtures/replays/tiny-no-impact.v1.json"


def run_directory(run_id: str) -> Path:
    runs = (ROOT / "runs").resolve()
    if not runs.is_relative_to(ROOT) or runs == ROOT:
        raise ValueError("output directory escapes simulation")
    runs.mkdir(exist_ok=True)
    target = (runs / run_id).resolve()
    if target.parent != runs:
        raise ValueError("invalid run ID")
    target.mkdir()  # Refuse overwrites, including failed historical runs.
    return target


def git_head() -> str:
    return subprocess.check_output(
        ["git", "--no-optional-locks", "rev-parse", "HEAD"], cwd=ROOT, text=True,
    ).strip()


def implementation_hash() -> str:
    paths = sorted((ROOT / "coordination_sim").glob("*.py")) + [
        ROOT / "pyproject.toml", ROOT / "uv.lock", ROOT / "metrics/registry.v1.json",
    ]
    return digest({str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest()
                   for path in paths})


def smoke(seed: int = 17, example: Path = EXAMPLE, run_id: str | None = None) -> Path:
    if type(seed) is not int or seed < 0:
        raise ValueError("seed must be a nonnegative integer")
    run_id = run_id or f"smoke-{uuid.uuid4().hex}"
    target = run_directory(run_id)
    started = datetime.now(timezone.utc)
    monotonic_start = time.monotonic()
    fixture, scenario, truth = tiny(seed)
    inputs = input_manifest(fixture, scenario)
    for name, value in (("fixture.json", fixture), ("scenario.json", scenario),
                        ("ground_truth.json", truth), ("input_manifest.json", inputs)):
        write_json(target / name, value)
    write_json(target / "metric_registry.json", json.loads((ROOT / "metrics/registry.v1.json").read_text()))

    events: list[dict] = []

    def event(action: str, summary: str, status: str, inputs: tuple[str, ...],
              outputs: tuple[str, ...], before: str | None = None,
              after: str | None = None, error: str | None = None) -> None:
        sequence = len(events) + 1
        row = {
            "schema_version": SCHEMA_VERSION, "event_id": f"event-{sequence:03}",
            "run_id": run_id, "scenario_id": scenario.scenario_id,
            "approach": "product_replay", "event_origin": "replay" if action == "replay_loaded" else "harness",
            "sequence_number": sequence,
            "simulated_at": (scenario.simulated_at + timedelta(seconds=sequence - 1)).isoformat(),
            "recorded_at": datetime.now(timezone.utc).isoformat(),
            "correlation_id": scenario.scenario_id,
            "causation_event_id": None if sequence == 1 else events[-1]["event_id"],
            "actor_id": "harness-observer", "actor_type": "benchmark",
            "actor_role": "observer", "actor_scope_refs": [fixture.company_id],
            "action_type": action, "phase": "bootstrap_smoke", "status": status,
            "summary": summary, "input_refs": inputs, "output_refs": outputs,
            "source_version_refs": [], "constraint_refs": [],
            "authorization_basis_refs": ["synthetic-bootstrap-scope"],
            "affected_entity_refs": [], "state_before_hash": before,
            "state_after_hash": after, "duration_ms": None,
            "error_code": error, "error_summary": error,
            "visibility_labels": ["judge_only", "synthetic", REPLAY_LABEL],
        }
        with (target / "trace.jsonl").open("ab") as stream:
            stream.write(canonical(row) + b"\n")
        events.append(row)

    terminal = "FAILED"
    error_code = None
    metric_value = None
    replay_hash = None
    event("fixture_generated", "Generated tiny synthetic fixture and separate expected labels.",
          "succeeded", (), ("fixture.json", "scenario.json", "ground_truth.json"), after=digest(inputs))
    try:
        initial = score(fixture, truth, fixture.initial_schedule)
        write_json(target / "initial_validation.json", initial)
        if initial.violations:
            raise ValueError("INITIAL_FIXTURE_INVALID")
        # Keep the actual replay bytes in each run so a later fixture edit cannot rewrite history.
        replay_bytes = example.read_bytes()
        with (target / "replay_input.json").open("xb") as stream:
            stream.write(replay_bytes)
        replay_hash = hashlib.sha256(replay_bytes).hexdigest()
        schedule = AuthoredReplay(target / "replay_input.json").run(fixture, scenario)
        outcome = {"label": REPLAY_LABEL, "origin": "authored_synthetic_example_not_product_capture",
                   "schedule": [block.model_dump(mode="json") for block in schedule]}
        write_json(target / "outcome.json", outcome)
        event("replay_loaded", "Loaded authored example schedule; no product executed.", "succeeded",
              ("input_manifest.json", "replay_input.json"), ("outcome.json",),
              before=digest(inputs), after=digest(outcome))
        report = score(fixture, truth, schedule)
        write_json(target / "validation.json", report)
        metric_value = len(report.violations)
        event("candidate_validated", f"Neutral bootstrap checks found {metric_value} violations.",
              "succeeded" if metric_value == 0 else "failed", ("outcome.json", "ground_truth.json"),
              ("validation.json",), before=digest(outcome), after=digest(report))
        terminal = "COMPLETED" if metric_value == 0 else "INVALID"
    except (OSError, ValueError) as error:
        # Do not serialize arbitrary input bodies or full exception strings into exports.
        error_code = "REPLAY_UNAVAILABLE" if isinstance(error, OSError) else "INVALID_INPUT_OR_REPLAY"
        event("run_failed", "Smoke input or replay evidence was unavailable or invalid.", "failed",
              ("input_manifest.json",), (), error=error_code)

    observation = MetricObservation(
        run_id=run_id, scenario_id=scenario.scenario_id, value=metric_value,
        status="MEASURED" if metric_value is not None else "NOT_MEASURED",
        missing_or_invalid_reason=error_code,
        source_event_or_artifact_refs=("trace.jsonl#event-003", "validation.json", "outcome.json", "ground_truth.json")
        if metric_value is not None else ("trace.jsonl#event-002", "input_manifest.json"),
        numerator_and_denominator_refs=("validation.json#/violations", "fixture.json#/tasks")
        if metric_value is not None else ("fixture.json#/tasks",),
    )
    write_json(target / "metric.json", observation)
    event("metric_recorded", f"Recorded bootstrap metric as {observation.status}.", "succeeded",
          observation.source_event_or_artifact_refs, ("metric.json",))
    event("run_completed", f"Replay smoke ended {terminal}; ALTO remains NOT_RUN.",
          "succeeded" if terminal == "COMPLETED" else "failed", ("metric.json",), ("manifest.json",))
    with (target / "timeline.txt").open("x", encoding="utf-8") as stream:
        stream.write(REPLAY_LABEL + "\n")
        for row in events:
            stream.write(f"{row['sequence_number']:03} {row['action_type']}: {row['summary']}\n")
    deterministic_events = [{key: value for key, value in row.items() if key not in {"run_id", "recorded_at"}}
                            for row in events]
    artifacts = {path.name: hashlib.sha256(path.read_bytes()).hexdigest()
                 for path in sorted(target.iterdir()) if path.is_file()}
    manifest = {
        "specification_version": SPEC_VERSION, "harness_version": HARNESS_VERSION,
        "schema_version": SCHEMA_VERSION, "run_id": run_id, "scenario_id": scenario.scenario_id,
        "scenario_version": scenario.scenario_version, "seed": seed, "preset": "tiny",
        "label": REPLAY_LABEL, "approach": "product_replay", "evidence_class": "recorded_replay",
        "provenance": "authored_synthetic_example_not_product_capture",
        "status": terminal, "error_code": error_code, "product_result": product_status(),
        "input_digest": digest(inputs), "ground_truth_digest": digest(truth),
        "replay_sha256": replay_hash, "deterministic_trace_digest": digest(deterministic_events),
        "harness_git_head": git_head(), "implementation_digest": implementation_hash(),
        "source_state": "working-tree content identified by implementation_digest; not a new commit",
        "runtime": {"python": platform.python_version(), "os": platform.system(),
                    "os_release": platform.release(), "machine": platform.machine()},
        "started_at": started.isoformat(), "ended_at": datetime.now(timezone.utc).isoformat(),
        "harness_wall_seconds": time.monotonic() - monotonic_start,
        "runtime_exclusions": ["run_id", "recorded_at", "started_at", "ended_at", "harness_wall_seconds"],
        "limits": {"preset": "tiny", "tasks": 75, "product_calls": 0, "model_calls": 0},
        "connector_modes": {}, "model_metrics": {"status": "NOT_MEASURED", "value": None,
                                                    "reason": "No model was called."},
        "artifact_sha256": artifacts,
    }
    write_json(target / "manifest.json", manifest)
    return target


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description=REPLAY_LABEL)
    parser.add_argument("command", choices=("smoke", "schemas"))
    parser.add_argument("--seed", type=int, default=17)
    args = parser.parse_args()
    if args.seed < 0:
        parser.error("seed must be nonnegative")
    if args.command == "schemas":
        from .contracts import Fixture, GroundTruth, ReplayExample, Scenario, ValidationReport
        target = run_directory(f"schemas-{uuid.uuid4().hex}")
        for model in (Fixture, GroundTruth, ReplayExample, Scenario, ValidationReport, MetricObservation):
            write_json(target / f"{model.__name__}.schema.json", model.model_json_schema())
        print(target.relative_to(ROOT))
        return 0
    target = smoke(seed=args.seed)
    manifest = json.loads((target / "manifest.json").read_text())
    metric = json.loads((target / "metric.json").read_text())
    print(REPLAY_LABEL)
    print(f"{manifest['status']}: {metric['metric_id']}={metric['value']} ({metric['status']})")
    print("ALTO: NOT_RUN")
    print(target.relative_to(ROOT))
    return 0 if manifest["status"] == "COMPLETED" else 1
