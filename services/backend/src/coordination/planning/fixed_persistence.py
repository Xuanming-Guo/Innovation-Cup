"""Least-privileged immutable fixed-candidate ledger; no provider call in a transaction."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any, cast
from uuid import UUID, uuid5

import psycopg
from psycopg.types.json import Jsonb

from coordination.auth.models import CompanyContext
from coordination.db.session import company_transaction
from coordination.interpretation.gateway import StructuredGatewayResponse
from coordination.planning.contracts import PlanningSnapshot, canonical_digest
from coordination.planning.fixed_contracts import (
    MAX_FIXED_PLAN_PROPOSALS,
    FixedCandidateResult,
    FixedCheckReport,
    FixedValidationReport,
    PlanProposalV2,
)
from coordination.planning.persistence import PlanningPersistenceError, PlanningStateConflictError


class PostgresFixedCandidateLedger:
    def __init__(
        self, dsn: str, *, job_id: UUID, lease_token: UUID, connect_timeout_seconds: int = 5
    ) -> None:
        self._dsn = dsn
        self._job_id = job_id
        self._lease_token = lease_token
        self._connect_timeout_seconds = connect_timeout_seconds

    @contextmanager
    def _transaction(self, context: CompanyContext, purpose: str) -> Iterator[Any]:
        with company_transaction(
            self._dsn,
            role="coordination_worker",
            actor_id=context.actor.user_id,
            company_id=context.company_id,
            demo_run_id=context.demo_run_id,
            demo_actor_session_id=context.demo_actor_session_id,
            purpose=purpose,
            connect_timeout_seconds=self._connect_timeout_seconds,
        ) as connection:
            connection.execute(
                "select set_config('app.job_id',%s,true), set_config('app.lease_token',%s,true)",
                (str(self._job_id), str(self._lease_token)),
            )
            yield connection

    def history(
        self, *, context: CompanyContext, snapshot: PlanningSnapshot
    ) -> tuple[FixedCandidateResult, ...]:
        try:
            with self._transaction(context, "planning.fixed.history") as connection:
                rows = connection.execute(
                    """
                    select proposal.candidate_payload, verification.diagnostics,
                           validation.validator_version, validation.passed,
                           validation.issues, validation.candidate_digest as validated_digest
                    from app.ai_plan_proposals proposal
                    join app.plan_verification_runs verification
                      on verification.company_id = proposal.company_id
                     and verification.proposal_id = proposal.id
                    left join app.plan_validation_runs validation
                      on validation.company_id = proposal.company_id
                     and validation.proposal_id = proposal.id
                    where proposal.company_id = %s and proposal.snapshot_id = %s
                      and proposal.demo_run_id is not distinct from %s
                    order by proposal.version
                    """,
                    (context.company_id, snapshot.snapshot_id, context.demo_run_id),
                ).fetchall()
        except psycopg.Error as error:
            raise PlanningPersistenceError("fixed planning history could not be loaded") from error
        values = []
        for row in rows:
            payload = row["candidate_payload"]
            proposal = PlanProposalV2.model_validate(payload["proposal"])
            validation = None
            if row["validator_version"] is not None:
                validation = FixedValidationReport(
                    validator_version=row["validator_version"],
                    candidate_digest=bytes(row["validated_digest"]).hex(),
                    snapshot_digest=snapshot.snapshot_digest,
                    passed=row["passed"],
                    issues=row["issues"],
                )
            values.append(
                FixedCandidateResult(
                    proposal=proposal,
                    check=FixedCheckReport.model_validate(row["diagnostics"]["report"]),
                    validation=validation,
                    placements=payload["placements"],
                    blocks=payload["blocks"],
                )
            )
        return tuple(values)

    def admitted_context(
        self, *, context: CompanyContext, snapshot: PlanningSnapshot
    ) -> dict[str, object]:
        try:
            with self._transaction(context, "planning.fixed.authorised-context") as connection:
                revision = connection.execute(
                    "select app.scope_planning_revision(%s,false) as revision",
                    (context.company_id,),
                ).fetchone()
                if revision is None or revision["revision"] != snapshot.base_company_revision:
                    raise PlanningStateConflictError(
                        "planning scope changed after the immutable snapshot"
                    )
                visibility = connection.execute(
                    """
                    select count(*) as expected,
                      count(source.id) filter (where source.status='active'
                        and source.authority_status='authoritative'
                        and source.current_version_id=selected.source_version_id
                        and app.can_read_source(app.current_actor_id(),
                          selected.company_id,selected.source_id)
                        and (version.expires_at is null or
                          version.expires_at>clock_timestamp())) as current
                    from app.planning_request_sources selected
                    left join app.source_records source
                      on source.company_id=selected.company_id and source.id=selected.source_id
                    left join app.source_versions version
                      on version.company_id=selected.company_id and
                        version.id=selected.source_version_id
                    where selected.company_id=%s and selected.request_id=%s
                    """,
                    (context.company_id, snapshot.request_id),
                ).fetchone()
                if visibility is None or visibility["expected"] != visibility["current"]:
                    raise PlanningStateConflictError(
                        "source access, freshness or authority changed before authoring"
                    )
                row = connection.execute(
                    """
                    select contract_json from app.candidate_contracts
                    where company_id=%s and id=%s and request_id=%s and admission_status='admitted'
                      and demo_run_id is not distinct from %s
                    """,
                    (
                        context.company_id,
                        snapshot.candidate_contract_id,
                        snapshot.request_id,
                        context.demo_run_id,
                    ),
                ).fetchone()
                if row is None:
                    raise PlanningStateConflictError(
                        "admitted task contract is no longer available"
                    )
                versions = connection.execute(
                    """
                    select task_id,row_version from app.work_items where company_id=%s
                    and demo_run_id is not distinct from %s and task_id=any(%s::uuid[])
                    """,
                    (
                        context.company_id,
                        context.demo_run_id,
                        [
                            rule.payload.task_id
                            for rule in snapshot.constraints
                            if rule.payload.family == "task_definition"
                        ],
                    ),
                ).fetchall()
                preferences = connection.execute(
                    """
                    select preference.id,preference.employee_id,preference.version,preference.text
                    from app.employee_preference_versions preference
                    where preference.company_id=%s and preference.status='confirmed'
                      and app.can_read_preference(preference.company_id,preference.id)
                    order by preference.employee_id,preference.version,preference.id limit 100
                    """,
                    (context.company_id,),
                ).fetchall()
                return {
                    **row["contract_json"],
                    "existing_task_versions": {
                        str(item["task_id"]): item["row_version"] for item in versions
                    },
                    "current_soft_preferences": [
                        {
                            "version_id": str(item["id"]),
                            "employee_id": str(item["employee_id"]),
                            "version": item["version"],
                            "text": item["text"],
                        }
                        for item in preferences
                    ],
                }
        except psycopg.Error as error:
            raise PlanningPersistenceError(
                "authorised planning context could not be loaded"
            ) from error

    def model_round_states(self, *, context: CompanyContext, workflow_id: UUID) -> dict[int, str]:
        ids = {
            uuid5(workflow_id, f"author:{round_index}:attempt:{attempt}"): (round_index, attempt)
            for round_index in range(1, MAX_FIXED_PLAN_PROPOSALS + 1)
            for attempt in range(1, 21)
        }
        try:
            with self._transaction(context, "planning.fixed.model-history") as connection:
                rows = connection.execute(
                    """
                    select run.id, run.status, run.error_code, proposal.id as proposal_id
                    from app.model_runs run
                    left join app.ai_plan_proposals proposal
                      on proposal.company_id = run.company_id and proposal.model_run_id = run.id
                    where run.company_id = %s and run.id = any(%s::uuid[])
                      and run.demo_run_id is not distinct from %s
                    """,
                    (context.company_id, list(ids), context.demo_run_id),
                ).fetchall()
        except psycopg.Error as error:
            raise PlanningPersistenceError("model attempt history could not be loaded") from error
        result: dict[int, str] = {}
        for row in sorted(rows, key=lambda item: ids[item["id"]]):
            round_index, _ = ids[row["id"]]
            state = row["status"]
            if state == "failed":
                state = row["error_code"] or "failed"
            elif state == "succeeded" and row["proposal_id"] is None:
                state = "succeeded_without_proposal"
            result[round_index] = state
        return result

    def begin_model_run(
        self,
        *,
        context: CompanyContext,
        snapshot: PlanningSnapshot,
        model_run_id: UUID,
        parent_run_id: UUID | None,
        operation: str,
        model: str,
        configuration: dict[str, object],
        input_digest: str,
    ) -> None:
        prompt_version = configuration.get("prompt_version", operation)
        if not isinstance(prompt_version, str) or not prompt_version:
            raise ValueError("model checkpoint requires a non-empty prompt version")
        try:
            with self._transaction(context, "planning.fixed.model-start") as connection:
                connection.execute(
                    """
                    insert into app.model_runs (
                        id, company_id, demo_run_id, stage, request_id, parent_run_id,
                        model, prompt_version, schema_version, config_digest, input_digest,
                        source_projection_digest, status, started_at
                    ) values (%s,%s,%s,%s,%s,%s,%s,%s,'plan-proposal.v2',%s,%s,%s,'running',now())
                    """,
                    (
                        model_run_id,
                        context.company_id,
                        context.demo_run_id,
                        "plan.revise" if operation == "plan.revise.v1" else "plan.propose",
                        snapshot.request_id,
                        parent_run_id,
                        model,
                        prompt_version,
                        bytes.fromhex(canonical_digest(configuration)),
                        bytes.fromhex(input_digest),
                        bytes.fromhex(snapshot.source_manifest_digest),
                    ),
                )
        except psycopg.errors.UniqueViolation as error:
            raise PlanningStateConflictError(
                "model attempt already started; do not repeat an ambiguous call"
            ) from error
        except psycopg.Error as error:
            raise PlanningPersistenceError("model attempt could not be checkpointed") from error

    def fail_model_run(self, *, context: CompanyContext, model_run_id: UUID, code: str) -> None:
        try:
            with self._transaction(context, "planning.fixed.model-failure") as connection:
                row = connection.execute(
                    """
                    update app.model_runs set status='failed', error_code=%s, completed_at=now()
                    where company_id=%s and id=%s and status='running'
                      and demo_run_id is not distinct from %s returning id
                    """,
                    (code, context.company_id, model_run_id, context.demo_run_id),
                ).fetchone()
                if row is None:
                    raise PlanningStateConflictError("model attempt is not current")
        except psycopg.Error as error:
            raise PlanningPersistenceError("model failure could not be checkpointed") from error

    def save_result(
        self,
        *,
        context: CompanyContext,
        result: FixedCandidateResult,
        model_run_id: UUID | None,
        response: StructuredGatewayResponse | None,
    ) -> UUID | None:
        proposal, check = result.proposal, result.check
        if proposal.company_id != context.company_id or proposal.demo_run_id != context.demo_run_id:
            raise PlanningStateConflictError(
                "candidate scope does not match its current worker scope"
            )
        if (proposal.author_kind == "ai_authored") != (
            model_run_id is not None and response is not None
        ):
            raise PlanningStateConflictError("live and authored provenance must not be conflated")
        verification_id = uuid5(proposal.proposal_id, "fixed-verification.v1")
        validation_id = uuid5(proposal.proposal_id, "independent-validation.v1")
        payload = {
            "schema_version": "plan-proposal.v2",
            "proposal": proposal.model_dump(mode="json"),
            "placements": [item.model_dump(mode="json") for item in result.placements],
            "blocks": [item.model_dump(mode="json") for item in result.blocks],
        }
        try:
            with self._transaction(context, "planning.fixed.result") as connection:
                connection.execute(
                    """
                    insert into app.ai_plan_proposals (
                        id,company_id,demo_run_id,snapshot_id,parent_proposal_id,version,
                        candidate_payload,candidate_digest,model_run_id,author_kind
                    ) values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                    """,
                    (
                        proposal.proposal_id,
                        context.company_id,
                        context.demo_run_id,
                        proposal.snapshot_id,
                        proposal.parent_proposal_id,
                        proposal.version,
                        Jsonb(payload),
                        bytes.fromhex(proposal.candidate_digest),
                        model_run_id,
                        proposal.author_kind,
                    ),
                )
                connection.execute(
                    """
                    insert into app.plan_verification_runs (
                        id,company_id,demo_run_id,proposal_id,snapshot_digest,
                        pre_candidate_digest,post_candidate_digest,compiler_version,
                        product_status,native_status,required_rule_ids,covered_rule_ids,
                        unverified_rule_ids,diagnostics,duration_ms,
                        timeout_ms,resource_limit,z3_version
                    ) values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                    """,
                    (
                        verification_id,
                        context.company_id,
                        context.demo_run_id,
                        proposal.proposal_id,
                        bytes.fromhex(check.snapshot_digest),
                        bytes.fromhex(check.candidate_digest_before),
                        bytes.fromhex(check.candidate_digest_after),
                        check.compiler_version,
                        check.product_status,
                        check.native_status,
                        list(check.required_rule_ids),
                        list(check.covered_rule_ids),
                        list(check.unverified_required_rule_ids),
                        Jsonb(
                            {
                                "report": check.model_dump(mode="json"),
                                "issues": [
                                    item.model_dump(mode="json") for item in check.diagnostics
                                ],
                            }
                        ),
                        check.duration_ms,
                        check.timeout_ms,
                        check.resource_limit,
                        check.solver_version,
                    ),
                )
                for rule in check.rule_results:
                    connection.execute(
                        """
                        insert into app.plan_verification_rule_results (
                          id,company_id,demo_run_id,verification_run_id,rule_key,constraint_id,
                          encoding_version,fixed_values,result,safe_diagnostic
                        ) select %s,%s,%s,%s,%s,constraint_row.id,%s,%s,%s,%s
                          from app.planning_snapshot_constraints selected
                          join app.validated_constraints constraint_row
                            on constraint_row.company_id=selected.company_id
                           and constraint_row.id=selected.constraint_id
                          where selected.company_id=%s and selected.snapshot_id=%s
                            and constraint_row.constraint_key=%s
                        """,
                        (
                            uuid5(verification_id, rule.rule_id),
                            context.company_id,
                            context.demo_run_id,
                            verification_id,
                            rule.rule_id,
                            check.compiler_version,
                            Jsonb(
                                {
                                    "candidate_digest": proposal.candidate_digest,
                                    "snapshot_digest": check.snapshot_digest,
                                    "category_key": rule.category_key,
                                    "category_title": rule.category_title,
                                    "category_keys": list(rule.category_keys),
                                    "category_titles": list(rule.category_titles),
                                    "candidate_values": rule.candidate_values,
                                    "technical_expression": rule.technical_expression,
                                }
                            ),
                            rule.result,
                            "Fixed submitted values checked against the exact admitted rule.",
                            context.company_id,
                            proposal.snapshot_id,
                            rule.rule_id,
                        ),
                    )
                if result.validation is not None:
                    validation = result.validation
                    connection.execute(
                        """
                        insert into app.plan_validation_runs (
                            id,company_id,demo_run_id,proposal_id,candidate_digest,
                            passed,issues,validator_version
                        ) values (%s,%s,%s,%s,%s,%s,%s,%s)
                        """,
                        (
                            validation_id,
                            context.company_id,
                            context.demo_run_id,
                            proposal.proposal_id,
                            bytes.fromhex(validation.candidate_digest),
                            validation.passed,
                            Jsonb([item.model_dump(mode="json") for item in validation.issues]),
                            validation.validator_version,
                        ),
                    )
                if model_run_id is not None and response is not None:
                    updated = connection.execute(
                        """
                        update app.model_runs set status='succeeded', completed_at=now(),
                          output_digest=%s, usage=%s
                        where company_id=%s and id=%s and status='running'
                          and demo_run_id is not distinct from %s returning id
                        """,
                        (
                            bytes.fromhex(proposal.candidate_digest),
                            Jsonb(
                                {
                                    **response.usage.model_dump(mode="json"),
                                    "sdk_version": response.sdk_version,
                                    "model_version": response.model_version,
                                    "provider_response_id": response.provider_response_id,
                                    "finish_reason": response.finish_reason,
                                }
                            ),
                            context.company_id,
                            model_run_id,
                            context.demo_run_id,
                        ),
                    ).fetchone()
                    if updated is None:
                        raise PlanningStateConflictError(
                            "model attempt is not current; result was not committed"
                        )
                if not result.approvable:
                    return None
                row = connection.execute(
                    "select app.promote_verified_ai_proposal(%s,%s,%s,%s) as plan_id",
                    (context.company_id, proposal.proposal_id, verification_id, validation_id),
                ).fetchone()
                if row is None or row["plan_id"] is None:
                    raise PlanningStateConflictError("checked candidate could not be promoted")
                self._write_task_briefs(connection, context, result, row["plan_id"])
                return cast(UUID, row["plan_id"])
        except psycopg.errors.UniqueViolation as error:
            raise PlanningStateConflictError("candidate version already exists") from error
        except psycopg.Error as error:
            raise PlanningPersistenceError("fixed candidate could not be persisted") from error

    def save_authored_result(
        self, *, context: CompanyContext, result: FixedCandidateResult
    ) -> UUID | None:
        if result.proposal.author_kind == "ai_authored":
            raise PlanningStateConflictError("authored replay cannot be attributed to AI")
        return self.save_result(context=context, result=result, model_run_id=None, response=None)

    @staticmethod
    def _write_task_briefs(
        connection: Any, context: CompanyContext, result: FixedCandidateResult, plan_id: UUID
    ) -> None:
        """Build each recipient projection before rendering, never a shared full-plan blob."""
        if not result.approvable:
            raise PlanningStateConflictError("briefs require both exact candidate checks")
        for version, task in enumerate(
            sorted(result.proposal.draft.tasks, key=lambda item: item.task_key), start=1
        ):
            audience_resources = {
                *task.reviewer_resource_ids,
                *(
                    block.resource_id
                    for block in task.blocks
                    if block.role in ("owner", "participant")
                ),
            }
            if task.owner_resource_id is not None:
                audience_resources.add(task.owner_resource_id)
            people = connection.execute(
                """
                select id,employee_id from app.execution_resources
                where company_id=%s and id=any(%s::uuid[]) and resource_kind='human'
                  and employee_id is not null and status='active'
                """,
                (context.company_id, list(audience_resources)),
            ).fetchall()
            if {row["id"] for row in people} != audience_resources:
                raise PlanningStateConflictError(
                    "a brief recipient is no longer an active authorised resource"
                )
            restricted = task.confidentiality == "restricted"
            body = {
                "schema_version": "employee-brief.v2",
                "task_id": str(task.task_id),
                "task_version": 1,
                "candidate_digest": result.proposal.candidate_digest,
                "summary": (
                    "Follow this exact approved assignment; submit its versioned "
                    "evidence for the required review."
                ),
                "tasks": [
                    {
                        "task_id": str(task.task_id),
                        "task_key": task.task_key,
                        "title": "Restricted assignment" if restricted else task.title,
                        "purpose": "Ask the manager for separately approved instructions."
                        if restricted
                        else task.purpose,
                        "deliverable": "Restricted details are withheld from this brief."
                        if restricted
                        else task.deliverable,
                        "acceptance_criteria": [] if restricted else list(task.acceptance_criteria),
                        "start_at": task.start.isoformat(),
                        "finish_at": task.end.isoformat(),
                        "review_policy": task.review_policy,
                        "reviewer_resource_ids": [
                            str(value) for value in task.reviewer_resource_ids
                        ],
                        "next_action": (
                            "Acknowledge the assignment; execution remains blocked "
                            "until its exact artifact gates pass."
                        ),
                    }
                ],
                "restricted_details_withheld": restricted,
            }
            audience = {
                "employee_ids": sorted(str(row["employee_id"]) for row in people),
                "team_ids": [],
                "task_ids": [str(task.task_id)],
            }
            digest = canonical_digest({"brief_payload": body, "audience_scope": audience})
            connection.execute(
                """
                insert into app.employee_brief_versions(id,company_id,demo_run_id,plan_id,version,
                  brief_payload,audience_scope,brief_digest) values(%s,%s,%s,%s,%s,%s,%s,%s)
                """,
                (
                    uuid5(plan_id, f"task-brief:{task.task_id}:v1"),
                    context.company_id,
                    context.demo_run_id,
                    plan_id,
                    version,
                    Jsonb(body),
                    Jsonb(audience),
                    bytes.fromhex(digest),
                ),
            )
