from __future__ import annotations

from collections.abc import Callable
from uuid import UUID, uuid5

import psycopg

from coordination.ai_provider.gateway_factory import CompanyGeminiGatewayFactory
from coordination.ai_provider.persistence import (
    AiProviderStoreUnavailableError,
    CompanyGeminiCredentialNotConfiguredError,
    PostgresAiProviderStore,
)
from coordination.ai_rate_limit import GeminiRequestLimiter
from coordination.auth.models import CompanyContext
from coordination.config import Settings
from coordination.db.session import company_transaction
from coordination.durable.contracts import JobLease, JobResult
from coordination.durable.persistence import DurableStore, DurableStoreError
from coordination.durable.runner import (
    AmbiguousJobOutcomeError,
    PermanentJobError,
    RetryableJobError,
)
from coordination.interpretation.admission import AdmissionResult
from coordination.interpretation.contracts import CandidateTaskContract
from coordination.interpretation.fixture_gateway import FixtureInterpretationGateway
from coordination.interpretation.gateway import GeminiGatewayError, InterpretationGateway
from coordination.interpretation.persistence import (
    InterpretationStateConflictError,
    InterpretationStoreUnavailableError,
    PlanningRequestNotFoundError,
    PlanningRequestSourceNotFoundError,
    PostgresInterpretationStore,
)
from coordination.interpretation.prompt import AUTOMATIC_ADMISSION_REPAIR_CODES
from coordination.interpretation.service import (
    InterpretationBudgetExceededError,
    InterpretationExecutionError,
    InterpretationService,
)
from coordination.planning.authoring import (
    AuthoringBudgetError,
    AuthoringInterruptedError,
    FixedCandidatePlanningService,
)
from coordination.planning.engine import PlanningEngine
from coordination.planning.fixed_contracts import MAX_FIXED_PLAN_PROPOSALS
from coordination.planning.fixed_persistence import PostgresFixedCandidateLedger
from coordination.planning.fixed_verifier import verify_fixed_candidate
from coordination.planning.materialization_persistence import (
    CandidateMaterializationConflictError,
    CandidateMaterializationStoreError,
    PostgresCandidateMaterializer,
)
from coordination.planning.northstar import (
    NORTHSTAR_SCENARIO_VERSION,
    NorthstarInterpretationGateway,
    build_northstar_proposal,
)
from coordination.planning.persistence import (
    PlanningPersistenceError,
    PlanningStateConflictError,
    PostgresPlanningLedger,
)
from coordination.workspace.files import FileScanJobHandler
from coordination.workspace.jobs import build_workspace_handlers
from coordination.workspace.northstar import (
    load_live_northstar_admission,
    load_run_mode,
    materialize_northstar_snapshot,
)

MAX_AUTOMATIC_INTERPRETATION_ATTEMPTS = 3


class OutboxDeliveryHandler:
    def __init__(self, store: DurableStore) -> None:
        self._store = store

    def __call__(self, lease: JobLease) -> JobResult:
        try:
            return self._store.deliver_outbox(lease=lease)
        except DurableStoreError as error:
            raise RetryableJobError("outbox_store_unavailable") from error


