from __future__ import annotations

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
    ) -> None:
        self._settings = settings
        self._credentials = credentials

    def __call__(self, context: CompanyContext) -> GoogleGeminiGateway:
        try:
            credential = self._credentials.resolve_google_credential(context=context)
        except CompanyGeminiCredentialNotConfiguredError:
            fallback = self._settings.gemini_api_key
            if fallback is None or self._settings.environment == "production":
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
            max_output_tokens=self._settings.gemini_max_output_tokens,
        )
        if credential.credential_kind == "api_key":
            return GoogleGeminiGateway(
                api_key=credential.credential.get_secret_value(),
                configuration=configuration,
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
        )
