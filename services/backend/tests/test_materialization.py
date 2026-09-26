from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest

from coordination.interpretation.fixture_gateway import FixtureInterpretationGateway
from coordination.interpretation.gateway import GeminiInvalidOutputError, GeminiRefusalError
from coordination.interpretation.projection import (
    EvidenceExcerpt,
    InterpretationProjection,
    SourceVersionEvidence,
)
from coordination.planning.engine import PlanningEngine
from coordination.planning.materializer import (
    AvailabilityWindow,
    MaterializationInput,
    PlanningResourceProfile,
    materialize_candidate,
)

COMPANY_ID = UUID("11111111-1111-4111-8111-111111111111")
REQUEST_ID = UUID("11111111-0000-4111-8111-111111111801")
CANDIDATE_ID = UUID("11111111-0000-4111-8111-111111111802")
MEMBERSHIP_ID = UUID("11111111-0000-4111-8111-111111111101")
SOURCE_ID = UUID("11111111-0000-4111-8111-111111111501")
VERSION_ID = UUID("11111111-0000-4111-8111-111111111601")
MANAGER_ID = UUID("11111111-0000-4111-8111-111111111201")
SPECIALIST_ID = UUID("11111111-0000-4111-8111-111111111202")
START = datetime(2026, 9, 28, 9, tzinfo=UTC)


def projection(
    prompt: str = "Coordinate the approved cross-team change",
) -> InterpretationProjection:
    return InterpretationProjection(
        projection_version="interpretation-projection.v1",
        company_id=COMPANY_ID,
        request_id=REQUEST_ID,
        request_version=1,
        original_request=prompt,
        retrieved_at=START - timedelta(days=1),
        requested_priority_key="high",
        requested_deadline=START + timedelta(hours=8),
        requested_deadline_timezone="Europe/London",
        sources=(
            SourceVersionEvidence(
                source_id=SOURCE_ID,
                source_version_id=VERSION_ID,
                source_kind="fixture",
                authority_status="authoritative",
                classification="internal",
                retrieved_at=START - timedelta(days=1),
                expires_at=START + timedelta(days=30),
                freshness="current",
                content_sha256_hex="11" * 32,
                excerpts=(
                    EvidenceExcerpt(locator="software-release", text="Approved release facts."),
                    EvidenceExcerpt(locator="hr-onboarding", text="Approved onboarding facts."),
                    EvidenceExcerpt(
                        locator="shared-specialist", text="Approved shared capacity facts."
                    ),
                ),
            ),
        ),
        employees=(),
        commitments=(),
        capacity=(),
        dependencies=(),
        supported_constraint_types=("task",),
        missing_data=(),
    )


def resources() -> tuple[PlanningResourceProfile, ...]:
    availability = (
        AvailabilityWindow(start_at=START, end_at=START + timedelta(hours=8)),
    )
    return (
        PlanningResourceProfile(
            resource_id=MANAGER_ID,
            timezone="Europe/London",
            availability=availability,
            capability_keys=("manager_review",),
            permission_keys=("approve_plan",),
            daily_active_minutes=360,
            profile_revision=1,
            estimate_revision=1,
        ),
        PlanningResourceProfile(
            resource_id=SPECIALIST_ID,
            timezone="Europe/London",
            availability=availability,
            capability_keys=("technical_coordination",),
            permission_keys=("internal_delivery",),
            daily_active_minutes=360,
            profile_revision=1,
            estimate_revision=1,
        ),
    )


def materialization(
    prompt: str = "Coordinate the approved cross-team change",
) -> MaterializationInput:
    gateway_response = FixtureInterpretationGateway().generate(projection(prompt))
    return MaterializationInput(
        candidate_contract_id=CANDIDATE_ID,
        contract=gateway_response.contract,
        source_manifest_digest=projection(prompt).digest,
        selected_source_version_ids=(VERSION_ID,),
        base_company_revision=0,
        policy_revision=0,
        requested_priority_key="high",
        requester_membership_id=MEMBERSHIP_ID,
        resources=resources(),
        frozen_at=START - timedelta(hours=1),
    )


def test_fixture_candidate_materializes_and_real_z3_uses_the_shared_specialist() -> None:
    snapshot = materialize_candidate(materialization())
    decision = PlanningEngine().plan(snapshot)

    assert decision.classification in {"FEASIBLE", "OPTIMAL_WITHIN_MODEL"}
    selected = decision.attempts[decision.selected_attempt or 0]
    assert selected.validation is not None and selected.validation.valid
    assert {placement.owner_resource_id for placement in selected.placements} == {SPECIALIST_ID}
    assert len(selected.placements) == 3


def test_fixture_solver_failure_is_repeatable() -> None:
    snapshot = materialize_candidate(
        materialization("Coordinate this [fixture:solver-infeasible]")
    )
    decision = PlanningEngine().plan(snapshot)

    assert decision.classification == "INFEASIBLE_WITHIN_SCOPE"
    assert decision.selected_attempt is None


@pytest.mark.parametrize(
    ("directive", "error_type"),
    [
        ("[fixture:model-refusal]", GeminiRefusalError),
        ("[fixture:model-invalid]", GeminiInvalidOutputError),
    ],
)
def test_fixture_model_failures_are_explicit(
    directive: str, error_type: type[Exception]
) -> None:
    with pytest.raises(error_type):
        FixtureInterpretationGateway().generate(projection(directive))
