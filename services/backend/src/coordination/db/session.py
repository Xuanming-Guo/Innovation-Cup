from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any, Literal
from uuid import UUID

import psycopg
from psycopg.rows import dict_row
from psycopg.sql import SQL, Identifier

RuntimeRole = Literal["coordination_api", "coordination_worker"]


@contextmanager
def authenticated_transaction(
    dsn: str,
    *,
    actor_id: UUID,
    purpose: str,
    connect_timeout_seconds: int = 5,
) -> Iterator[Any]:
    """Auth-only scope for the fixed-policy onboarding procedure, never business queries."""
    with (
        psycopg.connect(
            dsn, connect_timeout=connect_timeout_seconds, row_factory=dict_row
        ) as connection,
        connection.transaction(),
    ):
        connection.execute("set local role coordination_api")
        connection.execute(
            "select set_config('app.actor_id',%s,true),set_config('app.company_id','',true),"
            "set_config('app.demo_run_id','',true),set_config('app.demo_actor_session_id','',true),"
            "set_config('app.purpose',%s,true)",
            (str(actor_id), purpose),
        )
        yield connection


@contextmanager
def company_transaction(
    dsn: str,
    *,
    role: RuntimeRole,
    actor_id: UUID,
    company_id: UUID,
    purpose: str,
    connect_timeout_seconds: int = 5,
    demo_run_id: UUID | None = None,
    demo_actor_session_id: UUID | None = None,
) -> Iterator[Any]:
    """Open one transaction with a least-privileged role and local request context."""

    with (
        psycopg.connect(
            dsn,
            connect_timeout=connect_timeout_seconds,
            row_factory=dict_row,
        ) as connection,
        connection.transaction(),
    ):
        connection.execute(SQL("set local role {}").format(Identifier(role)))
        connection.execute(
            "select set_config('app.actor_id', %s, true), "
            "set_config('app.company_id', %s, true), "
            "set_config('app.purpose', %s, true), "
            "set_config('app.demo_run_id', %s, true), "
            "set_config('app.demo_actor_session_id', %s, true)",
            (
                str(actor_id),
                str(company_id),
                purpose,
                str(demo_run_id) if demo_run_id else "",
                str(demo_actor_session_id) if demo_actor_session_id else "",
            ),
        )
        yield connection


@contextmanager
def worker_transaction(
    dsn: str,
    *,
    purpose: str,
    connect_timeout_seconds: int = 5,
) -> Iterator[Any]:
    """Open a worker-control transaction without manufacturing a tenant actor context."""

    with (
        psycopg.connect(
            dsn,
            connect_timeout=connect_timeout_seconds,
            row_factory=dict_row,
        ) as connection,
        connection.transaction(),
    ):
        connection.execute(SQL("set local role {}").format(Identifier("coordination_worker")))
        connection.execute("select set_config('app.purpose', %s, true)", (purpose,))
        yield connection