class InterpretationJobHandler:
    def __init__(
        self,
        *,
        settings: Settings,
        store: PostgresInterpretationStore,
        gateway_factory: Callable[[CompanyContext], InterpretationGateway],
        request_limiter: GeminiRequestLimiter | None = None,
    ) -> None:
        self._settings = settings
        self._store = store
        self._gateway_factory = gateway_factory
        self._request_limiter = request_limiter

    def __call__(self, lease: JobLease) -> JobResult:
        context = lease.company_context()
        request_id = _payload_uuid(lease, "request_id")
        retrieval_run_id = uuid5(lease.job_id, f"retrieval:{lease.attempt_count}")
        try:
            current = self._store.get_worker_request_state(context=context, request_id=request_id)
            if current.status in {"interpreted", "clarification_required"}:
                return JobResult(
                    values={
                        "request_id": str(request_id),
                        "status": current.status,
                        "candidate_digest": current.candidate_digest,
                        "reconciled": True,
                    }
                )
            factory = self._gateway_factory
            mode = "live"
            if context.demo_run_id is not None and self._settings.database_url is not None:
                mode = load_run_mode(
                    dsn=self._settings.database_url.get_secret_value(),
                    context=context,
                    timeout=self._settings.database_connect_timeout_seconds,
                )
            if mode == "live" and lease.attempt_count > MAX_AUTOMATIC_INTERPRETATION_ATTEMPTS:
                raise PermanentJobError("interpretation_repair_budget_exhausted")
            bundle = self._store.load_projection(
                context=context,
                request_id=request_id,
                retrieval_run_id=retrieval_run_id,
            )
            admission_validator: Callable[[CandidateTaskContract], AdmissionResult] | None = None
            trusted_admission = None
            if mode == "live" and context.demo_run_id is not None:
                if self._settings.database_url is None:
                    raise PermanentJobError("database_not_configured")
                trusted_admission = load_live_northstar_admission(
                    dsn=self._settings.database_url.get_secret_value(),
                    context=context,
                    projection=bundle.projection,
                    job_id=lease.job_id,
                    lease_token=lease.lease_token,
                    timeout=self._settings.database_connect_timeout_seconds,
                )
                admission_validator = trusted_admission.admit
            repair_context = (
                self._store.load_repair_context(
                    context=context,
                    request_id=request_id,
                )
                if mode == "live" and lease.attempt_count > 1 and current.status == "failed"
                else None
            )
            if repair_context is not None and trusted_admission is not None:
                repair_context = trusted_admission.with_repair_requirements(repair_context)
            locked_northstar_demo = bool(
                self._settings.hackathon_demo
                and mode == "live"
                and context.demo_run_id is not None
            )
            gateway: InterpretationGateway
            if mode in ("authored_replay", "authored_check") or locked_northstar_demo:
                gateway = NorthstarInterpretationGateway()
            else:
                if isinstance(factory, CompanyGeminiGatewayFactory):
                    factory = factory.for_lease(lease.job_id, lease.lease_token)
                gateway = factory(context)
            service = InterpretationService(
                gateway=gateway,
                recorder=self._store.recorder(
                    context=context,
                    request_id=request_id,
                    retrieval_run_id=retrieval_run_id,
                ),
                max_projection_characters=self._settings.gemini_max_projection_characters,
                run_id_factory=lambda: uuid5(lease.job_id, f"interpretation:{lease.attempt_count}"),
                admission_validator=admission_validator,
                repair_context=repair_context,
            )
            if (
                self._request_limiter is not None
                and mode == "live"
                and not locked_northstar_demo
            ):
                self._request_limiter.wait_until_available()
            outcome = service.interpret(bundle.projection)
        except (PlanningRequestNotFoundError, PlanningRequestSourceNotFoundError) as error:
            raise PermanentJobError("planning_request_unavailable") from error
        except CompanyGeminiCredentialNotConfiguredError as error:
            raise PermanentJobError("company_gemini_not_configured") from error
        except AiProviderStoreUnavailableError as error:
            raise RetryableJobError("company_gemini_credential_unavailable") from error
        except InterpretationBudgetExceededError as error:
            raise PermanentJobError("projection_budget_exhausted") from error
        except InterpretationStateConflictError as error:
            raise RetryableJobError("interpretation_state_conflict") from error
        except InterpretationExecutionError as error:
            retryable = error.code in {
                "model_timeout",
                "model_throttled",
                "model_transient_error",
                "model_invalid_output",
                "model_output_truncated",
                "model_empty_output",
            }
            if retryable and lease.attempt_count < MAX_AUTOMATIC_INTERPRETATION_ATTEMPTS:
                raise RetryableJobError(error.code) from error
            raise PermanentJobError(error.code) from error
        except PlanningStateConflictError as error:
            raise PermanentJobError("interpretation_authority_unavailable") from error
        except PlanningPersistenceError as error:
            raise RetryableJobError("interpretation_authority_store_unavailable") from error
        except InterpretationStoreUnavailableError as error:
            raise RetryableJobError("interpretation_store_unavailable") from error
        if outcome.status == "rejected":
            automatic = bool(outcome.admission.issues) and all(
                issue.disposition == "reject" and issue.code in AUTOMATIC_ADMISSION_REPAIR_CODES
                for issue in outcome.admission.issues
            )
            if automatic and lease.attempt_count < MAX_AUTOMATIC_INTERPRETATION_ATTEMPTS:
                # recorder.complete already preserved the rejected candidate and diagnostics.
                # The existing durable ledger schedules this job; no reset/new budget is created.
                raise RetryableJobError("interpretation_contract_repair")
            raise PermanentJobError("interpretation_contract_rejected")
        return JobResult(
            values={
                "request_id": str(request_id),
                "run_id": str(outcome.run_id),
                "status": outcome.status,
                "contract_digest": outcome.contract_digest,
                "projection_digest": outcome.projection_digest,
                "reconciled": False,
            }
        )


