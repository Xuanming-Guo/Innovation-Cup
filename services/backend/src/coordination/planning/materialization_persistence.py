from __future__ import annotations

from typing import cast
from uuid import UUID

import psycopg

from coordination.auth.models import CompanyContext
from coordination.db.session import company_transaction
from coordination.interpretation.contracts import CandidateTaskContract
from coordination.planning.materializer import (
    MaterializationError,
    MaterializationInput,
    PlanningResourceProfile,
    materialize_candidate,
)
from coordination.planning.persistence import PostgresPlanningLedger


class CandidateMaterializationStoreError(RuntimeError):
    """Materialization state could not be read or written safely."""


class CandidateMaterializationConflictError(ValueError):
    """The admitted candidate or its authoritative planning context is unusable."""


class PostgresCandidateMaterializer:
    def __init__(self, dsn: str, *, connect_timeout_seconds: int = 5) -> None:
        self._dsn = dsn
        self._connect_timeout_seconds = connect_timeout_seconds
        self._ledger = PostgresPlanningLedger(
            dsn, connect_timeout_seconds=connect_timeout_seconds
        )

    def materialize(
        self, *, context: CompanyContext, candidate_contract_id: UUID
    ) -> UUID:
        try:
            with company_transaction(
                self._dsn,
                role="coordination_worker",
                actor_id=context.actor.user_id,
                company_id=context.company_id,
                purpose="planning:materialize-candidate",
                connect_timeout_seconds=self._connect_timeout_seconds,
            ) as connection:
                candidate = connection.execute(
                    """
                    select candidate.id, candidate.contract_json, candidate.created_at,
                           candidate.request_id, request.requested_priority_key,
                           request.requester_membership_id, retrieval.projection_digest,
                           company.planning_revision, company.policy_revision
                    from app.candidate_contracts as candidate
                    join app.planning_requests as request
                      on request.company_id = candidate.company_id
                     and request.id = candidate.request_id
                    join app.interpretation_runs as interpretation
                      on interpretation.company_id = candidate.company_id
                     and interpretation.id = candidate.interpretation_run_id
                    join app.retrieval_runs as retrieval
                      on retrieval.company_id = interpretation.company_id
                     and retrieval.id = interpretation.retrieval_run_id
                    join app.companies as company on company.id = candidate.company_id
                    where candidate.company_id = %s and candidate.id = %s
                      and candidate.admission_status = 'admitted'
                      and request.status = 'interpreted'
                    """,
                    (context.company_id, candidate_contract_id),
                ).fetchone()
                if candidate is None:
                    raise CandidateMaterializationConflictError(
                        "admitted candidate is absent or no longer current"
                    )
                selected_sources = connection.execute(
                    """
                    select selected.source_version_id
                    from app.planning_request_sources as selected
                    join app.source_records as source
                      on source.company_id = selected.company_id
                     and source.id = selected.source_id
                    join app.source_versions as version
                      on version.company_id = selected.company_id
                     and version.id = selected.source_version_id
                    where selected.company_id = %s and selected.request_id = %s
                      and source.status = 'active'
                      and source.authority_status = 'authoritative'
                      and source.current_version_id = selected.source_version_id
                      and (version.expires_at is null or version.expires_at > clock_timestamp())
                    order by selected.source_version_id
                    """,
                    (context.company_id, candidate["request_id"]),
                ).fetchall()
                expected_sources = connection.execute(
                    """
                    select count(*)::integer as count
                    from app.planning_request_sources
                    where company_id = %s and request_id = %s
                    """,
                    (context.company_id, candidate["request_id"]),
                ).fetchone()
                if (
                    expected_sources is None
                    or not selected_sources
                    or len(selected_sources) != expected_sources["count"]
                ):
                    raise CandidateMaterializationConflictError(
                        "selected source manifest is stale or non-authoritative"
                    )
                profile_rows = connection.execute(
                    """
                    select profile.resource_id, profile.timezone,
                           profile.availability_windows, profile.capability_keys,
                           profile.permission_keys, profile.daily_active_minutes,
                           profile.profile_revision, profile.estimate_revision
                    from app.planning_resource_profiles as profile
                    join app.execution_resources as resource
                      on resource.company_id = profile.company_id
                     and resource.id = profile.resource_id
                     and resource.status = 'active'
                    where profile.company_id = %s and profile.active
                    order by profile.resource_id
                    """,
                    (context.company_id,),
                ).fetchall()
        except CandidateMaterializationConflictError:
            raise
        except psycopg.Error as error:
            raise CandidateMaterializationStoreError(
                "candidate materialization context is unavailable"
            ) from error

        try:
            contract = CandidateTaskContract.model_validate(candidate["contract_json"])
            if (
                contract.company_id != context.company_id
                or contract.request_id != candidate["request_id"]
            ):
                raise CandidateMaterializationConflictError(
                    "candidate contract identity does not match its ledger record"
                )
            profiles = tuple(
                PlanningResourceProfile.model_validate(
                    {
                        "resource_id": row["resource_id"],
                        "timezone": row["timezone"],
                        "availability": row["availability_windows"],
                        "capability_keys": tuple(row["capability_keys"]),
                        "permission_keys": tuple(row["permission_keys"]),
                        "daily_active_minutes": row["daily_active_minutes"],
                        "profile_revision": row["profile_revision"],
                        "estimate_revision": row["estimate_revision"],
                    }
                )
                for row in profile_rows
            )
            snapshot = materialize_candidate(
                MaterializationInput(
                    candidate_contract_id=candidate_contract_id,
                    contract=contract,
                    source_manifest_digest=bytes(candidate["projection_digest"]).hex(),
                    selected_source_version_ids=tuple(
                        cast(UUID, row["source_version_id"]) for row in selected_sources
                    ),
                    base_company_revision=cast(int, candidate["planning_revision"]),
                    policy_revision=cast(int, candidate["policy_revision"]),
                    requested_priority_key=cast(str | None, candidate["requested_priority_key"]),
                    requester_membership_id=cast(UUID, candidate["requester_membership_id"]),
                    resources=profiles,
                    frozen_at=candidate["created_at"],
                )
            )
            self._ledger.save_snapshot(context=context, snapshot=snapshot)
        except CandidateMaterializationConflictError:
            raise
        except MaterializationError as error:
            raise CandidateMaterializationConflictError(str(error)) from error
        except ValueError as error:
            raise CandidateMaterializationConflictError(
                "candidate or planning profile failed deterministic validation"
            ) from error
        return snapshot.snapshot_id
