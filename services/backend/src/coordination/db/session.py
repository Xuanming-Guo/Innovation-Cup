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
def company_transaction(
    dsn: str,
    *,
    role: RuntimeRole,
    actor_id: UUID,
    company_id: UUID,
    purpose: str,
    connect_timeout_seconds: int = 5,
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
            "set_config('app.purpose', %s, true)",
            (str(actor_id), str(company_id), purpose),
        )
        yield connection