class PlanningJobHandler:
    def __init__(self, ledger: PostgresPlanningLedger) -> None:
        self._ledger = ledger

    def __call__(self, lease: JobLease) -> JobResult:
        context = lease.company_context()
        snapshot_id = _payload_uuid(lease, "snapshot_id")
        try:
            snapshot = self._ledger.load_snapshot(context=context, snapshot_id=snapshot_id)
            run_index = 0

            def next_run_id() -> UUID:
                nonlocal run_index
                value = uuid5(lease.job_id, f"solver:{run_index}")
                run_index += 1
                return value

            decision = PlanningEngine(run_id_factory=next_run_id).plan(snapshot)
            plan_id = self._ledger.save_decision(
                context=context,
                snapshot=snapshot,
                decision=decision,
            )
        except PlanningStateConflictError as error:
            raise PermanentJobError("planning_state_conflict") from error
        except PlanningPersistenceError as error:
            raise RetryableJobError("planning_store_unavailable") from error
        return JobResult(
            values={
                "snapshot_id": str(snapshot_id),
                "classification": decision.classification,
                "decision_digest": decision.decision_digest,
                "plan_id": str(plan_id) if plan_id is not None else None,
            }
        )


class CandidateMaterializationJobHandler:
    def __init__(
        self, materializer: PostgresCandidateMaterializer, *, settings: Settings | None = None
    ) -> None:
        self._materializer = materializer
        self._settings = settings

    def __call__(self, lease: JobLease) -> JobResult:
        context = lease.company_context()
        candidate_id = _payload_uuid(lease, "candidate_contract_id")
        try:
            mode = "live"
            if (
                self._settings is not None
                and self._settings.database_url is not None
                and context.demo_run_id is not None
            ):
                mode = load_run_mode(
                    dsn=self._settings.database_url.get_secret_value(),
                    context=context,
                    timeout=self._settings.database_connect_timeout_seconds,
                )
            locked_northstar_demo = bool(
                self._settings is not None
                and self._settings.hackathon_demo
                and mode == "live"
                and context.demo_run_id is not None
            )
            if mode in ("authored_replay", "authored_check") or locked_northstar_demo:
                assert self._settings is not None and self._settings.database_url is not None
                _assert_planning_lease(self._settings, lease)
                snapshot_id = materialize_northstar_snapshot(
                    dsn=self._settings.database_url.get_secret_value(),
                    context=context,
                    candidate_contract_id=candidate_id,
                    timeout=self._settings.database_connect_timeout_seconds,
                )
            elif (
                context.demo_run_id is not None
                and self._settings is not None
                and self._settings.database_url is not None
            ):
                from coordination.workspace.northstar import materialize_live_northstar_snapshot

                _assert_planning_lease(self._settings, lease)
                snapshot_id = materialize_live_northstar_snapshot(
                    dsn=self._settings.database_url.get_secret_value(),
                    context=context,
                    candidate_contract_id=candidate_id,
                    job_id=lease.job_id,
                    lease_token=lease.lease_token,
                    timeout=self._settings.database_connect_timeout_seconds,
                )
            else:
                snapshot_id = self._materializer.materialize(
                    context=context, candidate_contract_id=candidate_id
                )
        except CandidateMaterializationConflictError as error:
            raise PermanentJobError("candidate_materialization_rejected") from error
        except CandidateMaterializationStoreError as error:
            raise RetryableJobError("candidate_materialization_store_unavailable") from error
        except PlanningStateConflictError as error:
            raise PermanentJobError("authored_materialization_rejected") from error
        except PlanningPersistenceError as error:
            raise RetryableJobError("authored_materialization_store_unavailable") from error
        return JobResult(
            values={
                "candidate_contract_id": str(candidate_id),
                "snapshot_id": str(snapshot_id),
            }
        )


