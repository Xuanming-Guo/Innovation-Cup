from __future__ import annotations

import hashlib
from typing import Protocol
from uuid import UUID

import psycopg
from pydantic import SecretStr

from coordination.ai_provider.contracts import (
    AiCredentialKind,
    AiProviderConfiguration,
    AiProviderName,
    ResolvedAiCredential,
)
from coordination.auth.models import CompanyContext
from coordination.db.session import company_transaction


class AiProviderStoreError(RuntimeError):
    """Base exception for safe AI provider persistence failures."""


class AiProviderAuthorityError(AiProviderStoreError):
    pass


class CompanyGeminiCredentialNotConfiguredError(AiProviderStoreError):
    pass


class AiProviderStoreUnavailableError(AiProviderStoreError):
    pass


class AiProviderStore(Protocol):
    def get_configuration(self, *, context: CompanyContext) -> AiProviderConfiguration: ...

    def configure(
        self,
        *,
        context: CompanyContext,
        provider: AiProviderName,
        credential_kind: AiCredentialKind,
        credential_secret: str,
        validated_model: str,
        vertex_project_id: str | None,
        vertex_client_email: str | None,
        vertex_location: str | None,
        correlation_id: UUID,
    ) -> AiProviderConfiguration: ...

    def record_validation(
        self,
        *,
        context: CompanyContext,
        provider: AiProviderName,
        credential_kind: AiCredentialKind,
        outcome: str,
        validated_model: str | None,
        correlation_id: UUID,
    ) -> None: ...

    def remove(
        self, *, context: CompanyContext, correlation_id: UUID
    ) -> AiProviderConfiguration: ...

    def get_demo_binding(self, *, context: CompanyContext) -> dict[str, object]: ...
    def bind_demo_version(self, *, context: CompanyContext, profile_version_id: UUID) -> None: ...
    def revoke_demo_version(self, *, context: CompanyContext, profile_version_id: UUID) -> None: ...


class CompanyGeminiCredentialResolver(Protocol):
    def resolve_google_credential(self, *, context: CompanyContext) -> ResolvedAiCredential: ...


