from __future__ import annotations

import json
import re
from collections.abc import Callable, Collection
from dataclasses import dataclass, field
from typing import Any, Protocol, cast
from urllib.parse import quote

import httpx
from google import genai
from google.auth import exceptions as google_auth_exceptions
from google.genai import errors, types
from google.oauth2 import service_account
from pydantic import SecretStr

from coordination.ai_provider.contracts import AiCredentialKind, AiCredentialValidation

CLOUD_PLATFORM_SCOPE = "https://www.googleapis.com/auth/cloud-platform"
TOKEN_URI = "https://oauth2.googleapis.com/token"
AUTH_URI = "https://accounts.google.com/o/oauth2/auth"
CERT_PROVIDER_URI = "https://www.googleapis.com/oauth2/v1/certs"
UNIVERSE_DOMAIN = "googleapis.com"
PROJECT_ID_PATTERN = re.compile(r"^[a-z][a-z0-9-]{4,28}[a-z0-9]$")
SERVICE_ACCOUNT_NAME_PATTERN = re.compile(r"^[a-z][a-z0-9-]{4,28}[a-z0-9]$")
PRIVATE_KEY_ID_PATTERN = re.compile(r"^[0-9a-f]{40}$")
CLIENT_ID_PATTERN = re.compile(r"^[0-9]{10,32}$")
VERTEX_FIELDS = frozenset(
    {
        "type",
        "project_id",
        "private_key_id",
        "private_key",
        "client_email",
        "client_id",
        "auth_uri",
        "token_uri",
        "auth_provider_x509_cert_url",
        "client_x509_cert_url",
        "universe_domain",
    }
)


class InvalidGeminiCredentialError(RuntimeError):
    """The supplied credential is malformed or cannot access the configured model."""


class GeminiCredentialValidationUnavailableError(RuntimeError):
    """The provider could not complete a credential check safely."""


class GeminiCredentialValidator(Protocol):
    def validate(
        self, *, credential_kind: AiCredentialKind, credential: str
    ) -> AiCredentialValidation: ...


@dataclass(frozen=True)
class ParsedVertexServiceAccount:
    project_id: str
    client_email: str
    canonical_json: str = field(repr=False)
    credentials: service_account.Credentials = field(repr=False)


def _reject_duplicate_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    value: dict[str, object] = {}
    for key, item in pairs:
        if key in value:
            raise ValueError("duplicate service-account field")
        value[key] = item
    return value


def parse_vertex_service_account(
    raw_json: str,
    *,
    allowed_project_ids: Collection[str] = (),
) -> ParsedVertexServiceAccount:
    """Parse and locally validate a Google service-account key without exposing its secret."""

    try:
        decoded = json.loads(raw_json, object_pairs_hook=_reject_duplicate_keys)
    except (json.JSONDecodeError, ValueError) as error:
        raise InvalidGeminiCredentialError("invalid Vertex service-account credential") from error
    if not isinstance(decoded, dict) or set(decoded) != VERTEX_FIELDS:
        raise InvalidGeminiCredentialError("invalid Vertex service-account credential")
    if any(not isinstance(decoded[field], str) for field in VERTEX_FIELDS):
        raise InvalidGeminiCredentialError("invalid Vertex service-account credential")
    values = cast(dict[str, str], decoded)

    project_id = values["project_id"]
    client_email = values["client_email"]
    try:
        service_account_name, email_domain = client_email.split("@", 1)
    except ValueError as error:
        raise InvalidGeminiCredentialError("invalid Vertex service-account credential") from error
    expected_domain = f"{project_id}.iam.gserviceaccount.com"
    expected_cert_url = (
        f"https://www.googleapis.com/robot/v1/metadata/x509/{quote(client_email, safe='')}"
    )
    private_key = values["private_key"]
    project_allowlist = frozenset(allowed_project_ids)
    valid = (
        values["type"] == "service_account"
        and PROJECT_ID_PATTERN.fullmatch(project_id) is not None
        and (not project_allowlist or project_id in project_allowlist)
        and SERVICE_ACCOUNT_NAME_PATTERN.fullmatch(service_account_name) is not None
        and email_domain == expected_domain
        and PRIVATE_KEY_ID_PATTERN.fullmatch(values["private_key_id"]) is not None
        and CLIENT_ID_PATTERN.fullmatch(values["client_id"]) is not None
        and values["auth_uri"] == AUTH_URI
        and values["token_uri"] == TOKEN_URI
        and values["auth_provider_x509_cert_url"] == CERT_PROVIDER_URI
        and values["client_x509_cert_url"] == expected_cert_url
        and values["universe_domain"] == UNIVERSE_DOMAIN
        and private_key.startswith("-----BEGIN PRIVATE KEY-----\n")
        and private_key.endswith("\n-----END PRIVATE KEY-----\n")
        and 1_000 <= len(private_key) <= 16_384
    )
    if not valid:
        raise InvalidGeminiCredentialError("invalid Vertex service-account credential")

    try:
        credentials = service_account.Credentials.from_service_account_info(  # type: ignore[no-untyped-call]
            values,
            scopes=[CLOUD_PLATFORM_SCOPE],
        )
    except (TypeError, ValueError) as error:
        raise InvalidGeminiCredentialError("invalid Vertex service-account credential") from error
    canonical_json = json.dumps(
        values,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    )
    return ParsedVertexServiceAccount(
        project_id=project_id,
        client_email=client_email,
        canonical_json=canonical_json,
        credentials=credentials,
    )


