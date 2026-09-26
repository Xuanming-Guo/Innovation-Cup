from __future__ import annotations

import hashlib
from typing import Protocol
from uuid import UUID

import psycopg

from coordination.ai_provider.contracts import AiProviderConfiguration
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
        api_key: str,
        validated_model: str,
        correlation_id: UUID,
    ) -> AiProviderConfiguration: ...

    def remove(
        self, *, context: CompanyContext, correlation_id: UUID
    ) -> AiProviderConfiguration: ...


class CompanyGeminiCredentialResolver(Protocol):
    def resolve_gemini_api_key(self, *, context: CompanyContext) -> str: ...


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
                    "select * from app.get_company_gemini_configuration()"
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
        api_key: str,
        validated_model: str,
        correlation_id: UUID,
    ) -> AiProviderConfiguration:
        fingerprint = hashlib.sha256(api_key.encode("utf-8")).digest()
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
                    "select * from app.configure_company_gemini_credential(%s, %s, %s, %s)",
                    (api_key, fingerprint, validated_model, correlation_id),
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

    def remove(
        self, *, context: CompanyContext, correlation_id: UUID
    ) -> AiProviderConfiguration:
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
                    "select * from app.remove_company_gemini_credential(%s)",
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

    def resolve_gemini_api_key(self, *, context: CompanyContext) -> str:
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
                    "select app.resolve_company_gemini_api_key() as api_key"
                ).fetchone()
        except psycopg.errors.NoDataFound as error:
            raise CompanyGeminiCredentialNotConfiguredError(
                "company Gemini credential is not configured"
            ) from error
        except psycopg.Error as error:
            raise AiProviderStoreUnavailableError(
                "company Gemini credential is unavailable"
            ) from error
        value = row.get("api_key") if row else None
        if not isinstance(value, str) or not value:
            raise CompanyGeminiCredentialNotConfiguredError(
                "company Gemini credential is not configured"
            )
        return value


def _configuration(row: dict[str, object]) -> AiProviderConfiguration:
    return AiProviderConfiguration.model_validate(row)
