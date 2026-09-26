from __future__ import annotations

from importlib.metadata import version
from typing import Any, Literal, Protocol

import httpx
from google import genai
from google.auth.credentials import Credentials
from google.genai import errors, types
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from coordination.interpretation.contracts import CandidateTaskContract
from coordination.interpretation.projection import InterpretationProjection
from coordination.interpretation.prompt import (
    INTERPRETATION_SYSTEM_INSTRUCTION,
    build_interpretation_prompt,
    candidate_response_schema,
)


class GatewayConfiguration(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    model: str = Field(min_length=1, max_length=200)
    prompt_version: str = "interpretation-v1"
    schema_version: Literal["candidate-task-contract.v1"] = "candidate-task-contract.v1"
    safety_profile: str = "provider-default-no-tools-v1"
    timeout_seconds: int = Field(default=20, ge=1, le=120)
    retry_attempts: int = Field(default=2, ge=1, le=3)
    max_output_tokens: int = Field(default=8192, ge=512, le=32_768)
    temperature: float = Field(default=0.0, ge=0.0, le=1.0)

    def ledger_values(self) -> dict[str, object]:
        return {
            "max_output_tokens": self.max_output_tokens,
            "retry_attempts": self.retry_attempts,
            "safety_profile": self.safety_profile,
            "temperature": self.temperature,
            "timeout_seconds": self.timeout_seconds,
        }


class ModelUsage(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    prompt_tokens: int | None
    candidate_tokens: int | None
    total_tokens: int | None
    thought_tokens: int | None


class GatewayResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    contract: CandidateTaskContract
    model_version: str
    provider_response_id: str | None
    sdk_version: str
    finish_reason: str | None
    usage: ModelUsage


class GeminiGatewayError(RuntimeError):
    code: str = "model_error"
    outcome: str = "failed"


class GeminiTimeoutError(GeminiGatewayError):
    code = "model_timeout"
    outcome = "timeout"


class GeminiThrottledError(GeminiGatewayError):
    code = "model_throttled"
    outcome = "throttled"


class GeminiTransientError(GeminiGatewayError):
    code = "model_transient_error"
    outcome = "transient_failure"


class GeminiRefusalError(GeminiGatewayError):
    code = "model_refusal"
    outcome = "refused"


class GeminiInvalidOutputError(GeminiGatewayError):
    code = "model_invalid_output"
    outcome = "invalid_output"


class GeminiPermanentError(GeminiGatewayError):
    code = "model_permanent_error"
    outcome = "permanent_failure"


class InterpretationGateway(Protocol):
    configuration: GatewayConfiguration

    def generate(self, projection: InterpretationProjection) -> GatewayResponse: ...


class GoogleGeminiGateway:
    """Single server-only Google Gen AI SDK adapter. It exposes no tools to the model."""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        vertex_credentials: Credentials | None = None,
        vertex_project_id: str | None = None,
        vertex_location: str | None = None,
        configuration: GatewayConfiguration,
        client: Any | None = None,
    ) -> None:
        using_api_key = bool(api_key)
        using_vertex = all((vertex_credentials, vertex_project_id, vertex_location))
        if client is None and using_api_key == using_vertex:
            raise ValueError("exactly one Google credential mode is required")
        self.configuration = configuration
        http_options = types.HttpOptions(
            timeout=configuration.timeout_seconds * 1000,
            retry_options=types.HttpRetryOptions(
                attempts=configuration.retry_attempts,
                initial_delay=0.25,
                max_delay=2.0,
                exp_base=2.0,
                jitter=0.25,
                http_status_codes=[408, 429, 500, 502, 503, 504],
            ),
        )
        if client is not None:
            self._client = client
        elif using_api_key:
            self._client = genai.Client(api_key=api_key, http_options=http_options)
        else:
            self._client = genai.Client(
                vertexai=True,
                project=vertex_project_id,
                location=vertex_location,
                credentials=vertex_credentials,
                http_options=http_options,
            )

    def generate(self, projection: InterpretationProjection) -> GatewayResponse:
        try:
            response = self._client.models.generate_content(
                model=self.configuration.model,
                contents=build_interpretation_prompt(projection),
                config=types.GenerateContentConfig(
                    system_instruction=INTERPRETATION_SYSTEM_INSTRUCTION,
                    temperature=self.configuration.temperature,
                    max_output_tokens=self.configuration.max_output_tokens,
                    response_mime_type="application/json",
                    response_json_schema=candidate_response_schema(),
                ),
            )
        except errors.ClientError as error:
            if error.code == 429:
                raise GeminiThrottledError("Gemini request was throttled") from error
            if error.code == 408:
                raise GeminiTimeoutError("Gemini request timed out") from error
            raise GeminiPermanentError("Gemini rejected the request") from error
        except errors.ServerError as error:
            raise GeminiTransientError("Gemini service failed after bounded retries") from error
        except (httpx.TimeoutException, TimeoutError) as error:
            raise GeminiTimeoutError("Gemini request timed out") from error
        except (httpx.TransportError, ConnectionError) as error:
            raise GeminiTransientError("Gemini transport failed after bounded retries") from error

        candidates = response.candidates or []
        candidate = candidates[0] if candidates else None
        finish_reason = (
            str(candidate.finish_reason) if candidate and candidate.finish_reason else None
        )
        try:
            parsed = response.parsed
            if isinstance(parsed, CandidateTaskContract):
                contract = parsed
            elif parsed is not None:
                contract = CandidateTaskContract.model_validate(parsed)
            else:
                text = response.text
                if not text:
                    if finish_reason and finish_reason not in {"STOP", "FinishReason.STOP"}:
                        raise GeminiRefusalError("Gemini returned no permitted candidate")
                    raise GeminiInvalidOutputError("Gemini returned no candidate payload")
                contract = CandidateTaskContract.model_validate_json(text)
        except GeminiGatewayError:
            raise
        except (ValidationError, ValueError, TypeError) as error:
            raise GeminiInvalidOutputError("Gemini returned invalid structured output") from error

        usage = response.usage_metadata
        return GatewayResponse(
            contract=contract,
            model_version=response.model_version or self.configuration.model,
            provider_response_id=response.response_id,
            sdk_version=version("google-genai"),
            finish_reason=finish_reason,
            usage=ModelUsage(
                prompt_tokens=usage.prompt_token_count if usage else None,
                candidate_tokens=usage.candidates_token_count if usage else None,
                total_tokens=usage.total_token_count if usage else None,
                thought_tokens=usage.thoughts_token_count if usage else None,
            ),
        )
