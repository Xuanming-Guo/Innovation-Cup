from __future__ import annotations

from uuid import UUID

from pydantic import SecretStr

from coordination.ai_provider.contracts import ResolvedAiCredential
from coordination.ai_provider.persistence import (
    CompanyGeminiCredentialNotConfiguredError,
    CompanyGeminiCredentialResolver,
)
from coordination.ai_provider.validation import (
    InvalidGeminiCredentialError,
    parse_vertex_service_account,
)
from coordination.ai_rate_limit import GeminiRequestLimiter
from coordination.auth.models import CompanyContext
from coordination.config import Settings
from coordination.interpretation.gateway import GatewayConfiguration, GoogleGeminiGateway


class CompanyGeminiGatewayFactory:
    """Build a short-lived gateway from the current company's server-side credential."""

    def __init__(
        self,
        *,
        settings: Settings,
        credentials: CompanyGeminiCredentialResolver,
        for_planning: bool = False,
        request_limiter: GeminiRequestLimiter | None = None,
    ) -> None:
        self._settings = settings
        self._credentials = credentials
        self._for_planning = for_planning
        self._request_limiter = request_limiter

    def for_lease(self, job_id: UUID, lease_token: UUID) -> CompanyGeminiGatewayFactory:
        bind = getattr(self._credentials, "with_lease", None)
        if not callable(bind):
            raise ValueError("credential resolver does not support fenced durable execution")
        return CompanyGeminiGatewayFactory(
            settings=self._settings,
            credentials=bind(job_id, lease_token),
            for_planning=self._for_planning,
            request_limiter=self._request_limiter,
        )

    def __call__(self, context: CompanyContext) -> GoogleGeminiGateway:
        try:
            credential = self._credentials.resolve_google_credential(context=context)
        except CompanyGeminiCredentialNotConfiguredError:
            fallback = self._settings.gemini_api_key
            if (
                fallback is None
                or self._settings.environment == "production"
                or context.demo_run_id is not None
            ):
                raise
            credential = ResolvedAiCredential(
                provider="gemini_developer_api",
                credential_kind="api_key",
                credential=SecretStr(fallback.get_secret_value()),
                validated_model=self._settings.gemini_model,
            )
        if credential.validated_model != self._settings.gemini_model:
            raise CompanyGeminiCredentialNotConfiguredError(
                "company Google credential must be revalidated for the configured model"
            )

        configuration = GatewayConfiguration(
            model=self._settings.gemini_model,
            timeout_seconds=self._settings.gemini_timeout_seconds,
            retry_attempts=1,
            max_output_tokens=(
                self._settings.gemini_plan_max_output_tokens
                if self._for_planning and self._settings.gemini_plan_max_output_tokens is not None
                else self._settings.gemini_max_output_tokens
            ),
        )
        if credential.credential_kind == "api_key":
            if credential.provider != "gemini_developer_api":
                raise CompanyGeminiCredentialNotConfiguredError(
                    "company Google credential metadata does not match policy"
                )
            return GoogleGeminiGateway(
                api_key=credential.credential.get_secret_value(),
                configuration=configuration,
                request_limiter=self._request_limiter,
            )

        try:
            parsed = parse_vertex_service_account(
                credential.credential.get_secret_value(),
                allowed_project_ids=self._settings.vertex_project_allowlist,
            )
        except InvalidGeminiCredentialError as error:
            raise CompanyGeminiCredentialNotConfiguredError(
                "company Vertex credential is no longer valid"
            ) from error
        if (
            credential.provider != "vertex_ai"
            or credential.vertex_project_id != parsed.project_id
            or credential.vertex_client_email != parsed.client_email
            or credential.vertex_location != self._settings.vertex_location
        ):
            raise CompanyGeminiCredentialNotConfiguredError(
                "company Vertex credential metadata does not match policy"
            )
        return GoogleGeminiGateway(
            vertex_credentials=parsed.credentials,
            vertex_project_id=parsed.project_id,
            vertex_location=self._settings.vertex_location,
            configuration=configuration,
            request_limiter=self._request_limiter,
        )
