from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import time

from odoo_mcp.auth import IdentityTokenVerifier, base64url_encode


def test_identity_token_verifier_accepts_valid_token():
    token = make_token(
        {
            "sub": "user-1",
            "email": "alice@example.com",
            "scope": "crm project",
            "iss": "https://idp.example.com",
            "aud": "odoo-mcp",
            "exp": int(time.time()) + 60,
        },
        "secret",
    )

    access_token = asyncio.run(
        IdentityTokenVerifier(
            secret="secret",
            issuer="https://idp.example.com",
            audience="odoo-mcp",
        ).verify_token(token)
    )

    assert access_token is not None
    assert access_token.client_id == "alice@example.com"
    assert access_token.scopes == ["crm", "project"]


def test_identity_token_verifier_rejects_bad_signature():
    token = make_token(
        {
            "sub": "user-1",
            "email": "alice@example.com",
            "exp": int(time.time()) + 60,
        },
        "wrong",
    )

    access_token = asyncio.run(IdentityTokenVerifier(secret="secret").verify_token(token))

    assert access_token is None


def test_identity_token_verifier_rejects_invalid_jwks_token():
    access_token = asyncio.run(
        IdentityTokenVerifier(
            issuer="https://idp.example.com",
            audience="odoo-mcp",
            jwks_url="https://idp.example.com/.well-known/jwks.json",
        ).verify_token("not-a-jwt")
    )

    assert access_token is None


def make_token(payload: dict[str, object], secret: str) -> str:
    header = {"alg": "HS256", "typ": "JWT"}
    signing_input = ".".join(
        [
            base64url_encode(json.dumps(header, separators=(",", ":"), sort_keys=True).encode("utf-8")),
            base64url_encode(json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")),
        ]
    )
    signature = hmac.new(secret.encode("utf-8"), signing_input.encode("utf-8"), hashlib.sha256).digest()
    return f"{signing_input}.{base64url_encode(signature)}"
