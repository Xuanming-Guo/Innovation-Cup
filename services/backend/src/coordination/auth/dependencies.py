from __future__ import annotations

from functools import lru_cache
from typing import Annotated
from uuid import UUID

from fastapi import Depends, Header, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from coordination.auth.jwt import (
    AuthenticationError,
    IdentityProviderUnavailableError,
    SupabaseJwtVerifier,
)
from coordination.auth.models import CompanyContext
from coordination.config import Settings, get_settings
from coordination.db.memberships import (
    MembershipResolver,
    MembershipStoreUnavailableError,
    PostgresMembershipResolver,
)

bearer_scheme = HTTPBearer(auto_error=False)


@lru_cache(maxsize=4)
def _cached_verifier(
    issuer: str,
    audience: str,
    jwks_url: str,
    algorithms: tuple[str, ...],
    leeway_seconds: int,
) -> SupabaseJwtVerifier:
    return SupabaseJwtVerifier(
        issuer=issuer,
        audience=audience,
        jwks_url=jwks_url,
        algorithms=algorithms,
        leeway_seconds=leeway_seconds,
    )


def get_token_verifier(settings: Annotated[Settings, Depends(get_settings)]) -> SupabaseJwtVerifier:
    if settings.supabase_jwt_issuer is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="authentication is not configured",
        )
    return _cached_verifier(
        settings.supabase_jwt_issuer,
        settings.supabase_jwt_audience,
        settings.supabase_jwks_url,
        settings.supabase_jwt_algorithm_allowlist,
        settings.supabase_jwt_leeway_seconds,
    )


def get_membership_resolver(
    settings: Annotated[Settings, Depends(get_settings)],
) -> MembershipResolver:
    if settings.database_url is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="membership store is not configured",
        )
    return PostgresMembershipResolver(
        settings.database_url.get_secret_value(),
        connect_timeout_seconds=settings.database_connect_timeout_seconds,
    )


def require_company_context(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
    verifier: Annotated[SupabaseJwtVerifier, Depends(get_token_verifier)],
    memberships: Annotated[MembershipResolver, Depends(get_membership_resolver)],
    company_header: Annotated[str | None, Header(alias="X-Company-ID")] = None,
) -> CompanyContext:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="a bearer access token is required",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if company_header is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="X-Company-ID is required",
        )
    try:
        company_id = UUID(company_header)
    except ValueError as error:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="X-Company-ID must be a UUID",
        ) from error

    try:
        actor = verifier.verify(credentials.credentials)
    except IdentityProviderUnavailableError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="identity provider is temporarily unavailable",
        ) from error
    except AuthenticationError as error:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="access token is invalid",
            headers={"WWW-Authenticate": "Bearer"},
        ) from error

    try:
        membership = memberships.resolve_active(user_id=actor.user_id, company_id=company_id)
    except MembershipStoreUnavailableError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="current membership could not be verified",
        ) from error
    if membership is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="company was not found",
        )

    return CompanyContext(
        actor=actor,
        company_id=membership.company_id,
        membership_id=membership.membership_id,
        administrative_role=membership.administrative_role,
        employee_id=membership.employee_id,
    )


CompanyContextDependency = Annotated[CompanyContext, Depends(require_company_context)]
