from __future__ import annotations

from collections.abc import Sequence
from typing import Any, Literal, Protocol, cast
from uuid import UUID

import jwt
from jwt import PyJWKClient
from jwt.exceptions import InvalidTokenError, PyJWKClientConnectionError, PyJWKClientError

from coordination.auth.models import AuthenticatedUser


class AuthenticationError(ValueError):
    """Raised when an access token cannot establish an authenticated user."""


class IdentityProviderUnavailableError(RuntimeError):
    """Raised when signing keys cannot be refreshed safely."""


class SigningKey(Protocol):
    key: Any


class SigningKeyClient(Protocol):
    def get_signing_key_from_jwt(self, token: str) -> SigningKey: ...


class SupabaseJwtVerifier:
    """Verify Supabase access tokens locally against the project's rotating JWKS."""

    def __init__(
        self,
        *,
        issuer: str,
        audience: str,
        jwks_url: str,
        algorithms: Sequence[str],
        leeway_seconds: int = 30,
        signing_key_client: SigningKeyClient | None = None,
    ) -> None:
        accepted = tuple(algorithm.strip() for algorithm in algorithms if algorithm.strip())
        if not accepted or any(algorithm.startswith("HS") for algorithm in accepted):
            raise ValueError("only an explicit asymmetric JWT algorithm allowlist is supported")
        self._issuer = issuer.rstrip("/")
        self._audience = audience
        self._algorithms = accepted
        self._leeway_seconds = leeway_seconds
        self._signing_keys = signing_key_client or PyJWKClient(
            jwks_url,
            cache_jwk_set=True,
            lifespan=600,
            timeout=5,
        )

    def verify(self, token: str) -> AuthenticatedUser:
        try:
            header = jwt.get_unverified_header(token)
            algorithm = header.get("alg")
            if algorithm not in self._algorithms:
                raise AuthenticationError("token signing algorithm is not accepted")
            if not isinstance(header.get("kid"), str) or not header["kid"]:
                raise AuthenticationError("token signing key identifier is missing")
            signing_key = self._signing_keys.get_signing_key_from_jwt(token)
            claims = jwt.decode(
                token,
                signing_key.key,
                algorithms=list(self._algorithms),
                audience=self._audience,
                issuer=self._issuer,
                leeway=self._leeway_seconds,
                options={
                    "require": [
                        "aal",
                        "aud",
                        "exp",
                        "iat",
                        "is_anonymous",
                        "iss",
                        "role",
                        "session_id",
                        "sub",
                    ]
                },
            )
            if claims.get("role") != "authenticated":
                raise AuthenticationError("token does not represent an authenticated user")
            if claims.get("is_anonymous") is not False:
                raise AuthenticationError("anonymous sessions are not accepted")
            assurance_level = claims.get("aal")
            if assurance_level not in ("aal1", "aal2"):
                raise AuthenticationError("token assurance level is invalid")
            user_id = UUID(str(claims["sub"]))
            session_id = UUID(str(claims["session_id"]))
        except AuthenticationError:
            raise
        except PyJWKClientConnectionError as error:
            raise IdentityProviderUnavailableError(
                "identity provider signing keys are unavailable"
            ) from error
        except (InvalidTokenError, PyJWKClientError, KeyError, TypeError, ValueError) as error:
            raise AuthenticationError("access token is invalid") from error

        return AuthenticatedUser(
            user_id=user_id,
            role="authenticated",
            session_id=session_id,
            assurance_level=cast(Literal["aal1", "aal2"], assurance_level),
        )
