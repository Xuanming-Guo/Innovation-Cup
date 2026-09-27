from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from coordination.auth.jwt import AuthenticationError, SupabaseJwtVerifier

ISSUER = "https://project-ref.supabase.co/auth/v1"
AUDIENCE = "authenticated"


@dataclass
class StaticSigningKey:
    key: Any


class StaticSigningKeyClient:
    def __init__(self, key: Any) -> None:
        self.key = key
        self.calls = 0

    def get_signing_key_from_jwt(self, token: str) -> StaticSigningKey:
        del token
        self.calls += 1
        return StaticSigningKey(self.key)


@pytest.fixture
def rsa_keys() -> tuple[Any, Any]:
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    return private_key, private_key.public_key()


def claims(**overrides: Any) -> dict[str, object]:
    now = datetime.now(UTC)
    value: dict[str, object] = {
        "aal": "aal1",
        "aud": AUDIENCE,
        "exp": now + timedelta(minutes=5),
        "iat": now,
        "is_anonymous": False,
        "iss": ISSUER,
        "role": "authenticated",
        "session_id": str(uuid4()),
        "sub": str(uuid4()),
    }
    value.update(overrides)
    return value


def verifier(public_key: Any) -> SupabaseJwtVerifier:
    return SupabaseJwtVerifier(
        issuer=ISSUER,
        audience=AUDIENCE,
        jwks_url=f"{ISSUER}/.well-known/jwks.json",
        algorithms=("RS256",),
        signing_key_client=StaticSigningKeyClient(public_key),
    )


def encode(payload: dict[str, object], private_key: Any, **headers: object) -> str:
    return jwt.encode(
        payload, private_key, algorithm="RS256", headers={"kid": "test-key", **headers}
    )


def test_verifies_required_supabase_session_claims(rsa_keys: tuple[object, object]) -> None:
    private_key, public_key = rsa_keys
    payload = claims()

    actor = verifier(public_key).verify(encode(payload, private_key))

    assert actor.user_id == UUID(str(payload["sub"]))
    assert actor.session_id == UUID(str(payload["session_id"]))
    assert actor.assurance_level == "aal1"


@pytest.mark.parametrize(
    ("override", "value"),
    [
        ("aud", "wrong-audience"),
        ("iss", "https://attacker.invalid/auth/v1"),
        ("role", "service_role"),
        ("sub", "not-a-uuid"),
        ("session_id", "not-a-uuid"),
        ("aal", "aal3"),
    ],
)
def test_rejects_untrusted_or_malformed_claims(
    rsa_keys: tuple[object, object], override: str, value: object
) -> None:
    private_key, public_key = rsa_keys
    with pytest.raises(AuthenticationError):
        verifier(public_key).verify(encode(claims(**{override: value}), private_key))


def test_rejects_expiry_missing_kid_and_symmetric_algorithm(
    rsa_keys: tuple[Any, Any],
) -> None:
    private_key, public_key = rsa_keys
    expired = claims(exp=datetime.now(UTC) - timedelta(seconds=60))
    with pytest.raises(AuthenticationError):
        verifier(public_key).verify(encode(expired, private_key))

    no_kid = jwt.encode(claims(), private_key, algorithm="RS256")
    with pytest.raises(AuthenticationError):
        verifier(public_key).verify(no_kid)

    hs_token = jwt.encode(
        claims(),
        "not-a-real-secret-value-of-32-bytes",
        algorithm="HS256",
        headers={"kid": "x"},
    )
    with pytest.raises(AuthenticationError):
        verifier(public_key).verify(hs_token)


def test_verifies_anonymous_session_as_explicit_identity_state(
    rsa_keys: tuple[object, object],
) -> None:
    private_key, public_key = rsa_keys

    actor = verifier(public_key).verify(
        encode(claims(is_anonymous=True), private_key)
    )

    assert actor.is_anonymous is True
