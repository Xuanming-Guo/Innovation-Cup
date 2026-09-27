"""Operator configuration regressions; never read real credentials or open a database."""

from __future__ import annotations

import runpy
import sys
from pathlib import Path
from typing import Any, Protocol, cast
from unittest.mock import Mock
from uuid import UUID

import psycopg
import pytest
from psycopg.conninfo import conninfo_to_dict

SCRIPT_PATH = Path(__file__).resolve().parents[3] / "supabase/scripts/alto_scenario.py"
FAKE_URL = "postgresql://postgres.example:fake-only@database.invalid:5432/postgres"


class OperatorConnection(Protocol):
    def __call__(self, *, env_file: Path, pooler_file: Path) -> str: ...


@pytest.fixture(autouse=True)
def isolate_credentials_and_forbid_connections(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SUPABASE_DB_URL", raising=False)
    monkeypatch.delenv("SUPABASE_DB_PASSWORD", raising=False)

    def forbid_connection(*args: Any, **kwargs: Any) -> None:
        raise AssertionError("Configuration loading must not connect to a database")

    monkeypatch.setattr(psycopg, "connect", forbid_connection)


@pytest.fixture
def script_namespace() -> dict[str, Any]:
    return runpy.run_path(str(SCRIPT_PATH), run_name="alto_scenario_config_test")


@pytest.fixture
def load_connection(script_namespace: dict[str, Any]) -> OperatorConnection:
    return cast(OperatorConnection, script_namespace["operator_connection_string"])


@pytest.fixture
def config_paths(tmp_path: Path) -> tuple[Path, Path]:
    return tmp_path / "operator.env", tmp_path / "pooler-url"


def test_dotenv_url_loads_without_connection_or_output(
    load_connection: OperatorConnection,
    config_paths: tuple[Path, Path],
    capsys: pytest.CaptureFixture[str],
) -> None:
    env_file, pooler_file = config_paths
    env_file.write_text(f'SUPABASE_DB_URL="{FAKE_URL}"\n', encoding="utf-8")

    connection = conninfo_to_dict(load_connection(env_file=env_file, pooler_file=pooler_file))

    assert connection["host"] == "database.invalid"
    assert connection["dbname"] == "postgres"
    assert connection["user"] == "postgres.example"
    assert connection["password"] == "fake-only"
    assert connection["sslmode"] == "require"
    assert connection["connect_timeout"] == "10"
    captured = capsys.readouterr()
    assert captured.out == captured.err == ""


def test_environment_url_overrides_dotenv_url(
    load_connection: OperatorConnection,
    config_paths: tuple[Path, Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    env_file, pooler_file = config_paths
    env_file.write_text(f"SUPABASE_DB_URL={FAKE_URL}\n", encoding="utf-8")
    monkeypatch.setenv("SUPABASE_DB_URL", FAKE_URL.replace("database.invalid", "override.invalid"))

    connection = conninfo_to_dict(load_connection(env_file=env_file, pooler_file=pooler_file))

    assert connection["host"] == "override.invalid"


def test_explicit_url_precedes_password_and_needs_no_linked_project(
    load_connection: OperatorConnection,
    config_paths: tuple[Path, Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    env_file, pooler_file = config_paths
    env_file.write_text(f"SUPABASE_DB_URL={FAKE_URL}\n", encoding="utf-8")
    monkeypatch.setenv("SUPABASE_DB_PASSWORD", "unused-fake-password")

    connection = conninfo_to_dict(load_connection(env_file=env_file, pooler_file=pooler_file))

    assert connection["password"] == "fake-only"
    assert not pooler_file.exists()


@pytest.mark.parametrize("password_source", ["dotenv", "environment"])
def test_linked_password_preserves_reserved_characters_and_environment_precedence(
    load_connection: OperatorConnection,
    config_paths: tuple[Path, Path],
    monkeypatch: pytest.MonkeyPatch,
    password_source: str,
) -> None:
    env_file, pooler_file = config_paths
    password = "fake:@/?#%&= space$only"
    file_password = password if password_source == "dotenv" else "overridden-fake-password"
    env_file.write_text(f"SUPABASE_DB_PASSWORD='{file_password}'\n", encoding="utf-8")
    pooler_file.write_text(
        "postgresql://postgres.example@pooler.invalid:5432/postgres\n", encoding="utf-8"
    )
    if password_source == "environment":
        monkeypatch.setenv("SUPABASE_DB_PASSWORD", password)

    connection = conninfo_to_dict(load_connection(env_file=env_file, pooler_file=pooler_file))

    assert connection["password"] == password
    assert connection["host"] == "pooler.invalid"
    assert connection["user"] == "postgres.example"
    assert connection["dbname"] == "postgres"
    assert connection["sslmode"] == "require"
    assert connection["connect_timeout"] == "10"


def test_missing_configuration_is_actionable(
    load_connection: OperatorConnection, config_paths: tuple[Path, Path]
) -> None:
    env_file, pooler_file = config_paths

    with pytest.raises(ValueError) as error:
        load_connection(env_file=env_file, pooler_file=pooler_file)

    assert "SUPABASE_DB" in str(error.value)


def test_password_without_linked_metadata_fails_without_disclosure(
    load_connection: OperatorConnection,
    config_paths: tuple[Path, Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    env_file, pooler_file = config_paths
    password = "fake-linked-password-never-print"
    monkeypatch.setenv("SUPABASE_DB_PASSWORD", password)

    with pytest.raises(ValueError) as error:
        load_connection(env_file=env_file, pooler_file=pooler_file)

    assert "link" in str(error.value).lower()
    assert password not in str(error.value)


@pytest.mark.parametrize(
    "dsn",
    [
        "https://postgres:fake-secret@database.invalid/postgres",
        "postgresql://postgres:fake-secret@database.invalid/postgres?invalid_option=fake-secret",
    ],
)
def test_invalid_connection_string_is_redacted_and_does_not_fall_back(
    load_connection: OperatorConnection,
    config_paths: tuple[Path, Path],
    monkeypatch: pytest.MonkeyPatch,
    dsn: str,
) -> None:
    env_file, pooler_file = config_paths
    monkeypatch.setenv("SUPABASE_DB_URL", dsn)
    monkeypatch.setenv("SUPABASE_DB_PASSWORD", "fallback-fake-secret")
    pooler_file.write_text(
        "postgresql://postgres.example@pooler.invalid:5432/postgres", encoding="utf-8"
    )

    with pytest.raises(ValueError) as error:
        load_connection(env_file=env_file, pooler_file=pooler_file)

    assert str(error.value)
    assert "fake-secret" not in str(error.value)
    assert "database.invalid" not in str(error.value)
    assert dsn not in str(error.value)


@pytest.mark.parametrize(
    "dsn",
    [
        "dbname=postgres user=operator password=fake-only",
        "host=database.invalid user=operator password=fake-only",
        "host=database.invalid dbname=postgres password=fake-only",
    ],
)
def test_connection_requires_explicit_host_database_and_user(
    load_connection: OperatorConnection,
    config_paths: tuple[Path, Path],
    monkeypatch: pytest.MonkeyPatch,
    dsn: str,
) -> None:
    env_file, pooler_file = config_paths
    monkeypatch.setenv("SUPABASE_DB_URL", dsn)
    monkeypatch.setenv("PGHOST", "ambient.invalid")
    monkeypatch.setenv("PGDATABASE", "ambient_database")
    monkeypatch.setenv("PGUSER", "ambient_user")

    with pytest.raises(ValueError) as error:
        load_connection(env_file=env_file, pooler_file=pooler_file)

    assert "fake-only" not in str(error.value)


@pytest.mark.parametrize(
    ("configured_tls", "expected_tls"),
    [("disable", "require"), ("verify-ca", "verify-ca"), ("verify-full", "verify-full")],
)
def test_key_value_connection_enforces_tls_without_weakening_stricter_modes(
    load_connection: OperatorConnection,
    config_paths: tuple[Path, Path],
    monkeypatch: pytest.MonkeyPatch,
    configured_tls: str,
    expected_tls: str,
) -> None:
    env_file, pooler_file = config_paths
    monkeypatch.setenv(
        "SUPABASE_DB_URL",
        "host=database.invalid dbname=postgres user=operator "
        f"password=fake-only sslmode={configured_tls} connect_timeout=7",
    )

    connection = conninfo_to_dict(load_connection(env_file=env_file, pooler_file=pooler_file))

    assert connection["sslmode"] == expected_tls
    assert connection["connect_timeout"] == "7"


def test_database_error_exposes_sqlstate_but_not_server_message(
    script_namespace: dict[str, Any],
) -> None:
    message = "postgresql://operator:fake-secret@database.invalid/postgres row-value-private"

    diagnostic = script_namespace["safe_database_error"](psycopg.errors.UniqueViolation(message))

    assert "SQLSTATE 23505" in diagnostic
    assert "UniqueViolation" in diagnostic
    assert "fake-secret" not in diagnostic
    assert "database.invalid" not in diagnostic
    assert "row-value-private" not in diagnostic
    assert "postgresql://" not in diagnostic


def test_check_connection_mode_never_provisions_or_requires_confirmation(
    script_namespace: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    main = script_namespace["main"]
    load = Mock(return_value=FAKE_URL)
    check = Mock()
    provision = Mock(side_effect=AssertionError("Read-only mode must never provision"))
    monkeypatch.setattr(sys, "argv", [str(SCRIPT_PATH), "--check-connection"])
    monkeypatch.setitem(main.__globals__, "operator_connection_string", load)
    monkeypatch.setitem(main.__globals__, "check_connection", check)
    monkeypatch.setitem(main.__globals__, "provision", provision)

    main()

    load.assert_called_once_with()
    check.assert_called_once_with(FAKE_URL)
    provision.assert_not_called()


def test_provisioning_requires_confirmation_before_loading_credentials(
    script_namespace: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    main = script_namespace["main"]
    load = Mock(side_effect=AssertionError("Missing confirmation must not load credentials"))
    check = Mock(side_effect=AssertionError("Missing confirmation must not check a connection"))
    provision = Mock(side_effect=AssertionError("Missing confirmation must not provision"))
    monkeypatch.setattr(sys, "argv", [str(SCRIPT_PATH)])
    monkeypatch.setitem(main.__globals__, "operator_connection_string", load)
    monkeypatch.setitem(main.__globals__, "check_connection", check)
    monkeypatch.setitem(main.__globals__, "provision", provision)

    with pytest.raises(SystemExit) as error:
        main()

    assert error.value.code == 2
    load.assert_not_called()
    check.assert_not_called()
    provision.assert_not_called()


def test_hackathon_enable_requires_version_and_explicit_company_confirmation(
    script_namespace: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    main = script_namespace["main"]
    load = Mock(side_effect=AssertionError("invalid CLI must not load credentials"))
    monkeypatch.setattr(sys, "argv", [str(SCRIPT_PATH), "--enable-hackathon-demo"])
    monkeypatch.setitem(main.__globals__, "operator_connection_string", load)

    with pytest.raises(SystemExit) as error:
        main()

    assert error.value.code == 2
    load.assert_not_called()


@pytest.mark.parametrize("enabled", [True, False])
def test_hackathon_operator_mode_uses_only_the_selected_vault_version_reference(
    script_namespace: dict[str, Any], monkeypatch: pytest.MonkeyPatch, enabled: bool
) -> None:
    main = script_namespace["main"]
    provider_version = UUID("17171717-3000-4000-8000-000000000001")
    configure = Mock()
    arguments = [
        str(SCRIPT_PATH),
        "--confirm-synthetic-company",
        "11111111-1111-4111-8111-111111111111",
        "--enable-hackathon-demo" if enabled else "--disable-hackathon-demo",
    ]
    if enabled:
        arguments.extend(["--provider-version", str(provider_version)])
    monkeypatch.setattr(sys, "argv", arguments)
    monkeypatch.setitem(main.__globals__, "operator_connection_string", Mock(return_value=FAKE_URL))
    monkeypatch.setitem(main.__globals__, "configure_hackathon_demo", configure)
    monkeypatch.setitem(
        main.__globals__,
        "provision",
        Mock(side_effect=AssertionError("operator mode must not provision the scenario")),
    )

    main()

    configure.assert_called_once_with(FAKE_URL, provider_version if enabled else None)
