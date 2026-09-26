from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from datetime import UTC, datetime
from time import monotonic_ns
from typing import Literal, Protocol
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field

from coordination.interpretation.admission import AdmissionResult, admit_candidate
from coordination.interpretation.gateway import (
    GatewayConfiguration,
    GatewayResponse,
    GeminiGatewayError,
    InterpretationGateway,
)
from coordination.interpretation.projection import InterpretationProjection


class InterpretationBudgetExceededError(ValueError):
    """Raised and recorded before provider access when bounded input policy is exceeded."""

    def __init__(self, run_id: UUID) -> None:
        super().__init__("permission-bounded projection exceeds budget")
        self.run_id = run_id


class InterpretationExecutionError(RuntimeError):
    def __init__(self, *, run_id: UUID, outcome: str, code: str) -> None:
        super().__init__(f"interpretation failed: {code}")
        self.run_id = run_id
        self.outcome = outcome
        self.code = code


class InterpretationOutcome(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    run_id: UUID
    status: Literal["admitted", "clarification_required", "rejected"]
    contract_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    projection_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    admission: AdmissionResult
    response: GatewayResponse
    latency_ms: int = Field(ge=0)


class InterpretationRunRecorder(Protocol):
    def start(
        self,
        *,
        run_id: UUID,
        projection: InterpretationProjection,
        configuration: GatewayConfiguration,
        started_at: datetime,
    ) -> None: ...

    def complete(self, outcome: InterpretationOutcome, *, completed_at: datetime) -> None: ...

    def fail(
        self,
        *,
        run_id: UUID,
        outcome: str,
        error_code: str,
        latency_ms: int,
        completed_at: datetime,
    ) -> None: ...


class InterpretationService:
    def __init__(
        self,
        *,
        gateway: InterpretationGateway,
        recorder: InterpretationRunRecorder,
        max_projection_characters: int = 150_000,
        clock: Callable[[], datetime] | None = None,
        monotonic_clock: Callable[[], int] | None = None,
    ) -> None:
        self._gateway = gateway
        self._recorder = recorder
        self._max_projection_characters = max_projection_characters
        self._clock = clock or (lambda: datetime.now(UTC))
        self._monotonic_clock = monotonic_clock or monotonic_ns

    def interpret(self, projection: InterpretationProjection) -> InterpretationOutcome:
        projection_payload = projection.canonical_json()
        run_id = uuid4()
        started_at = self._clock()
        started_ns = self._monotonic_clock()
        self._recorder.start(
            run_id=run_id,
            projection=projection,
            configuration=self._gateway.configuration,
            started_at=started_at,
        )
        if len(projection_payload) > self._max_projection_characters:
            latency_ms = max(0, (self._monotonic_clock() - started_ns) // 1_000_000)
            self._recorder.fail(
                run_id=run_id,
                outcome="budget_exhausted",
                error_code="projection_budget_exhausted",
                latency_ms=latency_ms,
                completed_at=self._clock(),
            )
            raise InterpretationBudgetExceededError(run_id)
        try:
            response = self._gateway.generate(projection)
        except GeminiGatewayError as error:
            latency_ms = max(0, (self._monotonic_clock() - started_ns) // 1_000_000)
            self._recorder.fail(
                run_id=run_id,
                outcome=error.outcome,
                error_code=error.code,
                latency_ms=latency_ms,
                completed_at=self._clock(),
            )
            raise InterpretationExecutionError(
                run_id=run_id,
                outcome=error.outcome,
                code=error.code,
            ) from error

        admission = admit_candidate(response.contract, projection, now=self._clock())
        contract_json = json.dumps(
            response.contract.model_dump(mode="json"),
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
        latency_ms = max(0, (self._monotonic_clock() - started_ns) // 1_000_000)
        result = InterpretationOutcome(
            run_id=run_id,
            status=admission.status,
            contract_digest=hashlib.sha256(contract_json.encode("utf-8")).hexdigest(),
            projection_digest=projection.digest,
            admission=admission,
            response=response,
            latency_ms=latency_ms,
        )
        self._recorder.complete(result, completed_at=self._clock())
        return result
