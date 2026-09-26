from pathlib import Path

from coordination.config import BACKEND_ENV_FILE, Settings


def test_backend_env_file_is_resolved_from_the_backend_project() -> None:
    expected = Path(__file__).resolve().parents[1] / ".env"

    assert expected == BACKEND_ENV_FILE
    assert expected == Settings.model_config["env_file"]