class PostgresAiProviderStore:
    def __init__(
        self,
        dsn: str,
        *,
        connect_timeout_seconds: int = 5,
        job_id: UUID | None = None,
        lease_token: UUID | None = None,
    ) -> None:
        self._dsn = dsn
        self._connect_timeout_seconds = connect_timeout_seconds
        self._job_id = job_id
        self._lease_token = lease_token

    def with_lease(self, job_id: UUID, lease_token: UUID) -> PostgresAiProviderStore:
        return PostgresAiProviderStore(
            self._dsn,
            connect_timeout_seconds=self._connect_timeout_seconds,
            job_id=job_id,
            lease_token=lease_token,
        )

    def get_configuration(self, *, context: CompanyContext) -> AiProviderConfiguration:
        try:
            with company_transaction(
                self._dsn,
                role="coordination_api",
                actor_id=context.actor.user_id,
                company_id=context.company_id,
                purpose="ai_provider.configuration.read",
                demo_run_id=context.demo_run_id,
                demo_actor_session_id=context.demo_actor_session_id,
                connect_timeout_seconds=self._connect_timeout_seconds,
            ) as connection:
                row = connection.execute(
                    "select * from app.get_demo_ai_configuration()"
                    if context.demo_run_id is not None
                    else "select * from app.get_company_ai_configuration()"
                ).fetchone()
        except psycopg.errors.InsufficientPrivilege as error:
            raise AiProviderAuthorityError("company administrator authority is required") from error
        except psycopg.Error as error:
            raise AiProviderStoreUnavailableError(
                "AI provider configuration is unavailable"
            ) from error
        if row is None:
            raise AiProviderStoreUnavailableError("AI provider configuration returned no row")
        return _configuration(row)

    def configure(
        self,
        *,
        context: CompanyContext,
        provider: AiProviderName,
        credential_kind: AiCredentialKind,
        credential_secret: str,
        validated_model: str,
        vertex_project_id: str | None,
        vertex_client_email: str | None,
        vertex_location: str | None,
        correlation_id: UUID,
    ) -> AiProviderConfiguration:
        fingerprint = hashlib.sha256(credential_secret.encode("utf-8")).digest()
        try:
            with company_transaction(
                self._dsn,
                role="coordination_api",
                actor_id=context.actor.user_id,
                company_id=context.company_id,
                purpose="ai_provider.configuration.write",
                demo_run_id=context.demo_run_id,
                demo_actor_session_id=context.demo_actor_session_id,
                connect_timeout_seconds=self._connect_timeout_seconds,
            ) as connection:
                parameters = (
                    provider,
                    credential_kind,
                    credential_secret,
                    fingerprint,
                    validated_model,
                    vertex_project_id,
                    vertex_client_email,
                    vertex_location,
                    correlation_id,
                )
                if context.demo_run_id is not None:
                    configured = connection.execute(
                        "select app.configure_demo_ai_credential"
                        "(%s,%s,%s,%s,%s,%s,%s,%s,%s) as value",
                        parameters,
                    ).fetchone()
                    row = connection.execute(
                        "select * from app.get_demo_ai_configuration()"
                    ).fetchone()
                    if row is not None and configured is not None:
                        row["profile_id"] = configured["value"]["profile_id"]
                        row["profile_version_id"] = configured["value"]["profile_version_id"]
                else:
                    row = connection.execute(
                        "select * from app.configure_company_ai_credential"
                        "(%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                        parameters,
                    ).fetchone()
        except psycopg.errors.InsufficientPrivilege as error:
            raise AiProviderAuthorityError("company administrator authority is required") from error
        except psycopg.Error as error:
            raise AiProviderStoreUnavailableError(
                "AI provider configuration could not be stored"
            ) from error
        if row is None:
            raise AiProviderStoreUnavailableError("AI provider configuration returned no row")
        return _configuration(row)

    def record_validation(
        self,
        *,
        context: CompanyContext,
        provider: AiProviderName,
        credential_kind: AiCredentialKind,
        outcome: str,
        validated_model: str | None,
        correlation_id: UUID,
    ) -> None:
        try:
            with company_transaction(
                self._dsn,
                role="coordination_api",
                actor_id=context.actor.user_id,
                company_id=context.company_id,
                purpose="ai_provider.credential.test",
                demo_run_id=context.demo_run_id,
                demo_actor_session_id=context.demo_actor_session_id,
                connect_timeout_seconds=self._connect_timeout_seconds,
            ) as connection:
                connection.execute(
                    "select app.record_demo_ai_credential_test(%s, %s, %s, %s, %s)"
                    if context.demo_run_id is not None
                    else "select app.record_company_ai_credential_test(%s, %s, %s, %s, %s)",
                    (
                        provider,
                        credential_kind,
                        outcome,
                        validated_model,
                        correlation_id,
                    ),
                )
        except psycopg.errors.InsufficientPrivilege as error:
            raise AiProviderAuthorityError("company administrator authority is required") from error
        except psycopg.Error as error:
            raise AiProviderStoreUnavailableError(
                "AI provider credential test could not be recorded"
            ) from error

    def remove(self, *, context: CompanyContext, correlation_id: UUID) -> AiProviderConfiguration:
        if context.demo_run_id is not None:
            raise AiProviderAuthorityError(
                "demo credential removal requires an explicit owned version"
            )
        try:
            with company_transaction(
                self._dsn,
                role="coordination_api",
                actor_id=context.actor.user_id,
                company_id=context.company_id,
                purpose="ai_provider.configuration.delete",
                demo_run_id=context.demo_run_id,
                demo_actor_session_id=context.demo_actor_session_id,
                connect_timeout_seconds=self._connect_timeout_seconds,
            ) as connection:
                row = connection.execute(
                    "select * from app.remove_company_ai_credential(%s)",
                    (correlation_id,),
                ).fetchone()
        except psycopg.errors.InsufficientPrivilege as error:
            raise AiProviderAuthorityError("company administrator authority is required") from error
        except psycopg.Error as error:
            raise AiProviderStoreUnavailableError(
                "AI provider configuration could not be removed"
            ) from error
        if row is None:
            raise AiProviderStoreUnavailableError("AI provider configuration returned no row")
        return _configuration(row)

    def bind_demo_version(self, *, context: CompanyContext, profile_version_id: UUID) -> None:
        if context.demo_run_id is None:
            raise AiProviderAuthorityError("select an owned live run before binding a provider")
        self._demo_version_command(
            context=context, function="bind", profile_version_id=profile_version_id
        )

    def get_demo_binding(self, *, context: CompanyContext) -> dict[str, object]:
        if context.demo_run_id is None:
            raise AiProviderAuthorityError(
                "select an owned run before reading its provider binding"
            )
        try:
            with company_transaction(
                self._dsn,
                role="coordination_api",
                actor_id=context.actor.user_id,
                company_id=context.company_id,
                demo_run_id=context.demo_run_id,
                demo_actor_session_id=context.demo_actor_session_id,
                purpose="ai_provider.demo.binding",
                connect_timeout_seconds=self._connect_timeout_seconds,
            ) as connection:
                row = connection.execute(
                    "select app.get_demo_provider_binding() as value"
                ).fetchone()
                # A scalar SQL function returns a NULL value before a profile exists.
                if row is None or row["value"] is None:
                    return {}
                return dict(row["value"])
        except psycopg.Error as error:
            raise AiProviderStoreUnavailableError(
                "demo provider binding could not be read"
            ) from error

    def revoke_demo_version(self, *, context: CompanyContext, profile_version_id: UUID) -> None:
        if context.demo_run_id is None:
            raise AiProviderAuthorityError("select an owned run before revoking a provider version")
        self._demo_version_command(
            context=context, function="revoke", profile_version_id=profile_version_id
        )

    def _demo_version_command(
        self, *, context: CompanyContext, function: str, profile_version_id: UUID
    ) -> None:
        try:
            with company_transaction(
                self._dsn,
                role="coordination_api",
                actor_id=context.actor.user_id,
                company_id=context.company_id,
                demo_run_id=context.demo_run_id,
                demo_actor_session_id=context.demo_actor_session_id,
                purpose=f"ai_provider.demo.{function}",
                connect_timeout_seconds=self._connect_timeout_seconds,
            ) as connection:
                if function == "bind":
                    connection.execute(
                        "select app.bind_demo_provider(%s,%s,%s)",
                        (context.company_id, context.demo_run_id, profile_version_id),
                    )
                else:
                    connection.execute(
                        "select app.revoke_demo_provider_version(%s,%s)",
                        (context.company_id, profile_version_id),
                    )
        except psycopg.errors.InsufficientPrivilege as error:
            raise AiProviderAuthorityError(
                "the provider version or run is not owned by this actor"
            ) from error
        except psycopg.Error as error:
            raise AiProviderStoreUnavailableError(
                "demo provider version command could not be completed"
            ) from error

    def resolve_google_credential(self, *, context: CompanyContext) -> ResolvedAiCredential:
        try:
            with company_transaction(
                self._dsn,
                role="coordination_worker",
                actor_id=context.actor.user_id,
                company_id=context.company_id,
                purpose="ai_provider.credential.resolve",
                demo_run_id=context.demo_run_id,
                demo_actor_session_id=context.demo_actor_session_id,
                connect_timeout_seconds=self._connect_timeout_seconds,
            ) as connection:
                if self._job_id is not None and self._lease_token is not None:
                    connection.execute(
                        "select set_config('app.job_id',%s,true), "
                        "set_config('app.lease_token',%s,true)",
                        (str(self._job_id), str(self._lease_token)),
                    )
                elif context.demo_run_id is not None:
                    raise AiProviderAuthorityError(
                        "demo provider resolution requires a current fenced worker lease"
                    )
                row = connection.execute(
                    "select * from app.resolve_company_ai_credential()"
                ).fetchone()
        except psycopg.errors.NoDataFound as error:
            raise CompanyGeminiCredentialNotConfiguredError(
                "company Gemini credential is not configured"
            ) from error
        except psycopg.Error as error:
            raise AiProviderStoreUnavailableError(
                "company Gemini credential is unavailable"
            ) from error
        value = row.get("credential_secret") if row else None
        if not isinstance(value, str) or not value or row is None:
            raise CompanyGeminiCredentialNotConfiguredError(
                "company Gemini credential is not configured"
            )
        return ResolvedAiCredential(
            provider=row["provider"],
            credential_kind=row["credential_kind"],
            credential=SecretStr(value),
            validated_model=row["validated_model"],
            vertex_project_id=row["vertex_project_id"],
            vertex_client_email=row["vertex_client_email"],
            vertex_location=row["vertex_location"],
        )


def _configuration(row: dict[str, object]) -> AiProviderConfiguration:
    return AiProviderConfiguration.model_validate(row)
