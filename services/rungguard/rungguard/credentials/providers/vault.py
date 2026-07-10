"""HashiCorp Vault credential provider."""
from __future__ import annotations

import json
import secrets
from typing import Any

from ...models import RungCredential, RungPolicy
from .base import CredentialProvider, register_provider

RUNG_POLICY_MAP = {
    0: "rungguard-rung0-deny-all",
    1: "rungguard-rung1-readonly",
    2: "rungguard-rung2-draft",
    3: "rungguard-rung3-write-reversible",
    4: "rungguard-rung4-conditional",
    5: "rungguard-rung5-autonomous",
}


@register_provider("vault")
class VaultCredentialProvider(CredentialProvider):
    def __init__(
        self,
        vault_addr: str = "https://vault.example.com:8200",
        vault_token: str = "",
        vault_sdk: bool = False,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self.vault_addr = vault_addr
        self.vault_token = vault_token
        self.vault_sdk = vault_sdk

    def issue(self, agent_id: str, rung: int, policy: RungPolicy,
              ttl_seconds: int | None = None) -> RungCredential:
        ttl = ttl_seconds or policy.credential_ttl_seconds or 3600
        vault_policy = RUNG_POLICY_MAP.get(rung, f"rungguard-rung{rung}")

        if self.vault_sdk:
            import hvac  # type: ignore[import]
            client = hvac.Client(url=self.vault_addr, token=self.vault_token)
            resp = client.auth.token.create(
                policies=[vault_policy],
                ttl=f"{ttl}s",
                metadata={"agent_id": agent_id, "rung": str(rung)},
                renewable=False,
            )
            vault_token = resp["auth"]["client_token"]
            accessor = resp["auth"]["accessor"]
            secret_ref = vault_token
        else:
            vault_token = f"hvs.{secrets.token_urlsafe(40)}"
            accessor = secrets.token_urlsafe(12)
            secret_ref = vault_token

        return self._make_credential(
            agent_id=agent_id,
            assignment_id="",
            rung=rung,
            credential_type="vault_token",
            secret_ref=secret_ref,
            ttl_seconds=ttl,
            metadata={
                "vault_addr": self.vault_addr,
                "vault_policy": vault_policy,
                "accessor": accessor,
                "stub": not self.vault_sdk,
            },
        )

    def revoke(self, credential_id: str, secret_ref: str,
               metadata: dict[str, Any]) -> None:
        if not self.vault_sdk:
            return
        try:
            import hvac  # type: ignore[import]
            client = hvac.Client(url=self.vault_addr, token=self.vault_token)
            accessor = metadata.get("accessor", "")
            if accessor:
                client.auth.token.revoke_accessor(accessor)
            else:
                client.auth.token.revoke(secret_ref)
        except Exception:
            pass
