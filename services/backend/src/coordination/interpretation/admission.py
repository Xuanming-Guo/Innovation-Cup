from __future__ import annotations

import hashlib
import re
from collections import defaultdict
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict

from coordination.interpretation.contracts import (
    AssumptionBasis,
    CandidateBasis,
    CandidateClarification,
    CandidateTaskContract,
    ClarificationBasis,
    EvidenceBasis,
)
from coordination.interpretation.projection import InterpretationProjection


class AdmissionIssue(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    code: str
    path: str
    message: str
    disposition: Literal["reject", "clarify"]


class AdmissionResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    status: Literal["admitted", "clarification_required", "rejected"]
    issues: tuple[AdmissionIssue, ...]


def _all_bases(contract: CandidateTaskContract) -> list[tuple[str, CandidateBasis]]:
    values: list[tuple[str, CandidateBasis]] = []
    for task_index, task in enumerate(contract.tasks):
        values.extend((f"tasks[{task_index}].bases", basis) for basis in task.bases)
        values.extend(
            (f"tasks[{task_index}].estimate.bases", basis) for basis in task.estimate.bases
        )
        if task.deadline is not None:
            values.extend(
                (f"tasks[{task_index}].deadline.bases", basis) for basis in task.deadline.bases
            )
        for requirement_index, requirement in enumerate(task.requirements):
            values.extend(
                (f"tasks[{task_index}].requirements[{requirement_index}].bases", basis)
                for basis in requirement.bases
            )
    for dependency_index, dependency in enumerate(contract.dependencies):
        values.extend(
            (f"dependencies[{dependency_index}].bases", basis) for basis in dependency.bases
        )
    return values


def _cycle_exists(graph: dict[str, set[str]]) -> bool:
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(node: str) -> bool:
        if node in visiting:
            return True
        if node in visited:
            return False
        visiting.add(node)
        for successor in graph.get(node, set()):
            if visit(successor):
                return True
        visiting.remove(node)
        visited.add(node)
        return False

    return any(visit(node) for node in graph)


def admit_candidate(
    contract: CandidateTaskContract,
    projection: InterpretationProjection,
    *,
    now: datetime,
) -> AdmissionResult:
    issues: list[AdmissionIssue] = []

    def issue(
        code: str, path: str, message: str, disposition: Literal["reject", "clarify"]
    ) -> None:
        issues.append(
            AdmissionIssue(code=code, path=path, message=message, disposition=disposition)
        )

    if contract.company_id != projection.company_id:
        issue("tenant_mismatch", "company_id", "candidate company is not permitted", "reject")
    if contract.request_id != projection.request_id:
        issue("request_mismatch", "request_id", "candidate request does not match", "reject")
    if contract.request_version != projection.request_version:
        issue("stale_request", "request_version", "candidate request version is stale", "reject")

    task_keys = [task.task_key for task in contract.tasks]
    if len(task_keys) != len(set(task_keys)):
        issue("duplicate_task_key", "tasks", "candidate task keys must be unique", "reject")
    task_key_set = set(task_keys)

    for index, task in enumerate(contract.tasks):
        if task.deadline is not None and task.deadline.flexibility == "unknown":
            issue(
                "deadline_authority_unknown",
                f"tasks[{index}].deadline.flexibility",
                "deadline flexibility requires an explicit authority decision",
                "clarify",
            )

    assumption_ids = [assumption.assumption_id for assumption in contract.assumptions]
    if len(assumption_ids) != len(set(assumption_ids)):
        issue("duplicate_assumption", "assumptions", "assumption IDs must be unique", "reject")
    assumption_set = set(assumption_ids)

    source_versions = {source.source_version_id: source for source in projection.sources}
    clarification_responses = {
        answer.response_id: answer for answer in projection.clarification_answers
    }
    for path, basis in _all_bases(contract):
        if isinstance(basis, EvidenceBasis):
            source = source_versions.get(basis.source_version_id)
            if source is None:
                issue(
                    "source_not_permitted",
                    path,
                    "evidence refers to a source version outside the permitted projection",
                    "reject",
                )
                continue
            if source.freshness == "stale" or (
                source.expires_at is not None and source.expires_at <= now
            ):
                issue("stale_source", path, "evidence source is stale or expired", "reject")
            if basis.locator not in {excerpt.locator for excerpt in source.excerpts}:
                issue("unknown_locator", path, "evidence locator was not retrieved", "reject")
            if source.authority_status != "authoritative":
                issue(
                    "unconfirmed_source_authority",
                    path,
                    "material evidence is not marked authoritative",
                    "clarify",
                )
        elif isinstance(basis, AssumptionBasis) and basis.assumption_id not in assumption_set:
            issue("unknown_assumption", path, "basis refers to an unknown assumption", "reject")
        elif (
            isinstance(basis, ClarificationBasis)
            and basis.response_id not in clarification_responses
        ):
            issue(
                "unknown_clarification_response",
                path,
                "basis refers to a clarification response outside the permitted projection",
                "reject",
            )

    graph: dict[str, set[str]] = defaultdict(set)
    for index, dependency in enumerate(contract.dependencies):
        if dependency.predecessor_task_key not in task_key_set:
            issue(
                "unknown_predecessor",
                f"dependencies[{index}]",
                "dependency predecessor is not a candidate task",
                "reject",
            )
        if dependency.successor_task_key not in task_key_set:
            issue(
                "unknown_successor",
                f"dependencies[{index}]",
                "dependency successor is not a candidate task",
                "reject",
            )
        if dependency.predecessor_task_key == dependency.successor_task_key:
            issue(
                "self_dependency", f"dependencies[{index}]", "self-dependency is invalid", "reject"
            )
        graph[dependency.predecessor_task_key].add(dependency.successor_task_key)
    if _cycle_exists(graph):
        issue(
            "dependency_cycle", "dependencies", "candidate dependencies contain a cycle", "reject"
        )

    for index, assumption in enumerate(contract.assumptions):
        if assumption.material:
            issue(
                "material_assumption",
                f"assumptions[{index}]",
                "material assumptions require explicit human confirmation",
                "clarify",
            )
    for index, clarification in enumerate(contract.clarifications):
        unknown_related = set(clarification.related_task_keys) - task_key_set
        if unknown_related:
            issue(
                "unknown_clarification_task",
                f"clarifications[{index}]",
                "clarification refers to an unknown candidate task",
                "reject",
            )
        if clarification.blocks_planning:
            issue(
                "model_clarification",
                f"clarifications[{index}]",
                clarification.question,
                "clarify",
            )
    for index, unsupported in enumerate(contract.unsupported):
        if set(unsupported.related_task_keys) - task_key_set:
            issue(
                "unknown_unsupported_task",
                f"unsupported[{index}]",
                "unsupported marker refers to an unknown candidate task",
                "reject",
            )
        issue(
            unsupported.code,
            f"unsupported[{index}]",
            unsupported.description,
            "clarify",
        )

    if not contract.tasks and not contract.clarifications and not contract.unsupported:
        issue(
            "empty_interpretation", "tasks", "candidate contains no work or clarification", "reject"
        )

    if any(item.disposition == "reject" for item in issues):
        status: Literal["admitted", "clarification_required", "rejected"] = "rejected"
    elif any(item.disposition == "clarify" for item in issues):
        status = "clarification_required"
    else:
        status = "admitted"
    return AdmissionResult(status=status, issues=tuple(issues))


def actionable_clarifications(
    contract: CandidateTaskContract,
    admission: AdmissionResult,
) -> tuple[CandidateClarification, ...]:
    """Return every manager action required by a clarification admission result."""

    questions = list(contract.clarifications)
    used_keys = {question.question_key for question in questions}
    for index, issue in enumerate(admission.issues, start=1):
        if issue.disposition != "clarify" or issue.code == "model_clarification":
            continue
        suffix = hashlib.sha256(f"{issue.code}:{issue.path}".encode()).hexdigest()[:8]
        question_key = f"admission_{index}_{suffix}"
        collision = 1
        while question_key in used_keys:
            collision += 1
            question_key = f"admission_{index}_{suffix}_{collision}"
        used_keys.add(question_key)

        category: Literal["missing_data", "authority", "timezone", "ambiguity", "disclosure"]
        if issue.code in {
            "authority_unknown",
            "deadline_authority_unknown",
            "material_assumption",
            "unconfirmed_source_authority",
        }:
            category = "authority"
        elif issue.code == "insufficient_context":
            category = "missing_data"
        elif issue.code == "sensitive_request":
            category = "disclosure"
        else:
            category = "ambiguity"

        related_task_keys: tuple[str, ...] = ()
        question = f"Resolve this planning issue before continuing: {issue.message}"
        assumption_match = re.fullmatch(r"assumptions\[(\d+)\]", issue.path)
        unsupported_match = re.fullmatch(r"unsupported\[(\d+)\]", issue.path)
        deadline_match = re.fullmatch(r"tasks\[(\d+)\]\.deadline\.flexibility", issue.path)
        if issue.code == "material_assumption" and assumption_match is not None:
            assumption_index = int(assumption_match.group(1))
            if assumption_index < len(contract.assumptions):
                assumption = contract.assumptions[assumption_index]
                authority = assumption.authority_required.replace("_", " ")
                question = (
                    f"Confirm or correct this material assumption: {assumption.statement} "
                    f"Required decision authority: {authority}."
                )
        elif unsupported_match is not None:
            unsupported_index = int(unsupported_match.group(1))
            if unsupported_index < len(contract.unsupported):
                unsupported = contract.unsupported[unsupported_index]
                related_task_keys = unsupported.related_task_keys
                question = (
                    "The requested plan contains this unresolved item: "
                    f"{unsupported.description} Explain how it should be handled."
                )
        elif deadline_match is not None:
            task_index = int(deadline_match.group(1))
            if task_index < len(contract.tasks):
                task = contract.tasks[task_index]
                related_task_keys = (task.task_key,)
                question = (
                    f"Is the deadline for {task.title} fixed or negotiable, and who has "
                    "authority to make that decision?"
                )

        questions.append(
            CandidateClarification(
                question_key=question_key,
                category=category,
                question=question[:1000],
                blocks_planning=True,
                related_task_keys=related_task_keys,
            )
        )
    return tuple(questions)
