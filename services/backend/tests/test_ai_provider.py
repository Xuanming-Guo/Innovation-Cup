from __future__ import annotations

import json
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any, cast
from urllib.parse import quote
from uuid import UUID, uuid4

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient
from google.auth import exceptions as google_auth_exceptions
from google.genai import errors
from google.oauth2 import service_account
from pydantic import SecretStr

import coordination.ai_provider.gateway_factory as gateway_factory_module
from coordination.ai_provider.contracts import (
    AiCredentialKind,
    AiCredentialValidation,
    AiProviderConfiguration,
    ResolvedAiCredential,
)
from coordination.ai_provider.dependencies import (
    get_ai_provider_store,
    get_gemini_credential_validator,
)
from coordination.ai_provider.gateway_factory import CompanyGeminiGatewayFactory
from coordination.ai_provider.validation import (
    GoogleGeminiCredentialValidator,
    InvalidGeminiCredentialError,
    parse_vertex_service_account,
)
from coordination.api.main import create_app
from coordination.auth.dependencies import get_membership_resolver, get_token_verifier
from coordination.auth.models import AdministrativeRole, AuthenticatedUser, CompanyContext
from coordination.config import Settings
from coordination.db.memberships import ActiveMembership

USER_ID = UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa")
SESSION_ID = UUID("bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb")
COMPANY_ID = UUID("11111111-1111-4111-8111-111111111111")
MEMBERSHIP_ID = UUID("22222222-2222-4222-8222-222222222222")
NOW = datetime(2026, 9, 26, 12, tzinfo=UTC)
TEST_KEY = "test-company-gemini-key-value-0001"
PROJECT_ID = "test-vertex-project"
CLIENT_EMAIL = f"test-service-account@{PROJECT_ID}.iam.gserviceaccount.com"


def service_account_document(**overrides: str) -> str:
    """Build a synthetic, short-lived key so no credential is committed in fixtures."""

    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode("ascii")
    values = {
        "type": "service_account",
        "project_id": PROJECT_ID,
        "private_key_id": "a" * 40,
        "private_key": private_pem,
        "client_email": CLIENT_EMAIL,
        "client_id": "123456789012345678901",
        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
        "token_uri": "https://oauth2.googleapis.com/token",
        "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
        "client_x509_cert_url": (
            f"https://www.googleapis.com/robot/v1/metadata/x509/{quote(CLIENT_EMAIL, safe='')}"
        ),
        "universe_domain": "googleapis.com",
    }
    values.update(overrides)
    return json.dumps(values)


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


def configuration(
    status: str = "configured",
    *,
    credential_kind: AiCredentialKind = "api_key",
) -> AiProviderConfiguration:
    if status == "not_configured":
        return AiProviderConfiguration(
            status="not_configured",
            credential_hint=None,
            validated_model=None,
            configured_at=None,
            validated_at=None,
            rotated_at=None,
        )
    is_vertex = credential_kind == "vertex_service_account"
    return AiProviderConfiguration(
        provider="vertex_ai" if is_vertex else "gemini_developer_api",
        credential_kind=credential_kind,
        status="configured",
        credential_hint="0123456789ab",
        validated_model="gemini-test",
        vertex_project_id=PROJECT_ID if is_vertex else None,
        vertex_client_email=CLIENT_EMAIL if is_vertex else None,
        vertex_location="global" if is_vertex else None,
        configured_at=NOW,
        validated_at=NOW,
        rotated_at=None,
    )


class FakeStore:
    def __init__(self) -> None:
        self.credentials: list[str] = []
        self.validations: list[str] = []
        self.removals = 0

    def get_configuration(self, **values: Any) -> AiProviderConfiguration:
        assert values["context"].company_id == COMPANY_ID
        return configuration()

    def configure(self, **values: Any) -> AiProviderConfiguration:
        self.credentials.append(values["credential_secret"])
        assert values["validated_model"] == "gemini-test"
        return configuration(credential_kind=values["credential_kind"])

    def record_validation(self, **values: Any) -> None:
        self.validations.append(values["outcome"])

    def remove(self, **values: Any) -> AiProviderConfiguration:
        del values
        self.removals += 1
        return configuration("not_configured")


class FakeValidator:
    def __init__(self, error: Exception | None = None) -> None:
        self.error = error
        self.credentials: list[str] = []

    def validate(
        self,
        *,
        credential_kind: AiCredentialKind,
        credential: str,
    ) -> AiCredentialValidation:
        self.credentials.append(credential)
        if self.error:
            raise self.error
        is_vertex = credential_kind == "vertex_service_account"
        return AiCredentialValidation(
            provider="vertex_ai" if is_vertex else "gemini_developer_api",
            credential_kind=credential_kind,
            canonical_credential=SecretStr(credential),
            model="gemini-test",
            vertex_project_id=PROJECT_ID if is_vertex else None,
            vertex_client_email=CLIENT_EMAIL if is_vertex else None,
            vertex_location="global" if is_vertex else None,
        )


