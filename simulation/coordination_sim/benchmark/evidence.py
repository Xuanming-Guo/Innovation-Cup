"""Optional observed product evidence contracts. These never execute transitions."""
from typing import Literal
from pydantic import AwareDatetime, Field
from ..contracts import Contract


class EvidenceReference(Contract):
    source_version_ref: str
    locator: str
    authority_ref: str
    permission_version: str


class SummaryCache(Contract):
    summary_id: str
    source_versions: tuple[str, ...]
    derivation_version: str
    audience: tuple[str, ...]
    invalidated_at: AwareDatetime | None = None
    canonical_fact: Literal[False] = False


class InterpretationEvidence(Contract):
    candidate_contract_ref: str | None = None
    validated_constraint_refs: tuple[str, ...] = ()
    planning_snapshot_ref: str | None = None
    compiled_model_ref: str | None = None
    model_id: str | None = None
    prompt_version: str | None = None
    configuration_version: str | None = None
    status: str = 'NOT_AVAILABLE'


class CommitmentEvidence(Contract):
    proposal_digest: str
    base_revision: int
    committed_revision: int
    approved_digest: str
    approved_by: tuple[str, ...]
    authority_rechecked: bool
    permission_version: str
    observed_event_ref: str


class ExternalActionEvidence(Contract):
    action_id: str
    company_id: str
    proposal_digest: str
    provider: str
    idempotency_key: str
    expected_version: str
    observed_version: str | None = None
    status: Literal['pending','succeeded','unknown','failed','reconciled']
    attempts: int
    effect_ids: tuple[str, ...]
    observed_event_ref: str
    wrong_effect: bool = False
    overwrote_later_edit: bool = False
    approval_matched: bool


class NotificationEvidence(Contract):
    notification_id: str
    recipient_id: str
    persisted: bool
    signal_has_content: bool
    delivered: bool
    authorised_refetch: bool
    acknowledged: bool
    observed_event_ref: str


class SubmissionEvidence(Contract):
    task_id: str
    submission_id: str
    version: str
    submitted_by: str
    artifact_refs: tuple[str, ...]
    submitted_at: AwareDatetime


class ReviewEvidence(Contract):
    submission_id: str
    submission_version: str
    reviewer_id: str
    decision: Literal['accepted','revision_requested']
    observed_event_ref: str


class WorkloadEvidence(Contract):
    task_id: str
    employee_id: str
    event_kind: Literal['assigned','started','blocked','submitted','accepted']
    active_minutes: int | None = None
    elapsed_minutes: int | None = None
    maturity: Literal['exposure','submission','accepted']
    source_ref: str


class EstimateEvidence(Contract):
    task_id: str
    method: Literal['class_prior','skills_only','recent_context']
    prediction_version: str
    training_cutoff: AwareDatetime
    predicted_at: AwareDatetime
    accepted_at: AwareDatetime
    predicted_active_minutes: float
    observed_active_minutes: float | None
    interval_low: float | None = None
    interval_high: float | None = None
    split: Literal['development','held_out']


class CorrectionEvidence(Contract):
    correction_id: str
    employee_id: str
    original_version: str
    superseding_version: str | None
    disputed: bool
    original_snapshot_preserved: bool
    observed_event_ref: str


class ProductEvidence(Contract):
    schema_version: Literal['product-evidence-1'] = 'product-evidence-1'
    provenance: Literal['product_native','product_observation']
    interpretation: InterpretationEvidence = InterpretationEvidence()
    commitment: CommitmentEvidence | None = None
    actions: tuple[ExternalActionEvidence, ...] | None = None
    notifications: tuple[NotificationEvidence, ...] | None = None
    submissions: tuple[SubmissionEvidence, ...] | None = None
    reviews: tuple[ReviewEvidence, ...] | None = None
    workload: tuple[WorkloadEvidence, ...] | None = None
    estimates: tuple[EstimateEvidence, ...] | None = None
    corrections: tuple[CorrectionEvidence, ...] | None = None
    stage_ms: dict[str,float] | None = None
    objective_vector: tuple[float, ...] | None = None
    variables: int | None = None
    constraints: int | None = None
    required_recipients: tuple[str, ...] | None = None
    price_configuration: str | None = None
    attributable_cost: float | None = None
    currency: str | None = None
