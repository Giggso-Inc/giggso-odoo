from __future__ import annotations

from dataclasses import dataclass

from .audit import AuditLogger
from .auth import IdentityTokenVerifier
from .config import Settings
from .odoo_client import OdooConnectorClient, OdooConnectorConfig


@dataclass(frozen=True)
class AppServices:
    settings: Settings
    identity: IdentityTokenVerifier
    audit: AuditLogger
    connector: OdooConnectorClient

    @classmethod
    def build(cls, settings: Settings) -> "AppServices":
        return cls(
            settings=settings,
            identity=IdentityTokenVerifier(
                secret=settings.identity_token_secret,
                issuer=settings.identity_issuer,
                audience=settings.identity_audience,
                jwks_url=settings.identity_jwks_url,
            ),
            audit=AuditLogger(settings.audit_log),
            connector=OdooConnectorClient(
                OdooConnectorConfig(
                    url=settings.odoo_url,
                    secret=settings.odoo_connector_secret,
                )
            ),
        )

    def call_odoo(
        self,
        *,
        actor_email: str,
        module: str,
        action: str,
        params: dict[str, object] | None = None,
    ) -> object:
        return self.connector.call(
            actor_email=actor_email,
            module=module,
            action=action,
            params=params,
        )