class GoogleGeminiCredentialValidator:
    """Validate API-key or Vertex access without sending company content or generating output."""

    def __init__(
        self,
        *,
        model: str,
        timeout_seconds: int,
        vertex_location: str = "global",
        vertex_allowed_project_ids: Collection[str] = (),
        client_factory: Callable[..., Any] | None = None,
    ) -> None:
        self._model = model
        self._timeout_seconds = timeout_seconds
        self._vertex_location = vertex_location
        self._vertex_allowed_project_ids = tuple(vertex_allowed_project_ids)
        self._client_factory = client_factory or genai.Client

    def validate(
        self, *, credential_kind: AiCredentialKind, credential: str
    ) -> AiCredentialValidation:
        if credential_kind == "api_key":
            if not 20 <= len(credential) <= 512:
                raise InvalidGeminiCredentialError("invalid Gemini API credential")
            client = self._client_factory(
                api_key=credential,
                http_options=self._http_options(),
            )
            validation = AiCredentialValidation(
                provider="gemini_developer_api",
                credential_kind="api_key",
                canonical_credential=SecretStr(credential),
                model=self._model,
            )
        else:
            parsed = parse_vertex_service_account(
                credential,
                allowed_project_ids=self._vertex_allowed_project_ids,
            )
            client = self._client_factory(
                vertexai=True,
                project=parsed.project_id,
                location=self._vertex_location,
                credentials=parsed.credentials,
                http_options=self._http_options(),
            )
            validation = AiCredentialValidation(
                provider="vertex_ai",
                credential_kind="vertex_service_account",
                canonical_credential=SecretStr(parsed.canonical_json),
                model=self._model,
                vertex_project_id=parsed.project_id,
                vertex_client_email=parsed.client_email,
                vertex_location=self._vertex_location,
            )
        try:
            client.models.get(model=self._model)
        except google_auth_exceptions.RefreshError as error:
            raise InvalidGeminiCredentialError(
                "Google rejected the credential or configured model"
            ) from error
        except errors.ClientError as error:
            if error.code in {400, 401, 403, 404}:
                raise InvalidGeminiCredentialError(
                    "Google rejected the credential or configured model"
                ) from error
            raise GeminiCredentialValidationUnavailableError(
                "Google credential validation was throttled"
            ) from error
        except errors.ServerError as error:
            raise GeminiCredentialValidationUnavailableError(
                "Google credential validation is temporarily unavailable"
            ) from error
        except (
            google_auth_exceptions.TransportError,
            httpx.TimeoutException,
            TimeoutError,
            httpx.TransportError,
            ConnectionError,
        ) as error:
            raise GeminiCredentialValidationUnavailableError(
                "Google credential validation could not reach the provider"
            ) from error
        finally:
            close = getattr(client, "close", None)
            if callable(close):
                close()
        return validation

    def _http_options(self) -> types.HttpOptions:
        return types.HttpOptions(timeout=self._timeout_seconds * 1000)
