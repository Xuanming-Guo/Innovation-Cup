from pathlib import Path
from uuid import UUID

from pydantic import SecretStr

from coordination.config import BACKEND_ENV_FILE, Settings
from coordination.interpretation.gateway import GatewayConfiguration


def test_backend_env_file_is_resolved_from_the_backend_project() -> None:
    expected = Path(__file__).resolve().parents[1] / ".env"

    assert expected == BACKEND_ENV_FILE
    assert expected == Settings.model_config["env_file"]


def test_structured_interpretation_uses_a_bounded_sixty_second_default() -> None:
    gateway = GatewayConfiguration(model="gemini-test")

    assert Settings.model_fields["gemini_timeout_seconds"].default == 60
    assert gateway.timeout_seconds == 60
    assert Settings(gemini_timeout_seconds=120).gemini_timeout_seconds == 120


def test_host_registrar_requires_separate_complete_runtime_context() -> None:
    incomplete = Settings(build_commit="a" * 40)
    complete = Settings(
        build_commit="a" * 40,
        database_url=SecretStr("postgresql://runtime@example.invalid/postgres"),
        host_company_id=UUID("11111111-1111-4111-8111-111111111111"),
        host_actor_id=UUID("99999999-9999-4999-8999-999999999999"),
        host_instance_id=UUID("88888888-8888-4888-8888-888888888888"),
    )

    assert not incomplete.host_registrar_configuration_valid
    assert complete.host_registrar_configuration_valid
