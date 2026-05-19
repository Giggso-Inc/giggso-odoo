from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from dataclasses import dataclass
from typing import Any

from mcp.server.auth.provider import AccessToken


class AuthError(RuntimeError):
    """Raised when an MCP caller cannot be mapped to an Odoo user."""


@dataclass(frozen=True)
class IdentityClaims:
    subject: str
    email: str
    scopes: tuple[str, ...]


class IdentityTokenVerifier:
    """Verify identity tokens from enterprise OIDC or a local SSO gateway."""

    def __init__(
        self,
        *,
        secret: str | None = None,
        issuer: str | None = None,
        audience: str | None = None,
        jwks_url: str | None = None,
        leeway_seconds: int = 30,
    ) -> None:
        self.secret = secret.encode("utf-8") if secret else None
        self.issuer = issuer
        self.audience = audience
        self.jwks_url = jwks_url
        self.leeway_seconds = leeway_seconds

    async def verify_token(self, token: str) -> AccessToken | None:
        try:
            claims = self.verify_claims(token)
        except AuthError:
            return None
        return AccessToken(
            token=token,
            client_id=claims.email,
            scopes=list(claims.scopes),
        )

    def verify_claims(self, token: str) -> IdentityClaims:
        if self.jwks_url:
            return self._verify_oidc_claims(token)
        return self._verify_hs256_claims(token)

    def _verify_oidc_claims(self, token: str) -> IdentityClaims:
        try:
            from jwt import PyJWKClient, PyJWTError, decode as jwt_decode
        except ImportError as exc:
            raise AuthError("PyJWT[crypto] is required for JWKS/RS256 identity verification") from exc

        if not self.issuer:
            raise AuthError("OIDC issuer is required for JWKS identity verification")
        if not self.audience:
            raise AuthError("OIDC audience is required for JWKS identity verification")

        try:
            jwk_client = PyJWKClient(self.jwks_url)
            signing_key = jwk_client.get_signing_key_from_jwt(token)
            payload = jwt_decode(
                token,
                signing_key.key,
                algorithms=["RS256"],
                audience=self.audience,
                issuer=self.issuer,
                leeway=self.leeway_seconds,
                options={"require": ["exp", "sub"]},
            )
        except PyJWTError as exc:
            raise AuthError(f"OIDC identity token rejected: {exc}") from exc

        return claims_from_payload(payload)

    def _verify_hs256_claims(self, token: str) -> IdentityClaims:
        if not self.secret:
            raise AuthError("HS256 identity token secret is required when JWKS is not configured")
        header, payload, signature = split_jwt(token)
        algorithm = header.get("alg")
        if algorithm != "HS256":
            raise AuthError(f"Unsupported identity token algorithm: {algorithm}")

        signing_input = ".".join(token.split(".")[:2]).encode("utf-8")
        expected = hmac.new(self.secret, signing_input, hashlib.sha256).digest()
        if not hmac.compare_digest(base64url_encode(expected), signature):
            raise AuthError("Invalid identity token signature")

        now = int(time.time())
        expires_at = payload.get("exp")
        not_before = payload.get("nbf")
        if isinstance(expires_at, int) and now > expires_at + self.leeway_seconds:
            raise AuthError("Identity token has expired")
        if isinstance(not_before, int) and now + self.leeway_seconds < not_before:
            raise AuthError("Identity token is not valid yet")
        if self.issuer and payload.get("iss") != self.issuer:
            raise AuthError("Identity token issuer mismatch")
        if self.audience and not audience_matches(payload.get("aud"), self.audience):
            raise AuthError("Identity token audience mismatch")

        return claims_from_payload(payload)


def claims_from_payload(payload: dict[str, Any]) -> IdentityClaims:
    email = payload.get("email") or payload.get("upn") or payload.get("preferred_username")
    subject = payload.get("sub")
    if not isinstance(email, str) or not email:
        raise AuthError("Identity token must contain an email claim")
    if not isinstance(subject, str) or not subject:
        raise AuthError("Identity token must contain a subject claim")

    raw_scopes = payload.get("scope") or payload.get("scp") or ""
    scopes = tuple(scope for scope in str(raw_scopes).split() if scope)
    return IdentityClaims(subject=subject, email=email, scopes=scopes)


def split_jwt(token: str) -> tuple[dict[str, Any], dict[str, Any], str]:
    parts = token.split(".")
    if len(parts) != 3:
        raise AuthError("Identity token must have three JWT segments")
    header = json.loads(base64url_decode(parts[0]))
    payload = json.loads(base64url_decode(parts[1]))
    if not isinstance(header, dict) or not isinstance(payload, dict):
        raise AuthError("Identity token header and payload must be JSON objects")
    return header, payload, parts[2]


def audience_matches(raw_audience: object, expected: str) -> bool:
    if isinstance(raw_audience, str):
        return raw_audience == expected
    if isinstance(raw_audience, list):
        return expected in raw_audience
    return False


def base64url_decode(value: str) -> bytes:
    padded = value + "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(padded.encode("ascii"))


def base64url_encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")