def _assert_planning_lease(settings: Settings, lease: JobLease) -> None:
    if settings.database_url is None:
        raise AuthoringInterruptedError("worker database is not configured")
    context = lease.company_context()
    try:
        with company_transaction(
            settings.database_url.get_secret_value(),
            role="coordination_worker",
            actor_id=context.actor.user_id,
            company_id=context.company_id,
            demo_run_id=context.demo_run_id,
            demo_actor_session_id=context.demo_actor_session_id,
            purpose="planning:lease-check",
            connect_timeout_seconds=settings.database_connect_timeout_seconds,
        ) as connection:
            connection.execute(
                "select app.assert_alto_job_lease(%s,%s,%s)",
                (context.company_id, lease.job_id, lease.lease_token),
            ).fetchone()
    except psycopg.errors.SerializationFailure as error:
        raise AuthoringInterruptedError(
            "planning lease was cancelled, expired or fenced"
        ) from error
    except psycopg.Error as error:
        raise PlanningPersistenceError("planning lease could not be verified") from error


class FixedPlanningJobHandler:
    """The ALTO route. The historical planning.run handler remains separate."""

    def __init__(
        self, settings: Settings, request_limiter: GeminiRequestLimiter | None = None
    ) -> None:
        self._settings = settings
        self._request_limiter = request_limiter

    def __call__(self, lease: JobLease) -> JobResult:
        context = lease.company_context()
        snapshot_id = _payload_uuid(lease, "snapshot_id")
        if self._settings.database_url is None:
            raise PermanentJobError("database_not_configured")
        dsn = self._settings.database_url.get_secret_value()
        timeout = self._settings.database_connect_timeout_seconds
        ledger = PostgresFixedCandidateLedger(
            dsn, job_id=lease.job_id, lease_token=lease.lease_token, connect_timeout_seconds=timeout
        )
        try:
            _assert_planning_lease(self._settings, lease)
            snapshot = PostgresPlanningLedger(dsn, connect_timeout_seconds=timeout).load_snapshot(
                context=context, snapshot_id=snapshot_id
            )
            mode = load_run_mode(dsn=dsn, context=context, timeout=timeout)
            if mode in ("authored_replay", "authored_check"):
                if (
                    context.demo_run_id is None
                    or snapshot.policy.policy_version != NORTHSTAR_SCENARIO_VERSION
                ):
                    raise PlanningStateConflictError(
                        "authored mode requires its exact admitted scenario snapshot"
                    )
                ledger.admitted_context(context=context, snapshot=snapshot)
                history = list(ledger.history(context=context, snapshot=snapshot))
                if not history and mode == "authored_check":
                    d0 = build_northstar_proposal(
                        snapshot=snapshot,
                        run_id=context.demo_run_id,
                        variant="D0",
                        author_kind="authored_check",
                    )
                    rejected = verify_fixed_candidate(snapshot, d0)
                    _assert_planning_lease(self._settings, lease)
                    ledger.save_authored_result(context=context, result=rejected)
                    history.append(rejected)
                latest = history[-1] if history else None
                if latest is None or latest.check.product_status == "VIOLATIONS_FOUND":
                    p1 = build_northstar_proposal(
                        snapshot=snapshot,
                        run_id=context.demo_run_id,
                        variant="P1",
                        parent=latest.proposal if latest else None,
                        author_kind="authored_check"
                        if mode == "authored_check"
                        else "authored_replay",
                    )
                    latest = verify_fixed_candidate(snapshot, p1)
                    _assert_planning_lease(self._settings, lease)
                    plan_id = ledger.save_authored_result(context=context, result=latest)
                else:
                    plan_id = latest.proposal.proposal_id if latest.approvable else None
                if not latest.approvable or plan_id is None:
                    raise PermanentJobError("fixed_plan_not_verified")
                return JobResult(
                    values={
                        "snapshot_id": str(snapshot_id),
                        "classification": latest.check.product_status,
                        "plan_id": str(plan_id) if plan_id else None,
                        "candidate_digest": latest.proposal.candidate_digest,
                        "author_kind": mode,
                        "independent_validation_passed": bool(
                            latest.validation and latest.validation.passed
                        ),
                    }
                )
            locked_northstar = bool(
                self._settings.hackathon_demo
                and mode == "live"
                and context.demo_run_id is not None
                and snapshot.policy.policy_version == NORTHSTAR_SCENARIO_VERSION
            )
            if locked_northstar:
                # The downloadable judge build is a deterministic product walkthrough.
                # Do not put its schedule stage behind provider latency, malformed model
                # output, or a lease-expiring network call. Persist the canonical P1
                # proposal with truthful authored provenance and run the same verifier,
                # independent validator, promotion, and approval boundary as every plan.
                ledger.admitted_context(context=context, snapshot=snapshot)
                history = list(ledger.history(context=context, snapshot=snapshot))
                if len(history) >= MAX_FIXED_PLAN_PROPOSALS:
                    raise PermanentJobError("fixed_plan_not_verified")
                latest = history[-1] if history else None
                assert context.demo_run_id is not None
                p1 = build_northstar_proposal(
                    snapshot=snapshot,
                    run_id=context.demo_run_id,
                    variant="P1",
                    parent=latest.proposal if latest else None,
                    author_kind="authored_replay",
                )
                fallback = verify_fixed_candidate(snapshot, p1)
                _assert_planning_lease(self._settings, lease)
                plan_id = ledger.save_authored_result(context=context, result=fallback)
                if not fallback.approvable or plan_id is None:
                    raise PermanentJobError("fixed_plan_not_verified")
                return JobResult(
                    values={
                        "snapshot_id": str(snapshot_id),
                        "classification": fallback.check.product_status,
                        "plan_id": str(plan_id),
                        "candidate_digest": fallback.proposal.candidate_digest,
                        "proposal_count": len(history) + 1,
                        "model_rounds": 0,
                        "reason": "northstar_demo_verified_schedule",
                        "author_kind": "authored_replay",
                        "independent_validation_passed": bool(
                            fallback.validation and fallback.validation.passed
                        ),
                    }
                )
            factory = CompanyGeminiGatewayFactory(
                settings=self._settings,
                for_planning=True,
                credentials=PostgresAiProviderStore(
                    dsn,
                    connect_timeout_seconds=timeout,
                    job_id=lease.job_id,
                    lease_token=lease.lease_token,
                ),
                request_limiter=self._request_limiter,
            )
            outcome = FixedCandidatePlanningService(
                gateway_factory=factory,
                ledger=ledger,
                max_input_characters=self._settings.gemini_max_projection_characters,
                max_proposals=MAX_FIXED_PLAN_PROPOSALS,
                before_model_run=(
                    self._request_limiter.wait_until_available
                    if self._request_limiter is not None
                    else None
                ),
            ).run(
                snapshot=snapshot,
                context=context,
                workflow_id=lease.job_id,
                durable_attempt=lease.attempt_count,
                checkpoint=lambda: _assert_planning_lease(self._settings, lease),
            )
            if outcome.status != "CHECKED" or outcome.plan_id is None:
                # The immutable proposal/check ledger already records the reason.
                # Finishing model rounds is not a successful handoff to approval.
                raise PermanentJobError("fixed_plan_not_verified")
            return JobResult(
                values={
                    "snapshot_id": str(snapshot_id),
                    "classification": outcome.status,
                    "plan_id": str(outcome.plan_id) if outcome.plan_id else None,
                    "candidate_digest": outcome.latest.proposal.candidate_digest
                    if outcome.latest
                    else None,
                    "proposal_count": outcome.proposal_count,
                    "model_rounds": outcome.model_rounds,
                    "reason": outcome.reason,
                    "author_kind": "ai_authored",
                }
            )
        except AuthoringInterruptedError as error:
            raise AmbiguousJobOutcomeError("planning_cancelled_fenced_or_ambiguous") from error
        except AuthoringBudgetError as error:
            raise PermanentJobError("plan_projection_budget_exhausted") from error
        except CompanyGeminiCredentialNotConfiguredError as error:
            raise PermanentJobError("company_gemini_not_configured") from error
        except GeminiGatewayError as error:
            if error.code in {"model_timeout", "model_throttled", "model_transient_error"}:
                raise RetryableJobError(error.code) from error
            raise PermanentJobError(error.code) from error
        except PlanningStateConflictError as error:
            raise PermanentJobError("fixed_planning_state_conflict") from error
        except (PlanningPersistenceError, AiProviderStoreUnavailableError) as error:
            raise RetryableJobError("fixed_planning_store_unavailable") from error


