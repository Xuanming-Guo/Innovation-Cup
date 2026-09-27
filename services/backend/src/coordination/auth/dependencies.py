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
from coordination.auth.models import AuthenticatedUser, CompanyContext
from coordination.config import Settings, get_settings
from coordination.db.demo import (
    DemoSelectionUnavailableError,
    DemoStoreUnavailableError,
    resolve_demo_context,
)
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
    settings: Annotated[Settings, Depends(get_settings)],
    company_header: Annotated[str | None, Header(alias="X-Company-ID")] = None,
    demo_run_header: Annotated[str | None, Header(alias="X-Demo-Run-ID")] = None,
    demo_actor_header: Annotated[str | None, Header(alias="X-Demo-Actor-Session-ID")] = None,
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
    if actor.is_anonymous and not (
        settings.hackathon_demo and membership.company_is_demo and membership.demo_policy_enabled
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="anonymous access is unavailable for this company",
        )

    context = CompanyContext(
        actor=actor,
        company_id=membership.company_id,
        membership_id=membership.membership_id,
        administrative_role=membership.administrative_role,
        employee_id=membership.employee_id,
    )
    if demo_actor_header and not demo_run_header:
        raise HTTPException(status_code=400, detail="a demo run is required for an actor session")
    if demo_run_header:
        try:
            run_id = UUID(demo_run_header)
            actor_session_id = UUID(demo_actor_header) if demo_actor_header else None
        except ValueError as error:
            raise HTTPException(status_code=400, detail="demo selectors must be UUIDs") from error
        if settings.database_url is None:
            raise HTTPException(status_code=503, detail="demo workspace is unavailable")
        try:
            return resolve_demo_context(
                settings.database_url.get_secret_value(),
                context=context,
                run_id=run_id,
                actor_session_id=actor_session_id,
                connect_timeout_seconds=settings.database_connect_timeout_seconds,
            )
        except DemoSelectionUnavailableError as error:
            raise HTTPException(status_code=404, detail="demo workspace was not found") from error
        except DemoStoreUnavailableError as error:
            raise HTTPException(status_code=503, detail="demo workspace is unavailable") from error
    return context


def require_authenticated_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
    verifier: Annotated[SupabaseJwtVerifier, Depends(get_token_verifier)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> AuthenticatedUser:
    """Authentication without an existing company membership, for guarded onboarding."""
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=401,
            detail="a bearer access token is required",
            headers={"WWW-Authenticate": "Bearer"},
        )
    try:
        actor = verifier.verify(credentials.credentials)
        if actor.is_anonymous and not settings.hackathon_demo:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="anonymous demo access is disabled",
            )
        return actor
    except IdentityProviderUnavailableError as error:
        raise HTTPException(status_code=503, detail="identity provider unavailable") from error
    except AuthenticationError as error:
        raise HTTPException(
            status_code=401,
            detail="access token is invalid",
            headers={"WWW-Authenticate": "Bearer"},
        ) from error


CompanyContextDependency = Annotated[CompanyContext, Depends(require_company_context)]
AuthenticatedUserDependency = Annotated[AuthenticatedUser, Depends(require_authenticated_user)]
