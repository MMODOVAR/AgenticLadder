"""Azure Key Vault credential provider."""
from __future__ import annotations

import json
import secrets
from typing import Any

from ...models import RungCredential, RungPolicy
from .base import CredentialProvider, register_provider

RUNG_ROLE_MAP = {
    0: "RungGuardManual",
    1: "RungGuardAssistedReader",
    2: "RungGuardRecommendedContributor",
    3: "RungGuardSupervisedWriter",
    4: "RungGuardConditionalExecutor",
    5: "RungGuardAutonomous",
}


@register_provider("azure")
class AzureCredentialProvider(CredentialProvider):
    def __init__(
        self,
        vault_url: str = "https://rungguard.vault.azure.net/",
        tenant_id: str = "00000000-0000-0000-0000-000000000000",
        client_id: str = "",
        subscription_id: str = "",
        azure_sdk: bool = False,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self.vault_url = vault_url
        self.tenant_id = tenant_id
        self.client_id = client_id
        self.subscription_id = subscription_id
        self.azure_sdk = azure_sdk

    def _secret_name(self, agent_id: str, rung: int) -> str:
        return f"rungguard-{agent_id[:8]}-rung{rung}"

    def issue(self, agent_id: str, rung: int, policy: RungPolicy,
              ttl_seconds: int | None = None) -> RungCredential:
        ttl = ttl_seconds or policy.credential_ttl_seconds
        secret_name = self._secret_name(agent_id, rung)

        if self.azure_sdk:
            from azure.identity import DefaultAzureCredential  # type: ignore[import]
            from azure.keyvault.secrets import SecretClient  # type: ignore[import]
            credential = DefaultAzureCredential()
            client = SecretClient(vault_url=self.vault_url, credential=credential)
            token = secrets.token_urlsafe(32)
            resp = client.set_secret(secret_name, token)
            secret_ref = resp.id
            version = resp.properties.version or ""
        else:
            token = secrets.token_urlsafe(32)
            version = secrets.token_hex(8)
            secret_ref = f"{self.vault_url}secrets/{secret_name}/{version}"

        return self._make_credential(
            agent_id=agent_id,
            assignment_id="",
            rung=rung,
            credential_type="azure_keyvault_secret",
            secret_ref=secret_ref,
            ttl_seconds=ttl,
            metadata={
                "vault_url": self.vault_url,
                "secret_name": secret_name,
                "version": version,
                "role_assignment": RUNG_ROLE_MAP.get(rung, f"RungGuardRung{rung}"),
                "stub": not self.azure_sdk,
            },
        )

    def revoke(self, credential_id: str, secret_ref: str,
               metadata: dict[str, Any]) -> None:
        if not self.azure_sdk:
            return
        try:
            from azure.identity import DefaultAzureCredential  # type: ignore[import]
            from azure.keyvault.secrets import SecretClient  # type: ignore[import]
            credential = DefaultAzureCredential()
            client = SecretClient(vault_url=self.vault_url, credential=credential)
            secret_name = metadata.get("secret_name", "")
            version = metadata.get("version", "")
            props = client.get_secret(secret_name, version).properties
            props.enabled = False
            client.update_secret_properties(props)
        except Exception:
            pass
