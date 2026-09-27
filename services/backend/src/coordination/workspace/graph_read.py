"""Graph projections bind preview/check/approval to one exact candidate version."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from uuid import UUID, uuid5

from coordination.approval.persistence import read_review_status
from coordination.auth.models import CompanyContext
from coordination.planning.fixed_contracts import PlanProposalV2, rule_categories_for_family
from coordination.workspace.contracts import ProjectGraphData, RuleTechnicalDetail

if TYPE_CHECKING:
    from coordination.workspace.persistence import PostgresWorkspaceStore


def graph(
    store: PostgresWorkspaceStore,
    context: CompanyContext,
    project_id: UUID,
    *,
    proposal_id: UUID | None = None,
    plan_id: UUID | None = None,
) -> ProjectGraphData:
    historical_preview = proposal_id is not None
    exact_candidate_requested = proposal_id is not None or plan_id is not None
    # Reuse the authority already resolved for this request.
    manager = context.can_manage_planning
    if (proposal_id is not None or plan_id is not None) and not manager:
        from coordination.workspace.persistence import WorkspaceNotFoundError

        raise WorkspaceNotFoundError("candidate was not found")
    with store.transaction(context, "workspace:exact-graph") as connection:
        project = store.project(context, project_id, connection=connection)
        if plan_id is not None:
            # Resolve the exact requested plan within the current tenant/run and
            # project. Never quietly display a newer plan under an old review link.
            selected_plan = connection.execute(
                "select p.ai_proposal_id from app.plans p "
                "join app.planning_requests r on r.company_id=p.company_id "
                "and r.id=p.request_id where p.company_id=%s and p.id=%s "
                "and r.project_id=%s and p.demo_run_id is not distinct from %s",
                (context.company_id, plan_id, project_id, context.demo_run_id),
            ).fetchone()
            if (
                selected_plan is None
                or selected_plan["ai_proposal_id"] is None
                or (proposal_id is not None and proposal_id != selected_plan["ai_proposal_id"])
            ):
                from coordination.workspace.persistence import WorkspaceNotFoundError

                raise WorkspaceNotFoundError("the exact plan graph was not found")
            proposal_id = selected_plan["ai_proposal_id"]
        committed = connection.execute(
            """
            select w.task_id as id,coalesce(w.task_code,w.task_key) as task_key,
              w.title,coalesce(w.workstream_key,e.function_key,'engineering') as team,
              e.display_name as owner_name,r.employee_id as owner_employee_id,w.status,
              w.start_at,w.finish_at,app.task_reviewer_display_name(
                app.current_actor_id(),w.company_id,rp.id) as reviewer_name,
              coalesce(w.purpose,w.title) as summary,w.row_version,w.source_plan_id,
              r.employee_id=app.effective_employee_id(w.company_id,app.current_actor_id()) as
                is_mine,
              r.employee_id=app.effective_employee_id(w.company_id,app.current_actor_id())
                and w.status not in ('accepted','cancelled') as can_work
            from app.work_items w
            left join app.execution_resources r on r.company_id=w.company_id and
              r.id=w.owner_resource_id
            left join app.employee_profiles e on e.company_id=r.company_id and e.id=r.employee_id
            left join app.task_review_policies rp on rp.company_id=w.company_id and
              rp.task_id=w.task_id and rp.active
            where w.company_id=%s and w.project_id=%s order by w.display_order,w.task_key
            """,
            (context.company_id, project_id),
        ).fetchall()
        candidate = None
        history: list[dict[str, Any]] = []
        # Once a plan has been committed, the normal project graph is an
        # execution read model. Do not make that screen wait for every historic
        # proposal and verification-rule payload. Exact review links still load
        # their selected evidence, and uncommitted planning graphs keep the full
        # candidate history needed for approval.
        if manager and (not committed or exact_candidate_requested):
            history_rows = connection.execute(
                """
                select proposal.id as proposal_id,proposal.version,proposal.author_kind,
                  verification.product_status,coalesce(validation.passed,false)
                    as independent_validation_passed,
                  encode(proposal.candidate_digest,'hex') as candidate_digest,proposal.created_at
                from app.ai_plan_proposals proposal
                join app.planning_snapshots snapshot on snapshot.company_id=proposal.company_id
                  and snapshot.id=proposal.snapshot_id
                join app.planning_requests request on request.company_id=snapshot.company_id
                  and request.id=snapshot.request_id
                join app.plan_verification_runs verification on
                  verification.company_id=proposal.company_id
                  and verification.proposal_id=proposal.id
                left join app.plan_validation_runs validation on
                  validation.company_id=proposal.company_id and validation.proposal_id=proposal.id
                where proposal.company_id=%s and request.project_id=%s
                  and proposal.demo_run_id is not distinct from %s
                order by proposal.created_at desc,proposal.version desc,proposal.id desc limit 30
                """,
                (context.company_id, project_id, context.demo_run_id),
            ).fetchall()
            history = [dict(row) for row in history_rows]
            candidate = connection.execute(
                """
                select proposal.id,proposal.author_kind,proposal.candidate_payload,
                  proposal.candidate_digest,
                  plan.id as plan_id,verification.id as verification_id,verification.product_status,
                  verification.native_status,verification.z3_version,
                  verification.compiler_version,
                  coalesce(verification.diagnostics->'report'->>'verifier_version',
                    'unavailable') as verifier_version,
                  verification.duration_ms,
                  cardinality(verification.required_rule_ids) as required_rule_count,
                  cardinality(verification.covered_rule_ids) as covered_rule_count,
                  cardinality(verification.unverified_rule_ids) as unverified_rule_count,
                  encode(verification.post_candidate_digest,'hex') as verified_candidate_digest,
                  encode(verification.snapshot_digest,'hex') as verified_snapshot_digest,
                  coalesce(proposal.candidate_digest=verification.pre_candidate_digest
                    and proposal.candidate_digest=verification.post_candidate_digest
                    and proposal.candidate_digest=validation.candidate_digest
                    and snapshot.snapshot_digest=verification.snapshot_digest,false)
                    as digests_match,
                  validation.passed,validation.validator_version,proposal.snapshot_id,
                  commitment.id as commitment_id
                from app.ai_plan_proposals proposal
                join app.planning_snapshots snapshot on snapshot.company_id=proposal.company_id
                  and snapshot.id=proposal.snapshot_id
                join app.planning_requests request on request.company_id=snapshot.company_id and
                  request.id=snapshot.request_id
                left join app.plans plan on plan.company_id=proposal.company_id and
                  plan.ai_proposal_id=proposal.id
                left join app.plan_verification_runs verification on
                  verification.company_id=proposal.company_id
                  and verification.proposal_id=proposal.id
                left join app.plan_validation_runs validation on
                  validation.company_id=proposal.company_id and validation.proposal_id=proposal.id
                left join app.plan_commitments commitment on
                  commitment.company_id=plan.company_id and commitment.plan_id=plan.id
                where proposal.company_id=%s and request.project_id=%s
                  and (%s::uuid is null or proposal.id=%s)
                  and proposal.demo_run_id is not distinct from %s
                order by proposal.created_at desc,proposal.version desc,proposal.id desc limit 1
                """,
                (
                    context.company_id,
                    project_id,
                    proposal_id,
                    proposal_id,
                    context.demo_run_id,
                ),
            ).fetchone()
        if proposal_id is not None:
            if candidate is None:
                from coordination.workspace.persistence import WorkspaceNotFoundError

                raise WorkspaceNotFoundError("candidate was not found")
            committed = []  # Explicit historical preview; never replace executable work.
        nodes: list[dict[str, Any]] = []
        edges: list[dict[str, Any]] = []
        rules: list[dict[str, Any]] = []
        plan_id = project.plan_id
        check_status = "not_checked"
        can_approve = False
        reason: str | None = (
            "A complete candidate must pass verification and independent validation."
        )
        timezone = "America/Los_Angeles" if context.demo_run_id else "UTC"
        verification_summary: dict[str, Any] | None = None
        approval_status = "not_approved"
        # Committed work is authoritative. Drafts are previews and never executable rows.
        if committed:
            node_ids = {row["id"] for row in committed}
            nodes = [
                {key: value for key, value in row.items() if key != "source_plan_id"}
                for row in committed
            ]
            for node in nodes:
                node["is_mine"], node["can_work"] = bool(node["is_mine"]), bool(node["can_work"])
            edge_rows = connection.execute(
                """
                select id,predecessor_task_id as "from",successor_task_id as "to",edge_kind as
                  kind,required_state as label
                from app.task_dependency_edges where company_id=%s and project_id=%s order by id
                """,
                (context.company_id, project_id),
            ).fetchall()
            edges = [
                dict(row) for row in edge_rows if row["from"] in node_ids and row["to"] in node_ids
            ]
            # Do not label committed nodes with the evidence for a different uncommitted draft.
            committed_plan = connection.execute(
                """
                select c.plan_id from app.plan_commitments c
                join app.plans p on p.company_id=c.company_id and p.id=c.plan_id
                join app.planning_requests r on r.company_id=p.company_id and r.id=p.request_id
                where c.company_id=%s and r.project_id=%s order by c.committed_at desc,c.id desc
                  limit 1
                """,
                (context.company_id, project_id),
            ).fetchone()
            plan_id = committed_plan["plan_id"] if committed_plan else None
            if candidate is not None and candidate["plan_id"] != plan_id:
                candidate = None
            check_status, reason = (
                "committed",
                "This graph shows committed work; approval is already recorded.",
            )
            approval_status = "committed"
        elif candidate is not None:
            proposal = PlanProposalV2.model_validate(candidate["candidate_payload"]["proposal"])
            if proposal.candidate_digest != bytes(candidate["candidate_digest"]).hex():
                raise ValueError("candidate digest binding changed")
            timezone = proposal.draft.timezone
            people = connection.execute(
                """
                select r.id,r.employee_id,e.display_name,e.function_key
                from app.execution_resources r join app.employee_profiles e
                  on e.company_id=r.company_id and e.id=r.employee_id
                where r.company_id=%s and r.resource_kind='human' and r.status='active'
                """,
                (context.company_id,),
            ).fetchall()
            names = {row["id"]: row for row in people}
            for task in proposal.draft.tasks:
                owner = names.get(task.owner_resource_id, {})
                key = task.task_key.upper()
                # The authored story has explicit cross-function work: M2 belongs to Marketing,
                # although Iris's directory function is Design. Other projects use owner function.
                hub = {
                    "D": "design",
                    "E": "engineering",
                    "Q": "qa",
                    "M": "marketing",
                    "S": "support",
                    "L": "engineering",
                    "R": "goal",
                }.get(key[:1])
                team = (
                    (hub or "engineering")
                    if proposal.author_kind != "ai_authored"
                    else owner.get("function_key", "engineering")
                )
                nodes.append(
                    {
                        "id": task.task_id,
                        "task_key": key,
                        "title": task.title,
                        "team": team,
                        "owner_name": owner.get("display_name"),
                        "owner_employee_id": owner.get("employee_id"),
                        "status": "proposed",
                        "start_at": task.start,
                        "finish_at": task.end,
                        "reviewer_name": ", ".join(
                            str(names[value]["display_name"])
                            for value in task.reviewer_resource_ids
                            if value in names
                        )
                        or None,
                        "summary": task.purpose,
                        "is_mine": owner.get("employee_id") == context.effective_employee_id,
                        "can_work": False,
                        "row_version": task.expected_work_version or 0,
                    }
                )
            edges = [
                {
                    "id": uuid5(proposal.proposal_id, gate.rule_id),
                    "from": gate.predecessor_task_id,
                    "to": gate.successor_task_id,
                    "kind": "acceptance"
                    if gate.required_state in ("accepted", "approved")
                    else "dependency",
                    "label": gate.required_state.replace("_", " "),
                }
                for gate in proposal.draft.gates
            ]
            plan_id = candidate["plan_id"]
            check_status = candidate["product_status"] or "not_checked"
            reason = "Candidate has violations or could not be verified. Review its rule results."
            if check_status == "CHECKED" and not candidate["passed"]:
                reason = "Independent concrete validation has not passed for this exact candidate."
        if candidate is not None:
            records = connection.execute(
                """
                select result.id,result.rule_key,result.result,result.encoding_version,
                  result.safe_diagnostic,
                  result.fixed_values - 'technical_expression' as fixed_values,
                  (result.fixed_values ? 'technical_expression'
                    and jsonb_typeof(result.fixed_values->'technical_expression')='string')
                    as technical_expression_available,
                  constraint_row.payload,constraint_row.source_version_ids,source.title as
                    source_title,
                  version.provider_version
                from app.plan_verification_rule_results result
                left join app.validated_constraints constraint_row on
                  constraint_row.company_id=result.company_id
                  and constraint_row.id=result.constraint_id
                left join app.source_versions version on
                  version.company_id=constraint_row.company_id
                  and version.id=(constraint_row.source_version_ids->>0)::uuid
                left join app.source_records source on source.company_id=version.company_id and
                  source.id=version.source_id
                where result.company_id=%s and result.verification_run_id=%s order by
                  result.rule_key
                """,
                (context.company_id, candidate["verification_id"]),
            ).fetchall()
            formulas = {
                "resource_capacity": "active(person,slot) + busy(person,slot) <= capacity",
                "reservation": "active(person,slot) + protected(person,slot) <= capacity",
                "effort": "sum(active minutes) = admitted effort minutes",
                "eligibility": "proposed owner is in the admitted eligible domain",
                "working_window": "release <= start < finish <= window end",
                "execution_gate": "successor.start >= predecessor.decision_or_submission.end + lag",
                "active_participants": "participant active intervals = owner active intervals",
                "acceptance_review": "review.start >= submitted_work.end; independent reviewer",
                "deadline": "finish <= admitted hard deadline",
            }
            for row in records:
                payload = row["payload"] or {}
                fixed_values = row["fixed_values"] or {}
                category_keys, category_titles = rule_categories_for_family(
                    str(payload.get("family", ""))
                )
                stored_category_key = fixed_values.get("category_key")
                stored_category_title = fixed_values.get("category_title")
                stored_category_keys = fixed_values.get("category_keys")
                stored_category_titles = fixed_values.get("category_titles")
                candidate_values = fixed_values.get("candidate_values")
                rules.append(
                    {
                        "id": str(row["id"]),
                        "rule_id": row["rule_key"],
                        "title": row["rule_key"],
                        "status": row["result"],
                        "description": row["safe_diagnostic"]
                        or "Exact fixed candidate rule result.",
                        "category_key": stored_category_key or category_keys[0],
                        "category_title": stored_category_title or category_titles[0],
                        "category_keys": stored_category_keys or list(category_keys),
                        "category_titles": stored_category_titles or list(category_titles),
                        "encoding_version": row.get("encoding_version") or "unavailable",
                        "formula": formulas.get(str(payload.get("family", ""))),
                        "source_label": row["source_title"],
                        "source_version": row["provider_version"]
                        or (row["source_version_ids"][0] if row["source_version_ids"] else None),
                        "candidate_values": candidate_values
                        if isinstance(candidate_values, dict)
                        else {
                            "admitted_rule": payload,
                            "candidate_digest": fixed_values.get("candidate_digest"),
                            "snapshot_digest": fixed_values.get("snapshot_digest"),
                        },
                        "technical_expression_available": bool(
                            row.get("technical_expression_available")
                        ),
                    }
                )
            if (
                not committed
                and plan_id is not None
                and candidate["product_status"] == "CHECKED"
                and candidate["passed"]
            ):
                status = read_review_status(connection, context=context, plan_id=plan_id)
                can_approve = (
                    manager
                    and not historical_preview
                    and plan_id == project.plan_id
                    and status == "proposed"
                )
                approval_status = status
                reason = None if can_approve else f"This exact candidate is {status}."
            if historical_preview:
                can_approve = False
                approval_status = "historical_read_only"
                reason = (
                    "Recorded candidate preview is read-only. Return to current work to approve."
                )
        if candidate is not None and candidate["verification_id"] is not None:
            verification_summary = {
                "proposal_id": candidate["id"],
                "author_kind": candidate.get("author_kind") or "unavailable",
                "product_status": candidate.get("product_status") or "UNABLE_TO_VERIFY",
                "native_status": candidate.get("native_status") or "unknown",
                "z3_version": candidate.get("z3_version") or "unavailable",
                "compiler_version": candidate.get("compiler_version") or "unavailable",
                "verifier_version": candidate.get("verifier_version") or "unavailable",
                "duration_ms": candidate.get("duration_ms") or 0,
                "required_rule_count": candidate.get("required_rule_count") or 0,
                "covered_rule_count": candidate.get("covered_rule_count") or 0,
                "unverified_rule_count": candidate.get("unverified_rule_count") or 0,
                "candidate_digest": candidate.get("verified_candidate_digest")
                or bytes(candidate["candidate_digest"]).hex(),
                "snapshot_digest": candidate.get("verified_snapshot_digest") or "unavailable",
                "digests_match": bool(candidate.get("digests_match")),
                "independent_validation_passed": bool(candidate.get("passed")),
                "validator_version": candidate.get("validator_version"),
                "approval_status": approval_status,
            }
        elif not committed and plan_id is not None:
            legacy = connection.execute(
                "select author_kind from app.plans where company_id=%s and id=%s",
                (context.company_id, plan_id),
            ).fetchone()
            if legacy and legacy["author_kind"] == "legacy_solver":
                check_status, reason = (
                    "legacy_solver",
                    "Historical solver-authored plan; open its recorded legacy review.",
                )
        if not context.demo_run_id:
            company = connection.execute(
                "select default_timezone from app.companies where id=%s", (context.company_id,)
            ).fetchone()
            if company:
                timezone = company["default_timezone"]
        return ProjectGraphData.model_validate(
            {
                "project": project,
                "nodes": nodes,
                "edges": edges,
                "rules": rules,
                "plan_id": plan_id,
                "can_approve": can_approve,
                "check_status": check_status,
                "approval_disabled_reason": reason,
                "timezone": timezone,
                "candidate_history": history,
                "selected_proposal_id": candidate["id"] if candidate and not committed else None,
                "is_candidate_preview": bool(candidate is not None and not committed),
                "verification_summary": verification_summary,
            }
        )


def rule_detail(
    store: PostgresWorkspaceStore,
    context: CompanyContext,
    project_id: UUID,
    rule_result_id: UUID,
    *,
    proposal_id: UUID,
) -> RuleTechnicalDetail:
    """Read one persisted assertion through an exact manager/project/proposal binding."""
    if not context.can_manage_planning:
        from coordination.workspace.persistence import WorkspaceNotFoundError

        raise WorkspaceNotFoundError("rule result was not found")
    with store.transaction(context, "workspace:rule-detail") as connection:
        row = connection.execute(
            """
            select result.rule_key,result.encoding_version,result.fixed_values
            from app.plan_verification_rule_results result
            join app.plan_verification_runs verification
              on verification.company_id=result.company_id
             and verification.id=result.verification_run_id
            join app.ai_plan_proposals proposal
              on proposal.company_id=verification.company_id
             and proposal.id=verification.proposal_id
            join app.planning_snapshots snapshot
              on snapshot.company_id=proposal.company_id and snapshot.id=proposal.snapshot_id
            join app.planning_requests request
              on request.company_id=snapshot.company_id and request.id=snapshot.request_id
            where result.company_id=%s
              and result.demo_run_id is not distinct from %s
              and verification.demo_run_id is not distinct from %s
              and proposal.demo_run_id is not distinct from %s
              and snapshot.demo_run_id is not distinct from %s
              and request.demo_run_id is not distinct from %s
              and request.project_id=%s and proposal.id=%s and result.id=%s
            """,
            (
                context.company_id,
                context.demo_run_id,
                context.demo_run_id,
                context.demo_run_id,
                context.demo_run_id,
                context.demo_run_id,
                project_id,
                proposal_id,
                rule_result_id,
            ),
        ).fetchone()
        if row is None:
            from coordination.workspace.persistence import WorkspaceNotFoundError

            raise WorkspaceNotFoundError("rule result was not found")
        fixed_values = row["fixed_values"] or {}
        expression = fixed_values.get("technical_expression")
        return RuleTechnicalDetail(
            rule_id=row["rule_key"],
            technical_expression=expression if isinstance(expression, str) else None,
            encoding_version=row["encoding_version"],
        )
