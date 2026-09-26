from __future__ import annotations

from time import perf_counter
from typing import Literal
from uuid import uuid4

import z3  # type: ignore[import-untyped]

from coordination.planning.compiler import (
    compile_snapshot,
    diagnose_unsat,
    extract_schedule,
    objective_values,
    optimization_is_proven,
)
from coordination.planning.contracts import (
    PlanningDecision,
    PlanningScope,
    PlanningSnapshot,
    ResultClassification,
    SolverAttempt,
    ValidationReport,
    canonical_digest,
)
from coordination.planning.normalizer import (
    NormalizedPlanningModel,
    PlanningInputError,
    normalize_snapshot,
)
from coordination.planning.validator import VALIDATOR_VERSION, validate_schedule


def classify_unknown_termination(
    reason: str,
) -> Literal["timeout", "resource_limit", "unknown"]:
    normalized_reason = reason.lower()
    if "timeout" in normalized_reason or "canceled" in normalized_reason:
        return "timeout"
    if "resource" in normalized_reason or "rlimit" in normalized_reason:
        return "resource_limit"
    return "unknown"


class PlanningEngine:
    """Compile, solve and independently validate one immutable planning snapshot."""

    def plan(self, snapshot: PlanningSnapshot) -> PlanningDecision:
        try:
            normalized = normalize_snapshot(snapshot)
        except PlanningInputError as error:
            empty_digest = canonical_digest(
                {
                    "snapshot_digest": snapshot.snapshot_digest,
                    "scope": "pinned_insertion",
                    "placements": [],
                    "blocks": [],
                }
            )
            attempt = SolverAttempt(
                run_id=uuid4(),
                scope="pinned_insertion",
                classification="INVALID_INPUT",
                raw_status="invalid",
                termination="invalid",
                reason_unknown=None,
                snapshot_digest=snapshot.snapshot_digest,
                model=None,
                solver_version=z3.get_version_string(),
                runtime_ms=0,
                timeout_ms=snapshot.policy.timeout_ms,
                resource_limit=snapshot.policy.resource_limit,
                objectives=(),
                placements=(),
                blocks=(),
                diagnostic_constraint_ids=tuple(
                    sorted(
                        {
                            constraint_id
                            for issue in error.issues
                            for constraint_id in issue.constraint_ids
                        }
                    )
                ),
                validation=ValidationReport(
                    validator_version=VALIDATOR_VERSION,
                    valid=False,
                    schedule_digest=empty_digest,
                    issues=error.issues,
                ),
            )
            return PlanningDecision.record(
                snapshot_digest=snapshot.snapshot_digest,
                classification="INVALID_INPUT",
                selected_attempt=None,
                attempts=(attempt,),
            )

        attempts = [self._solve(normalized, scope="pinned_insertion")]
        first = attempts[0]
        repair_is_meaningful = any(
            task.movement == "authorized" for task in normalized.tasks.values()
        )
        if (
            first.classification == "INFEASIBLE_WITHIN_SCOPE"
            and snapshot.policy.allow_authorized_repair
            and snapshot.policy.max_repair_attempts > 0
            and repair_is_meaningful
        ):
            attempts.append(self._solve(normalized, scope="authorized_repair"))

        selected_attempt = next(
            (
                index
                for index, attempt in enumerate(attempts)
                if attempt.classification in ("OPTIMAL_WITHIN_MODEL", "FEASIBLE")
                and attempt.validation is not None
                and attempt.validation.valid
            ),
            None,
        )
        final = attempts[selected_attempt] if selected_attempt is not None else attempts[-1]
        return PlanningDecision.record(
            snapshot_digest=snapshot.snapshot_digest,
            classification=final.classification,
            selected_attempt=selected_attempt,
            attempts=tuple(attempts),
        )

    def _solve(self, normalized: NormalizedPlanningModel, *, scope: PlanningScope) -> SolverAttempt:
        problem = compile_snapshot(normalized, scope=scope)
        started = perf_counter()
        try:
            status = problem.optimizer.check()
        except z3.Z3Exception as error:
            runtime_ms = max(0, round((perf_counter() - started) * 1000))
            return SolverAttempt(
                run_id=uuid4(),
                scope=scope,
                classification="UNKNOWN_OR_TIMEOUT",
                raw_status="unknown",
                termination="unknown",
                reason_unknown=str(error)[:500],
                snapshot_digest=normalized.snapshot.snapshot_digest,
                model=problem.metadata,
                solver_version=z3.get_version_string(),
                runtime_ms=runtime_ms,
                timeout_ms=normalized.snapshot.policy.timeout_ms,
                resource_limit=normalized.snapshot.policy.resource_limit,
                objectives=(),
                placements=(),
                blocks=(),
                diagnostic_constraint_ids=(),
                validation=None,
            )
        runtime_ms = max(0, round((perf_counter() - started) * 1000))

        if status == z3.unsat:
            return SolverAttempt(
                run_id=uuid4(),
                scope=scope,
                classification="INFEASIBLE_WITHIN_SCOPE",
                raw_status="unsat",
                termination="completed",
                reason_unknown=None,
                snapshot_digest=normalized.snapshot.snapshot_digest,
                model=problem.metadata,
                solver_version=z3.get_version_string(),
                runtime_ms=runtime_ms,
                timeout_ms=normalized.snapshot.policy.timeout_ms,
                resource_limit=normalized.snapshot.policy.resource_limit,
                objectives=(),
                placements=(),
                blocks=(),
                diagnostic_constraint_ids=diagnose_unsat(problem),
                validation=None,
            )
        if status == z3.unknown:
            reason_unknown = problem.optimizer.reason_unknown()[:500]
            termination = classify_unknown_termination(reason_unknown)
            return SolverAttempt(
                run_id=uuid4(),
                scope=scope,
                classification="UNKNOWN_OR_TIMEOUT",
                raw_status="unknown",
                termination=termination,
                reason_unknown=reason_unknown,
                snapshot_digest=normalized.snapshot.snapshot_digest,
                model=problem.metadata,
                solver_version=z3.get_version_string(),
                runtime_ms=runtime_ms,
                timeout_ms=normalized.snapshot.policy.timeout_ms,
                resource_limit=normalized.snapshot.policy.resource_limit,
                objectives=(),
                placements=(),
                blocks=(),
                diagnostic_constraint_ids=(),
                validation=None,
            )

        model = problem.optimizer.model()
        placements, blocks = extract_schedule(problem, model)
        validation = validate_schedule(
            normalized,
            scope=scope,
            placements=placements,
            blocks=blocks,
        )
        classification: ResultClassification
        if not validation.valid:
            classification = "INVALID_INPUT"
        elif optimization_is_proven(problem):
            classification = "OPTIMAL_WITHIN_MODEL"
        else:
            classification = "FEASIBLE"
        return SolverAttempt(
            run_id=uuid4(),
            scope=scope,
            classification=classification,
            raw_status="sat",
            termination="completed",
            reason_unknown=None,
            snapshot_digest=normalized.snapshot.snapshot_digest,
            model=problem.metadata,
            solver_version=z3.get_version_string(),
            runtime_ms=runtime_ms,
            timeout_ms=normalized.snapshot.policy.timeout_ms,
            resource_limit=normalized.snapshot.policy.resource_limit,
            objectives=objective_values(problem, model),
            placements=placements,
            blocks=blocks,
            diagnostic_constraint_ids=(),
            validation=validation,
        )
