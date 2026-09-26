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


class CompanyGeminiCredentialResolver(Protocol):
    def resolve_google_credential(self, *, context: CompanyContext) -> ResolvedAiCredential: ...


class PostgresAiProviderStore:
    def __init__(self, dsn: str, *, connect_timeout_seconds: int = 5) -> None:
        self._dsn = dsn
        self._connect_timeout_seconds = connect_timeout_seconds

    def get_configuration(self, *, context: CompanyContext) -> AiProviderConfiguration:
        try:
            with company_transaction(
                self._dsn,
                role="coordination_api",
                actor_id=context.actor.user_id,
                company_id=context.company_id,
                purpose="ai_provider.configuration.read",
                connect_timeout_seconds=self._connect_timeout_seconds,
            ) as connection:
                row = connection.execute(
                    "select * from app.get_company_ai_configuration()"
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
                connect_timeout_seconds=self._connect_timeout_seconds,
            ) as connection:
                row = connection.execute(
                    """
                    select * from app.configure_company_ai_credential(
                      %s, %s, %s, %s, %s, %s, %s, %s, %s
                    )
                    """,
                    (
                        provider,
                        credential_kind,
                        credential_secret,
                        fingerprint,
                        validated_model,
                        vertex_project_id,
                        vertex_client_email,
                        vertex_location,
                        correlation_id,
                    ),
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
                connect_timeout_seconds=self._connect_timeout_seconds,
            ) as connection:
                connection.execute(
                    "select app.record_company_ai_credential_test(%s, %s, %s, %s, %s)",
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
        try:
            with company_transaction(
                self._dsn,
                role="coordination_api",
                actor_id=context.actor.user_id,
                company_id=context.company_id,
                purpose="ai_provider.configuration.delete",
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

    def resolve_google_credential(self, *, context: CompanyContext) -> ResolvedAiCredential:
        try:
            with company_transaction(
                self._dsn,
                role="coordination_worker",
                actor_id=context.actor.user_id,
                company_id=context.company_id,
                purpose="ai_provider.credential.resolve",
                connect_timeout_seconds=self._connect_timeout_seconds,
            ) as connection:
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
