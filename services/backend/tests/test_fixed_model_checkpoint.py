from contextlib import contextmanager
from types import SimpleNamespace
from typing import Any, cast
from uuid import uuid4

import pytest

from coordination.auth.models import AuthenticatedUser, CompanyContext
from coordination.planning.contracts import PlanningSnapshot, canonical_digest
from coordination.planning.fixed_persistence import PostgresFixedCandidateLedger


@pytest.mark.parametrize("prompt_version", [None, "alto-plan-author.v2"])
def test_model_checkpoint_records_exact_prompt_version_and_configuration(
    monkeypatch: pytest.MonkeyPatch, prompt_version: str | None
) -> None:
    writes: list[tuple[Any, ...]] = []
    ledger = PostgresFixedCandidateLedger(
        "postgresql://unused", job_id=uuid4(), lease_token=uuid4()
    )

    @contextmanager
    def transaction(*_: Any) -> Any:
        yield SimpleNamespace(execute=lambda _sql, params: writes.append(params))

    monkeypatch.setattr(ledger, "_transaction", transaction)
    context = CompanyContext(
        actor=AuthenticatedUser(uuid4(), "authenticated", uuid4(), "aal1"),
        company_id=uuid4(),
        membership_id=uuid4(),
        administrative_role="manager",
        employee_id=None,
    )
    snapshot = cast(
        PlanningSnapshot,
        SimpleNamespace(
            request_id=uuid4(),
            source_manifest_digest="a" * 64,
        ),
    )
    configuration: dict[str, object] = {"max_output_tokens": 32768}
    if prompt_version is not None:
        configuration["prompt_version"] = prompt_version
    ledger.begin_model_run(
        context=context,
        snapshot=snapshot,
        model_run_id=uuid4(),
        parent_run_id=None,
        operation="plan.revise.v1",
        model="unit-only",
        configuration=configuration,
        input_digest="b" * 64,
    )
    assert len(writes) == 1
    assert writes[0][3] == "plan.revise"
    assert writes[0][7] == (prompt_version or "plan.revise.v1")
    assert writes[0][8] == bytes.fromhex(canonical_digest(configuration))
