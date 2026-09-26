"""Replay authored evidence verbatim; never generate or repair a product plan."""

from pathlib import Path
from typing import Protocol

from .contracts import Block, Fixture, ReplayExample, Scenario
from .serialization import digest


def input_manifest(fixture: Fixture, scenario: Scenario) -> dict:
    # Ground truth is intentionally absent from the method input and its signature.
    return {"fixture": fixture.model_dump(mode="json"), "event": scenario.model_dump(mode="json")}


class ReplayPort(Protocol):
    def run(self, fixture: Fixture, scenario: Scenario) -> tuple[Block, ...]: ...


class AuthoredReplay:
    def __init__(self, path: Path):
        self.path = path

    def run(self, fixture: Fixture, scenario: Scenario) -> tuple[Block, ...]:
        example = ReplayExample.model_validate_json(self.path.read_bytes())
        if example.input_digest != digest(input_manifest(fixture, scenario)):
            raise ValueError("REPLAY_INPUT_MISMATCH")
        return example.schedule


def product_status() -> dict:
    return {
        "status": "NOT_RUN", "value": None, "adapter": "NOT IMPLEMENTED",
        "reason": "A real product build and supported seed/reset/drive/export API are required.",
        "product_commit": None, "api_version": None, "mapping_equivalence": "NOT_AVAILABLE",
        "solver": "NOT_AVAILABLE", "interpretation": "NOT_AVAILABLE",
        "approval": "NOT_AVAILABLE", "commitment": "NOT_AVAILABLE",
        "synchronisation": "NOT_AVAILABLE", "acceptance": "NOT_AVAILABLE",
    }
