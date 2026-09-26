"""One-time authored example exporter; not an execution/capture of a product.

Use PYTHONPATH=. .venv/bin/python -B scripts/generate_replay_example.py.
Refuses to overwrite the reviewed v1 reference; changes require a new version.
"""

from coordination_sim import REPLAY_LABEL
from coordination_sim.contracts import ReplayExample
from coordination_sim.generation import tiny
from coordination_sim.replay import input_manifest
from coordination_sim.runner import EXAMPLE, ROOT
from coordination_sim.scoring import score
from coordination_sim.serialization import digest, write_json


def main() -> None:
    fixture, scenario, truth = tiny(17)
    if score(fixture, truth, fixture.initial_schedule).violations:
        raise ValueError("cannot export an invalid starting schedule")
    if not EXAMPLE.resolve().is_relative_to(ROOT):
        raise ValueError("example output must stay inside simulation")
    EXAMPLE.parent.mkdir(parents=True, exist_ok=True)
    example = ReplayExample(
        provenance="authored_synthetic_example_not_product_capture", label=REPLAY_LABEL,
        input_digest=digest(input_manifest(fixture, scenario)), schedule=fixture.initial_schedule,
    )
    write_json(EXAMPLE, example)
    print(f"Authored synthetic reference only: {EXAMPLE.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
