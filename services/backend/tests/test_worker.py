import pytest
from pydantic import SecretStr

from coordination.config import Settings
from coordination.worker.main import main, worker_status


def test_worker_once_is_explicitly_foundation_only(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert main(["--once"]) == 0
    captured = capsys.readouterr()
    assert '"queue_consumer_enabled": false' in captured.out


def test_worker_status_contains_no_secret_configuration() -> None:
    status = worker_status(
        Settings(
            database_url=SecretStr("postgresql://user:secret@localhost/db"),
            gemini_api_key=SecretStr("secret"),
        )
    )
    assert "secret" not in str(status)
