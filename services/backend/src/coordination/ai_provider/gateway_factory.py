from __future__ import annotations

from coordination.ai_provider.persistence import (
    CompanyGeminiCredentialNotConfiguredError,
    CompanyGeminiCredentialResolver,
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
            api_key = self._credentials.resolve_gemini_api_key(context=context)
        except CompanyGeminiCredentialNotConfiguredError:
            fallback = self._settings.gemini_api_key
            if fallback is None or self._settings.environment == "production":
                raise
            api_key = fallback.get_secret_value()
        return GoogleGeminiGateway(
            api_key=api_key,
            configuration=GatewayConfiguration(
                model=self._settings.gemini_model,
                timeout_seconds=self._settings.gemini_timeout_seconds,
                retry_attempts=1,
                max_output_tokens=self._settings.gemini_max_output_tokens,
            ),
        )
