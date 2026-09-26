from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from google.genai import errors

from coordination.ai_provider.contracts import (
    AiProviderConfiguration,
    GeminiCredentialValidation,
)
from coordination.ai_provider.dependencies import (
    get_ai_provider_store,
    get_gemini_credential_validator,
)
from coordination.ai_provider.validation import (
    GoogleGeminiCredentialValidator,
    InvalidGeminiCredentialError,
)
from coordination.api.main import create_app
from coordination.auth.dependencies import get_membership_resolver, get_token_verifier
from coordination.auth.models import AdministrativeRole, AuthenticatedUser
from coordination.db.memberships import ActiveMembership

USER_ID = UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa")
SESSION_ID = UUID("bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb")
COMPANY_ID = UUID("11111111-1111-4111-8111-111111111111")
MEMBERSHIP_ID = UUID("22222222-2222-4222-8222-222222222222")
NOW = datetime(2026, 9, 26, 12, tzinfo=UTC)
TEST_KEY = "test-company-gemini-key-value-0001"


class FakeVerifier:
    def verify(self, token: str) -> AuthenticatedUser:
        assert token == "valid-token"
        return AuthenticatedUser(
            user_id=USER_ID,
            role="authenticated",
            session_id=SESSION_ID,
            assurance_level="aal2",
        )


class FakeMembershipResolver:
    def __init__(self, role: AdministrativeRole) -> None:
        self._role = role

    def resolve_active(self, *, user_id: UUID, company_id: UUID) -> ActiveMembership | None:
        if user_id != USER_ID or company_id != COMPANY_ID:
            return None
        return ActiveMembership(
            membership_id=MEMBERSHIP_ID,
            company_id=COMPANY_ID,
            user_id=USER_ID,
            administrative_role=self._role,
            employee_id=uuid4(),
        )


def configuration(status: str = "configured") -> AiProviderConfiguration:
    if status == "not_configured":
        return AiProviderConfiguration(
            status="not_configured",
            credential_hint=None,
            validated_model=None,
            configured_at=None,
            validated_at=None,
            rotated_at=None,
        )
    return AiProviderConfiguration(
        status="configured",
        credential_hint="0123456789ab",
        validated_model="gemini-test",
        configured_at=NOW,
        validated_at=NOW,
        rotated_at=None,
    )


class FakeStore:
    def __init__(self) -> None:
        self.keys: list[str] = []
        self.removals = 0

    def get_configuration(self, **values: Any) -> AiProviderConfiguration:
        assert values["context"].company_id == COMPANY_ID
        return configuration()

    def configure(self, **values: Any) -> AiProviderConfiguration:
        self.keys.append(values["api_key"])
        assert values["validated_model"] == "gemini-test"
        return configuration()

    def remove(self, **values: Any) -> AiProviderConfiguration:
        del values
        self.removals += 1
        return configuration("not_configured")


class FakeValidator:
    def __init__(self, error: Exception | None = None) -> None:
        self.error = error
        self.keys: list[str] = []

    def validate(self, *, api_key: str) -> GeminiCredentialValidation:
        self.keys.append(api_key)
        if self.error:
            raise self.error
        return GeminiCredentialValidation(model="gemini-test")


def client_for(
    role: AdministrativeRole, store: FakeStore, validator: FakeValidator
) -> TestClient:
    application = create_app()
    application.dependency_overrides[get_token_verifier] = FakeVerifier
    application.dependency_overrides[get_membership_resolver] = lambda: FakeMembershipResolver(role)
    application.dependency_overrides[get_ai_provider_store] = lambda: store
    application.dependency_overrides[get_gemini_credential_validator] = lambda: validator
    return TestClient(application)


def headers() -> dict[str, str]:
    return {
        "Authorization": "Bearer valid-token",
        "X-Company-ID": str(COMPANY_ID),
    }


def test_company_admin_can_verify_store_and_remove_a_key_without_disclosure() -> None:
    store = FakeStore()
    validator = FakeValidator()
    with client_for("company_admin", store, validator) as client:
        saved = client.put(
            f"/v1/companies/{COMPANY_ID}/ai-provider/gemini",
            headers=headers(),
            json={"api_key": TEST_KEY, "correlation_id": str(uuid4())},
        )
        loaded = client.get(
            f"/v1/companies/{COMPANY_ID}/ai-provider/gemini", headers=headers()
        )
        removed = client.delete(
            f"/v1/companies/{COMPANY_ID}/ai-provider/gemini",
            headers=headers(),
            params={"correlation_id": str(uuid4())},
        )

    assert saved.status_code == 200
    assert loaded.status_code == 200
    assert removed.status_code == 200
    assert saved.json()["credential_hint"] == "0123456789ab"
    assert TEST_KEY not in saved.text + loaded.text + removed.text
    assert validator.keys == [TEST_KEY]
    assert store.keys == [TEST_KEY]
    assert store.removals == 1


def test_non_admin_cannot_read_or_replace_company_credentials() -> None:
    store = FakeStore()
    validator = FakeValidator()
    with client_for("manager", store, validator) as client:
        loaded = client.get(
            f"/v1/companies/{COMPANY_ID}/ai-provider/gemini", headers=headers()
        )
        saved = client.put(
            f"/v1/companies/{COMPANY_ID}/ai-provider/gemini",
            headers=headers(),
            json={"api_key": TEST_KEY, "correlation_id": str(uuid4())},
        )

    assert loaded.status_code == 403
    assert saved.status_code == 403
    assert validator.keys == []
    assert store.keys == []


def test_invalid_key_is_not_persisted_or_echoed() -> None:
    store = FakeStore()
    validator = FakeValidator(InvalidGeminiCredentialError("provider detail"))
    with client_for("company_admin", store, validator) as client:
        response = client.put(
            f"/v1/companies/{COMPANY_ID}/ai-provider/gemini",
            headers=headers(),
            json={"api_key": TEST_KEY, "correlation_id": str(uuid4())},
        )

    assert response.status_code == 422
    assert TEST_KEY not in response.text
    assert store.keys == []


class FakeModels:
    def __init__(self, error: Exception | None = None) -> None:
        self.error = error
        self.models: list[str] = []

    def get(self, *, model: str) -> object:
        self.models.append(model)
        if self.error:
            raise self.error
        return SimpleNamespace(name=model)


class FakeClient:
    def __init__(self, models: FakeModels) -> None:
        self.models = models
        self.closed = False

    def close(self) -> None:
        self.closed = True


def test_validator_checks_model_access_without_generation_and_closes_client() -> None:
    models = FakeModels()
    client = FakeClient(models)
    validator = GoogleGeminiCredentialValidator(
        model="gemini-test",
        timeout_seconds=2,
        client_factory=lambda key: client if key == TEST_KEY else pytest.fail("wrong key"),
    )

    result = validator.validate(api_key=TEST_KEY)

    assert result.model == "gemini-test"
    assert models.models == ["gemini-test"]
    assert client.closed is True


def test_validator_classifies_rejected_credentials() -> None:
    client = FakeClient(FakeModels(errors.ClientError(403, {})))
    validator = GoogleGeminiCredentialValidator(
        model="gemini-test", timeout_seconds=2, client_factory=lambda _key: client
    )

    with pytest.raises(InvalidGeminiCredentialError):
        validator.validate(api_key=TEST_KEY)
    assert client.closed is True