def client_for(
    role: AdministrativeRole,
    store: FakeStore,
    validator: FakeValidator,
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


def test_company_admin_can_use_legacy_api_key_request_without_disclosure() -> None:
    store = FakeStore()
    validator = FakeValidator()
    with client_for("company_admin", store, validator) as client:
        saved = client.put(
            f"/v1/companies/{COMPANY_ID}/ai-provider/gemini",
            headers=headers(),
            json={"api_key": TEST_KEY, "correlation_id": str(uuid4())},
        )
        loaded = client.get(f"/v1/companies/{COMPANY_ID}/ai-provider/gemini", headers=headers())
        removed = client.delete(
            f"/v1/companies/{COMPANY_ID}/ai-provider/gemini",
            headers=headers(),
            params={"correlation_id": str(uuid4())},
        )

    assert saved.status_code == loaded.status_code == removed.status_code == 200
    assert saved.json()["credential_kind"] == "api_key"
    assert TEST_KEY not in saved.text + loaded.text + removed.text
    assert validator.credentials == [TEST_KEY]
    assert store.credentials == [TEST_KEY]
    assert store.validations == ["accepted"]
    assert store.removals == 1


def test_company_admin_can_store_vertex_json_and_only_receive_safe_metadata() -> None:
    raw_credential = service_account_document()
    store = FakeStore()
    validator = FakeValidator()
    with client_for("company_admin", store, validator) as client:
        response = client.put(
            f"/v1/companies/{COMPANY_ID}/ai-provider/gemini",
            headers=headers(),
            json={
                "credential_kind": "vertex_service_account",
                "service_account_json": raw_credential,
                "correlation_id": str(uuid4()),
            },
        )

    assert response.status_code == 200
    assert response.json()["provider"] == "vertex_ai"
    assert response.json()["vertex_project_id"] == PROJECT_ID
    assert response.json()["vertex_client_email"] == CLIENT_EMAIL
    assert raw_credential not in response.text
    assert "PRIVATE KEY" not in response.text
    assert store.credentials == [raw_credential]
    assert store.validations == ["accepted"]


def test_non_admin_cannot_read_or_replace_company_credentials() -> None:
    store = FakeStore()
    validator = FakeValidator()
    with client_for("manager", store, validator) as client:
        loaded = client.get(f"/v1/companies/{COMPANY_ID}/ai-provider/gemini", headers=headers())
        saved = client.put(
            f"/v1/companies/{COMPANY_ID}/ai-provider/gemini",
            headers=headers(),
            json={"api_key": TEST_KEY, "correlation_id": str(uuid4())},
        )

    assert loaded.status_code == saved.status_code == 403
    assert validator.credentials == []
    assert store.credentials == []


def test_invalid_credential_is_audited_but_not_persisted_or_echoed() -> None:
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
    assert store.credentials == []
    assert store.validations == ["rejected"]


def test_request_shape_error_does_not_echo_secret_input() -> None:
    marker = "request-shape-secret-marker-value"
    store = FakeStore()
    validator = FakeValidator()
    with client_for("company_admin", store, validator) as client:
        response = client.put(
            f"/v1/companies/{COMPANY_ID}/ai-provider/gemini",
            headers=headers(),
            json={
                "credential_kind": "api_key",
                "api_key": marker,
                "service_account_json": marker * 4,
                "correlation_id": str(uuid4()),
            },
        )

    assert response.status_code == 422
    assert marker not in response.text
    assert validator.credentials == []
    assert store.credentials == []


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


def test_api_key_validator_checks_model_access_without_generation() -> None:
    models = FakeModels()
    client = FakeClient(models)
    captured: dict[str, object] = {}

    def client_factory(**values: object) -> FakeClient:
        captured.update(values)
        return client

    validator = GoogleGeminiCredentialValidator(
        model="gemini-test", timeout_seconds=2, client_factory=client_factory
    )

    result = validator.validate(credential_kind="api_key", credential=TEST_KEY)

    assert result.credential_kind == "api_key"
    assert captured["api_key"] == TEST_KEY
    assert "credentials" not in captured
    assert models.models == ["gemini-test"]
    assert client.closed is True


def test_vertex_validator_builds_an_explicit_scoped_vertex_client() -> None:
    models = FakeModels()
    client = FakeClient(models)
    captured: dict[str, object] = {}

    def client_factory(**values: object) -> FakeClient:
        captured.update(values)
        return client

    validator = GoogleGeminiCredentialValidator(
        model="gemini-test",
        timeout_seconds=2,
        vertex_location="global",
        vertex_allowed_project_ids=(PROJECT_ID,),
        client_factory=client_factory,
    )

    result = validator.validate(
        credential_kind="vertex_service_account",
        credential=service_account_document(),
    )

    google_credentials = cast(service_account.Credentials, captured["credentials"])
    assert captured["vertexai"] is True
    assert captured["project"] == PROJECT_ID
    assert captured["location"] == "global"
    assert google_credentials.service_account_email == CLIENT_EMAIL
    assert google_credentials.scopes == ["https://www.googleapis.com/auth/cloud-platform"]
    assert result.vertex_project_id == PROJECT_ID
    assert result.canonical_credential.get_secret_value().startswith("{")
    assert models.models == ["gemini-test"]
    assert client.closed is True


@pytest.mark.parametrize(
    ("override", "value"),
    [
        ("type", "authorized_user"),
        ("project_id", "Wrong Project"),
        ("client_email", "other@example.com"),
        ("token_uri", "https://example.invalid/token"),
        ("private_key", "-----BEGIN PRIVATE KEY-----\ninvalid\n-----END PRIVATE KEY-----\n"),
    ],
)
def test_vertex_parser_rejects_untrusted_identity_fields(override: str, value: str) -> None:
    with pytest.raises(InvalidGeminiCredentialError):
        parse_vertex_service_account(service_account_document(**{override: value}))


def test_vertex_parser_rejects_pasted_python_instead_of_json() -> None:
    with pytest.raises(InvalidGeminiCredentialError):
        parse_vertex_service_account("from google import genai\nprint('not JSON')")


def test_vertex_parser_rejects_unexpected_duplicate_and_disallowed_project_fields() -> None:
    raw_credential = service_account_document()
    unexpected = json.loads(raw_credential)
    unexpected["unexpected_secret"] = "not-allowed"
    duplicate = raw_credential.replace(
        '{"type":',
        '{"type":"service_account","type":',
        1,
    )

    with pytest.raises(InvalidGeminiCredentialError):
        parse_vertex_service_account(json.dumps(unexpected))
    with pytest.raises(InvalidGeminiCredentialError):
        parse_vertex_service_account(duplicate)
    with pytest.raises(InvalidGeminiCredentialError):
        parse_vertex_service_account(
            raw_credential,
            allowed_project_ids=("different-project",),
        )


def test_validator_classifies_provider_rejection_and_closes_client() -> None:
    client = FakeClient(FakeModels(errors.ClientError(403, {})))
    validator = GoogleGeminiCredentialValidator(
        model="gemini-test",
        timeout_seconds=2,
        client_factory=lambda **_values: client,
    )

    with pytest.raises(InvalidGeminiCredentialError):
        validator.validate(credential_kind="api_key", credential=TEST_KEY)
    assert client.closed is True


def test_validator_classifies_service_account_token_rejection_without_disclosure() -> None:
    token_error = google_auth_exceptions.RefreshError(  # type: ignore[no-untyped-call]
        "token rejected"
    )
    client = FakeClient(FakeModels(token_error))
    validator = GoogleGeminiCredentialValidator(
        model="gemini-test",
        timeout_seconds=2,
        client_factory=lambda **_values: client,
    )

    with pytest.raises(InvalidGeminiCredentialError, match="Google rejected"):
        validator.validate(
            credential_kind="vertex_service_account",
            credential=service_account_document(),
        )
    assert client.closed is True


class FakeCredentialResolver:
    def __init__(self, credential: ResolvedAiCredential) -> None:
        self.credential = credential

    def resolve_google_credential(self, *, context: CompanyContext) -> ResolvedAiCredential:
        assert context.company_id == COMPANY_ID
        return self.credential


def test_worker_factory_selects_vertex_instead_of_api_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    raw_credential = service_account_document()
    captured: dict[str, object] = {}

    def gateway(**values: object) -> Any:
        captured.update(values)
        return object()

    monkeypatch.setattr(gateway_factory_module, "GoogleGeminiGateway", gateway)
    settings = Settings(
        environment="test",
        gemini_model="gemini-test",
        vertex_location="global",
        vertex_allowed_project_ids=PROJECT_ID,
    )
    resolver = FakeCredentialResolver(
        ResolvedAiCredential(
            provider="vertex_ai",
            credential_kind="vertex_service_account",
            credential=SecretStr(raw_credential),
            validated_model="gemini-test",
            vertex_project_id=PROJECT_ID,
            vertex_client_email=CLIENT_EMAIL,
            vertex_location="global",
        )
    )
    context = CompanyContext(
        actor=FakeVerifier().verify("valid-token"),
        company_id=COMPANY_ID,
        membership_id=MEMBERSHIP_ID,
        administrative_role="company_admin",
        employee_id=None,
    )

    result = CompanyGeminiGatewayFactory(settings=settings, credentials=resolver)(context)

    assert result is not None
    assert "api_key" not in captured
    assert captured["vertex_project_id"] == PROJECT_ID
    assert captured["vertex_location"] == "global"
    vertex_credentials = cast(service_account.Credentials, captured["vertex_credentials"])
    assert vertex_credentials.service_account_email == CLIENT_EMAIL
