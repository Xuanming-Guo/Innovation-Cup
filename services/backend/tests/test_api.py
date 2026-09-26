from fastapi.testclient import TestClient
from pydantic import SecretStr

from coordination.api.main import create_app
from coordination.config import Settings, get_settings
from coordination.db.health import database_is_ready


def test_liveness_and_version_expose_no_secrets() -> None:
    settings = Settings(
        environment="test",
        build_commit="test-commit",
        database_url=SecretStr("postgresql://user:secret@localhost/database"),
        gemini_api_key=SecretStr("gemini-secret"),
    )
    application = create_app()
    application.dependency_overrides[get_settings] = lambda: settings
    application.dependency_overrides[database_is_ready] = lambda: True

    with TestClient(application) as client:
        live = client.get("/health/live")
        version = client.get("/version")
        ready = client.get("/health/ready")

    assert live.status_code == 200
    assert ready.status_code == 200
    assert ready.json()["checks"] == {"configuration": True, "durable_schema": True}
    assert live.json() == {"service": "coordination-api", "status": "live"}
    assert version.json()["build_commit"] == "test-commit"
    serialized = f"{version.text}{ready.text}"
    assert "gemini-secret" not in serialized
    assert "postgresql://" not in serialized


def test_production_readiness_fails_closed_when_configuration_is_missing() -> None:
    application = create_app()
    application.dependency_overrides[get_settings] = lambda: Settings(
        environment="production",
        database_url=None,
        supabase_jwt_issuer=None,
        supabase_url=None,
    )

    with TestClient(application) as client:
        response = client.get("/health/ready")

    assert response.status_code == 503
    assert response.json()["status"] == "not_ready"
    assert set(response.json()["missing_configuration"]) == {
        "database_url",
        "supabase_jwt_issuer",
        "supabase_url",
    }


def test_native_origins_receive_narrow_cors_headers() -> None:
    application = create_app()

    with TestClient(application) as client:
        allowed = client.options(
            "/v1/session",
            headers={
                "Origin": "tauri://localhost",
                "Access-Control-Request-Method": "GET",
                "Access-Control-Request-Headers": "Authorization,X-Company-ID",
            },
        )
        rejected = client.options(
            "/v1/session",
            headers={
                "Origin": "https://untrusted.example",
                "Access-Control-Request-Method": "GET",
            },
        )

    assert allowed.status_code == 200
    assert allowed.headers["access-control-allow-origin"] == "tauri://localhost"
    assert "access-control-allow-origin" not in rejected.headers