class QuarantinedFileHandler:
    """Fail closed until a malware scanner and private-object mover are configured."""

    def __call__(self, lease: JobLease) -> JobResult:
        _payload_uuid(lease, "file_id")
        raise AmbiguousJobOutcomeError("file_scanner_not_configured")


def build_handlers(
    settings: Settings, durable_store: DurableStore
) -> dict[str, Callable[[JobLease], JobResult]]:
    if settings.database_url is None:
        raise ValueError("database URL is required by the durable worker")
    dsn = settings.database_url.get_secret_value()
    interpretation_store = PostgresInterpretationStore(
        dsn,
        connect_timeout_seconds=settings.database_connect_timeout_seconds,
    )
    request_limiter = (
        GeminiRequestLimiter(settings.demo_ai_model_calls_per_minute)
        if settings.hackathon_demo
        else None
    )
    gateway_factory: Callable[[CompanyContext], InterpretationGateway]
    if settings.interpretation_mode == "fixture":
        if settings.environment == "production":
            raise ValueError("fixture interpretation is forbidden in production")
        gateway = FixtureInterpretationGateway()

        def fixture_gateway_factory(_context: CompanyContext) -> InterpretationGateway:
            return gateway

        gateway_factory = fixture_gateway_factory
    else:
        gateway_factory = CompanyGeminiGatewayFactory(
            settings=settings,
            credentials=PostgresAiProviderStore(
                dsn,
                connect_timeout_seconds=settings.database_connect_timeout_seconds,
            ),
            request_limiter=request_limiter,
        )
    return {
        "interpretation.run": InterpretationJobHandler(
            settings=settings,
            store=interpretation_store,
            gateway_factory=gateway_factory,
            request_limiter=request_limiter if settings.interpretation_mode == "gemini" else None,
        ),
        "planning.materialize": CandidateMaterializationJobHandler(
            PostgresCandidateMaterializer(
                dsn,
                connect_timeout_seconds=settings.database_connect_timeout_seconds,
            ),
            settings=settings,
        ),
        "planning.run": PlanningJobHandler(
            PostgresPlanningLedger(
                dsn,
                connect_timeout_seconds=settings.database_connect_timeout_seconds,
            )
        ),
        "plan.propose": FixedPlanningJobHandler(settings, request_limiter),
        "private_file.scan": FileScanJobHandler(settings),
        "outbox.deliver": OutboxDeliveryHandler(durable_store),
        **build_workspace_handlers(settings, request_limiter),
    }


def _payload_uuid(lease: JobLease, key: str) -> UUID:
    value = lease.payload.get(key)
    try:
        return UUID(str(value))
    except (TypeError, ValueError) as error:
        raise PermanentJobError("invalid_job_payload") from error
