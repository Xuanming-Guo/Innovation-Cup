from types import SimpleNamespace
from typing import Any
from uuid import uuid4

import pytest
from pydantic import BaseModel, SecretStr, ValidationError

from coordination.ai_provider import gateway_factory as factory_module
from coordination.ai_provider.contracts import ResolvedAiCredential
from coordination.ai_provider.gateway_factory import CompanyGeminiGatewayFactory
from coordination.auth.models import AuthenticatedUser, CompanyContext
from coordination.config import Settings
from coordination.interpretation.gateway import (
    GatewayConfiguration,
    GeminiTruncatedOutputError,
    GoogleGeminiGateway,
)


class CredentialResolver:
    def resolve_google_credential(self, *, context: CompanyContext) -> ResolvedAiCredential:
        return ResolvedAiCredential(
            provider="gemini_developer_api",
            credential_kind="api_key",
            credential=SecretStr("test-only-no-provider-call"),
            validated_model="gemini-test",
        )

    def with_lease(self, job_id: object, lease_token: object) -> "CredentialResolver":
        return self


@pytest.mark.parametrize(
    "planning,plan_cap,expected",
    [(True, 32768, 32768), (False, 32768, 8192), (True, None, 8192), (True, 4096, 4096)],
)
def test_full_plan_budget_is_explicit_scoped_and_retained_after_lease_binding(
    monkeypatch: pytest.MonkeyPatch, planning: bool, plan_cap: int | None, expected: int
) -> None:
    captured: list[GatewayConfiguration] = []

    def capture_gateway(**values: Any) -> Any:
        captured.append(values["configuration"])
        return SimpleNamespace(configuration=values["configuration"])

    monkeypatch.setattr(factory_module, "GoogleGeminiGateway", capture_gateway)
    monkeypatch.setitem(Settings.model_config, "env_file", None)
    settings = Settings(
        gemini_model="gemini-test",
        gemini_max_output_tokens=8192,
        gemini_plan_max_output_tokens=plan_cap,
    )
    context = CompanyContext(
        actor=AuthenticatedUser(uuid4(), "authenticated", uuid4(), "aal1"),
        company_id=uuid4(),
        membership_id=uuid4(),
        administrative_role="manager",
        employee_id=None,
    )
    factory = CompanyGeminiGatewayFactory(
        settings=settings, credentials=CredentialResolver(), for_planning=planning
    )
    factory(context)
    factory.for_lease(uuid4(), uuid4())(context)
    assert [config.max_output_tokens for config in captured] == [expected, expected]
    assert all(config.retry_attempts == 1 for config in captured)
    assert all(config.ledger_values()["max_output_tokens"] == expected for config in captured)


@pytest.mark.parametrize("invalid_cap", [511, 32769])
def test_planning_output_budget_cannot_exceed_its_bounds(
    monkeypatch: pytest.MonkeyPatch, invalid_cap: int
) -> None:
    monkeypatch.setitem(Settings.model_config, "env_file", None)
    with pytest.raises(ValidationError):
        Settings(gemini_plan_max_output_tokens=invalid_cap)


class TinyOutput(BaseModel):
    complete: bool


def test_larger_cap_reaches_sdk_but_truncated_parseable_response_is_still_rejected() -> None:
    requests: list[dict[str, Any]] = []
    closed: list[bool] = []

    def generate(**values: Any) -> Any:
        requests.append(values)
        return SimpleNamespace(
            candidates=[SimpleNamespace(finish_reason="MAX_TOKENS")],
            parsed=TinyOutput(complete=True),
            usage_metadata=None,
        )

    gateway = GoogleGeminiGateway(
        configuration=GatewayConfiguration(model="gemini-test", max_output_tokens=32768),
        client=SimpleNamespace(
            models=SimpleNamespace(generate_content=generate), close=lambda: closed.append(True)
        ),
    )
    with pytest.raises(GeminiTruncatedOutputError):
        gateway.generate_structured(
            operation="plan.revise.v1",
            system_instruction="Test only; no provider.",
            prompt="{}",
            output_type=TinyOutput,
        )
    assert len(requests) == 1
    assert requests[0]["config"].max_output_tokens == 32768
    assert requests[0]["config"].automatic_function_calling.disable is True
    assert closed == [True]
