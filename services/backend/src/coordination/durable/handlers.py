from __future__ import annotations

from collections.abc import Callable
from uuid import UUID, uuid5

from coordination.ai_provider.gateway_factory import CompanyGeminiGatewayFactory
from coordination.ai_provider.persistence import (
    AiProviderStoreUnavailableError,
    CompanyGeminiCredentialNotConfiguredError,
    PostgresAiProviderStore,
)
from coordination.auth.models import CompanyContext
from coordination.config import Settings
from coordination.durable.contracts import JobLease, JobResult
from coordination.durable.persistence import DurableStore, DurableStoreError
from coordination.durable.runner import (
    AmbiguousJobOutcomeError,
    PermanentJobError,
    RetryableJobError,
)
from coordination.interpretation.fixture_gateway import FixtureInterpretationGateway
from coordination.interpretation.gateway import InterpretationGateway
from coordination.interpretation.persistence import (
    InterpretationStateConflictError,
    InterpretationStoreUnavailableError,
    PlanningRequestNotFoundError,
    PlanningRequestSourceNotFoundError,
    PostgresInterpretationStore,
)
from coordination.interpretation.service import (
    InterpretationBudgetExceededError,
    InterpretationExecutionError,
    InterpretationService,
)
from coordination.planning.engine import PlanningEngine
from coordination.planning.materialization_persistence import (
    CandidateMaterializationConflictError,
    CandidateMaterializationStoreError,
    PostgresCandidateMaterializer,
)
from coordination.planning.persistence import (
    PlanningPersistenceError,
    PlanningStateConflictError,
    PostgresPlanningLedger,
)


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
    ) -> None:
        self._settings = settings
        self._store = store
        self._gateway_factory = gateway_factory

    def __call__(self, lease: JobLease) -> JobResult:
        context = lease.company_context()
        request_id = _payload_uuid(lease, "request_id")
        retrieval_run_id = uuid5(lease.job_id, f"retrieval:{lease.attempt_count}")
        try:
            current = self._store.get_worker_request_state(
                context=context, request_id=request_id
            )
            if current.status in {"interpreted", "clarification_required"}:
                return JobResult(
                    values={
                        "request_id": str(request_id),
                        "status": current.status,
                        "candidate_digest": current.candidate_digest,
                        "reconciled": True,
                    }
                )
            gateway = self._gateway_factory(context)
            bundle = self._store.load_projection(
                context=context,
                request_id=request_id,
                retrieval_run_id=retrieval_run_id,
            )
            service = InterpretationService(
                gateway=gateway,
                recorder=self._store.recorder(
                    context=context,
                    request_id=request_id,
                    retrieval_run_id=retrieval_run_id,
                ),
                max_projection_characters=self._settings.gemini_max_projection_characters,
                run_id_factory=lambda: uuid5(
                    lease.job_id, f"interpretation:{lease.attempt_count}"
                ),
            )
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
            }
            if retryable:
                raise RetryableJobError(error.code) from error
            raise PermanentJobError(error.code) from error
        except InterpretationStoreUnavailableError as error:
            raise RetryableJobError("interpretation_store_unavailable") from error
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
    def __init__(self, materializer: PostgresCandidateMaterializer) -> None:
        self._materializer = materializer

    def __call__(self, lease: JobLease) -> JobResult:
        context = lease.company_context()
        candidate_id = _payload_uuid(lease, "candidate_contract_id")
        try:
            snapshot_id = self._materializer.materialize(
                context=context, candidate_contract_id=candidate_id
            )
        except CandidateMaterializationConflictError as error:
            raise PermanentJobError("candidate_materialization_rejected") from error
        except CandidateMaterializationStoreError as error:
            raise RetryableJobError("candidate_materialization_store_unavailable") from error
        return JobResult(
            values={
                "candidate_contract_id": str(candidate_id),
                "snapshot_id": str(snapshot_id),
            }
        )


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
        )
    return {
        "interpretation.run": InterpretationJobHandler(
            settings=settings,
            store=interpretation_store,
            gateway_factory=gateway_factory,
        ),
        "planning.materialize": CandidateMaterializationJobHandler(
            PostgresCandidateMaterializer(
                dsn,
                connect_timeout_seconds=settings.database_connect_timeout_seconds,
            )
        ),
        "planning.run": PlanningJobHandler(
            PostgresPlanningLedger(
                dsn,
                connect_timeout_seconds=settings.database_connect_timeout_seconds,
            )
        ),
        "private_file.scan": QuarantinedFileHandler(),
        "outbox.deliver": OutboxDeliveryHandler(durable_store),
    }


def _payload_uuid(lease: JobLease, key: str) -> UUID:
    value = lease.payload.get(key)
    try:
        return UUID(str(value))
    except (TypeError, ValueError) as error:
        raise PermanentJobError("invalid_job_payload") from error
