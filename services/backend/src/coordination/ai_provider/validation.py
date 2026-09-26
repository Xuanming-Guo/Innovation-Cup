from __future__ import annotations

from collections.abc import Callable
from typing import Any, Protocol

import httpx
from google import genai
from google.genai import errors, types

from coordination.ai_provider.contracts import GeminiCredentialValidation


class InvalidGeminiCredentialError(RuntimeError):
    """The supplied key cannot access the configured Gemini model."""


class GeminiCredentialValidationUnavailableError(RuntimeError):
    """The provider could not complete a credential check safely."""


class GeminiCredentialValidator(Protocol):
    def validate(self, *, api_key: str) -> GeminiCredentialValidation: ...


class GoogleGeminiCredentialValidator:
    """Validate a key without sending company content or generating billable output."""

    def __init__(
        self,
        *,
        model: str,
        timeout_seconds: int,
        client_factory: Callable[[str], Any] | None = None,
    ) -> None:
        self._model = model
        self._timeout_seconds = timeout_seconds
        self._client_factory = client_factory or self._build_client

    def _build_client(self, api_key: str) -> Any:
        return genai.Client(
            api_key=api_key,
            http_options=types.HttpOptions(timeout=self._timeout_seconds * 1000),
        )

    def validate(self, *, api_key: str) -> GeminiCredentialValidation:
        client = self._client_factory(api_key)
        try:
            client.models.get(model=self._model)
        except errors.ClientError as error:
            if error.code in {400, 401, 403, 404}:
                raise InvalidGeminiCredentialError(
                    "Gemini rejected the credential or configured model"
                ) from error
            raise GeminiCredentialValidationUnavailableError(
                "Gemini credential validation was throttled"
            ) from error
        except errors.ServerError as error:
            raise GeminiCredentialValidationUnavailableError(
                "Gemini credential validation is temporarily unavailable"
            ) from error
        except (
            httpx.TimeoutException,
            TimeoutError,
            httpx.TransportError,
            ConnectionError,
        ) as error:
            raise GeminiCredentialValidationUnavailableError(
                "Gemini credential validation could not reach the provider"
            ) from error
        finally:
            close = getattr(client, "close", None)
            if callable(close):
                close()
        return GeminiCredentialValidation(model=self._model)
