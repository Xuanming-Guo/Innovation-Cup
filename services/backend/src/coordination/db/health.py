from __future__ import annotations

from typing import Annotated

import psycopg
from fastapi import Depends

from coordination.config import Settings, get_settings


def database_is_ready(settings: Annotated[Settings, Depends(get_settings)]) -> bool:
    if settings.database_url is None:
        return False
    try:
        with psycopg.connect(
            settings.database_url.get_secret_value(),
            connect_timeout=settings.database_connect_timeout_seconds,
        ) as connection:
            connection.execute("set local role coordination_api")
            row = connection.execute(
                "select to_regprocedure("
                "'app.ensure_durable_job(uuid,text,uuid,text,bytea,uuid)') is not null "
                "and has_function_privilege("
                "'app.ensure_durable_job(uuid,text,uuid,text,bytea,uuid)', 'EXECUTE')"
            ).fetchone()
    except psycopg.Error:
        return False
    return bool(row and row[0])


DatabaseReadinessDependency = Annotated[bool, Depends(database_is_ready)]
