from __future__ import annotations

from datetime import timedelta

from coordination.interpretation.contracts import (
    CandidateClarification,
    CandidateDeadline,
    CandidateDependency,
    CandidateEstimate,
    CandidateRequirement,
    CandidateTask,
    CandidateTaskContract,
    EvidenceBasis,
)
from coordination.interpretation.gateway import (
    GatewayConfiguration,
    GatewayResponse,
    GeminiInvalidOutputError,
    GeminiRefusalError,
    GeminiTimeoutError,
    ModelUsage,
)
from coordination.interpretation.projection import InterpretationProjection

FIXTURE_MODEL = "fixture:northstar-connected-v1"


class FixtureInterpretationGateway:
    """Deterministic demo adapter that replaces only the external Gemini call."""

    configuration = GatewayConfiguration(
        model=FIXTURE_MODEL,
        prompt_version="fixture-northstar-v1",
        safety_profile="fixture-no-network-no-tools-v1",
        timeout_seconds=1,
        retry_attempts=1,
        max_output_tokens=8192,
    )

    def generate(self, projection: InterpretationProjection) -> GatewayResponse:
        request = projection.original_request.lower()
        if "[fixture:model-refusal]" in request:
            raise GeminiRefusalError("fixture model refusal")
        if "[fixture:model-timeout]" in request:
            raise GeminiTimeoutError("fixture model timeout")
        if "[fixture:model-invalid]" in request:
            raise GeminiInvalidOutputError("fixture invalid structured output")

        sources = [source for source in projection.sources if source.freshness == "current"]
        evidence_by_locator = {
            excerpt.locator: EvidenceBasis(
                kind="evidence",
                source_version_id=source.source_version_id,
                locator=excerpt.locator,
                claim=excerpt.text[:1000],
            )
            for source in sources
            for excerpt in source.excerpts
        }
        required = ("software-release", "hr-onboarding", "shared-specialist")
        if any(locator not in evidence_by_locator for locator in required):
            raise GeminiInvalidOutputError("fixture source pack is incomplete")

        if "[fixture:clarification]" in request:
            contract = CandidateTaskContract(
                schema_version="candidate-task-contract.v1",
                company_id=projection.company_id,
                request_id=projection.request_id,
                request_version=projection.request_version,
                tasks=(),
                dependencies=(),
                assumptions=(),
                clarifications=(
                    CandidateClarification(
                        question_key="confirm_shared_specialist_window",
                        category="missing_data",
                        question="Which approved capacity window may the shared specialist use?",
                        blocks_planning=True,
                        related_task_keys=(),
                    ),
                ),
                unsupported=(),
            )
            return self._response(contract)

        deadline = projection.requested_deadline or projection.retrieved_at + timedelta(days=4)
        task_minutes = 10_020 if "[fixture:solver-infeasible]" in request else 90
        specialist_requirement = CandidateRequirement(
            requirement_key="technical_coordination",
            kind="skill",
            description="Requires the approved shared technical coordination capability.",
            strength="hard",
            minimum_level="approved",
            bases=(evidence_by_locator["shared-specialist"],),
        )
        software = CandidateTask(
            task_key="software_release_readiness",
            title="Prepare the software release readiness pack",
            purpose=(
                "Protect the approved release while incorporating the new coordination request."
            ),
            deliverable="A checked release-readiness pack with owner handoffs recorded.",
            acceptance_criteria=(
                "Release dependencies and rollback ownership are explicitly recorded.",
                "Only the approved software-team source facts are used.",
            ),
            timing_type="flexible_active",
            estimate=CandidateEstimate(
                active_minutes=task_minutes,
                lower_minutes=None,
                upper_minutes=None,
                bases=(evidence_by_locator["software-release"],),
            ),
            deadline=CandidateDeadline(
                requested_at=deadline,
                timezone=projection.requested_deadline_timezone or "Europe/London",
                flexibility="fixed",
                bases=(evidence_by_locator["software-release"],),
            ),
            requirements=(specialist_requirement,),
            bases=(evidence_by_locator["software-release"],),
        )
        onboarding = CandidateTask(
            task_key="onboarding_access_brief",
            title="Prepare the internal onboarding access brief",
            purpose=(
                "Coordinate a new joiner's approved technical access without ranking candidates."
            ),
            deliverable="An employee-shareable access and orientation brief.",
            acceptance_criteria=(
                "The brief lists approved access steps and a named reviewer.",
                "Private HR context is omitted from the employee-facing output.",
            ),
            timing_type="flexible_active",
            estimate=CandidateEstimate(
                active_minutes=task_minutes,
                lower_minutes=None,
                upper_minutes=None,
                bases=(evidence_by_locator["hr-onboarding"],),
            ),
            deadline=CandidateDeadline(
                requested_at=deadline,
                timezone=projection.requested_deadline_timezone or "Europe/London",
                flexibility="fixed",
                bases=(evidence_by_locator["hr-onboarding"],),
            ),
            requirements=(specialist_requirement,),
            bases=(evidence_by_locator["hr-onboarding"],),
        )
        handoff = CandidateTask(
            task_key="cross_team_handoff",
            title="Complete the approved cross-team handoff",
            purpose="Confirm both teams can proceed from the capacity-feasible sequence.",
            deliverable="A concise handoff record with no restricted source excerpts.",
            acceptance_criteria=("Both preceding deliverables are referenced by exact task key.",),
            timing_type="flexible_active",
            estimate=CandidateEstimate(
                active_minutes=30,
                lower_minutes=None,
                upper_minutes=None,
                bases=(evidence_by_locator["shared-specialist"],),
            ),
            deadline=CandidateDeadline(
                requested_at=deadline,
                timezone=projection.requested_deadline_timezone or "Europe/London",
                flexibility="fixed",
                bases=(evidence_by_locator["shared-specialist"],),
            ),
            requirements=(specialist_requirement,),
            bases=(evidence_by_locator["shared-specialist"],),
        )
        dependencies = (
            CandidateDependency(
                predecessor_task_key="software_release_readiness",
                successor_task_key="cross_team_handoff",
                dependency_type="finish_to_start",
                minimum_lag_minutes=0,
                bases=(evidence_by_locator["shared-specialist"],),
            ),
            CandidateDependency(
                predecessor_task_key="onboarding_access_brief",
                successor_task_key="cross_team_handoff",
                dependency_type="finish_to_start",
                minimum_lag_minutes=0,
                bases=(evidence_by_locator["shared-specialist"],),
            ),
        )
        contract = CandidateTaskContract(
            schema_version="candidate-task-contract.v1",
            company_id=projection.company_id,
            request_id=projection.request_id,
            request_version=projection.request_version,
            tasks=(software, onboarding, handoff),
            dependencies=dependencies,
            assumptions=(),
            clarifications=(),
            unsupported=(),
        )
        return self._response(contract)

    @staticmethod
    def _response(contract: CandidateTaskContract) -> GatewayResponse:
        return GatewayResponse(
            contract=contract,
            model_version=FIXTURE_MODEL,
            provider_response_id=None,
            sdk_version="fixture",
            finish_reason="FIXTURE_COMPLETE",
            usage=ModelUsage(
                prompt_tokens=None,
                candidate_tokens=None,
                total_tokens=None,
                thought_tokens=None,
            ),
        )
